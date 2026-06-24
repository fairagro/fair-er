import os
import json
import requests
import streamlit as st

# ── Config ─────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OR_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/free"

FUSEKI_URL = os.environ.get("FUSEKI_URL", "http://fuseki:3030")
FUSEKI_USER = os.environ.get("FUSEKI_USER", "admin")
FUSEKI_PASSWORD = os.environ.get("FUSEKI_PASSWORD", "")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "")
OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", 11434))

# Models known to support tool calling in Ollama
OLLAMA_TOOL_CAPABLE_MODELS = {
    "llama3.1", "llama3.2", "llama3.3",
    "qwen2.5", "qwen2.5-coder",
    "mistral", "mistral-nemo", "mistral-small",
    "mixtral",
    "command-r", "command-r-plus",
    "firefunction-v2",
    "nemotron-mini",
}

# ── SPARQL tool implementation ─────────────────────────────────────────────────
def run_sparql(dataset: str, query: str) -> str:
    """Execute a SPARQL SELECT query against a Fuseki dataset and return results as JSON string."""
    try:
        response = requests.post(
            f"{FUSEKI_URL}/{dataset}/sparql",
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            auth=(FUSEKI_USER, FUSEKI_PASSWORD),
            timeout=30,
        )
        if response.status_code != 200:
            return f"SPARQL error HTTP {response.status_code}: {response.text[:500]}"
        results = response.json()
        bindings = results.get("results", {}).get("bindings", [])
        if not bindings:
            return "Query returned no results."
        vars_ = results["head"]["vars"]
        lines = [" | ".join(vars_)]
        lines.append("-" * len(lines[0]))
        for row in bindings[:500]:
            lines.append(" | ".join(row.get(v, {}).get("value", "") for v in vars_))
        if len(bindings) > 500:
            lines.append(f"... ({len(bindings) - 500} more rows truncated)")
        lines.append(f"\nTotal rows returned: {len(bindings)}")
        return "\n".join(lines)
    except Exception as e:
        return f"SPARQL execution error: {e}"


def list_fuseki_datasets() -> str:
    """List all available datasets on the Fuseki server."""
    try:
        response = requests.get(
            f"{FUSEKI_URL}/$/datasets",
            auth=(FUSEKI_USER, FUSEKI_PASSWORD),
            timeout=10,
        )
        if response.status_code != 200:
            return f"Error listing datasets: HTTP {response.status_code}"
        datasets = [d["ds.name"].lstrip("/") for d in response.json().get("datasets", [])]
        return "Available datasets: " + ", ".join(datasets)
    except Exception as e:
        return f"Error: {e}"


# ── Tool definitions (OpenAI-compatible tool calling format) ───────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "sparql_query",
            "description": (
                "Execute a SPARQL SELECT query against a named Fuseki dataset. "
                "Use dataset 'FAIR_Metrics' for metric definitions, labels, and dimension mappings. "
                "Use dataset 'bonares', 'openagrar', 'e!dal', 'nsfi', 'publisso', or 'demo' for "
                "DQV measurement data (scores per DOI). "
                "Use dataset 'demo' to query the most recently uploaded evaluation results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset": {
                        "type": "string",
                        "description": "The Fuseki dataset name to query (e.g. 'bonares', 'FAIR_Metrics', 'demo')"
                    },
                    "query": {
                        "type": "string",
                        "description": "A valid SPARQL SELECT query"
                    }
                },
                "required": ["dataset", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_datasets",
            "description": "List all available datasets on the Fuseki server.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a FAIR data quality assistant integrated into a Streamlit application 
that evaluates research datasets against the FAIR principles (Findable, Accessible, Interoperable, Reusable).

You have access to a Fuseki triplestore containing FAIR evaluation results stored as RDF using the 
W3C Data Quality Vocabulary (DQV). You can query it using the sparql_query tool.

Key dataset structure (EXACT — based on actual RDF):
- Measurement datasets: 'bonares', 'openagrar', 'e!dal', 'nsfi', 'publisso', 'demo'
- 'FAIR_Metrics' dataset holds metric definitions, labels, dimensions
- 'demo' holds the most recently uploaded evaluation results

RDF graph pattern (follow this exactly):
  fairagro:dataset-<encoded-doi>  a dcat:Dataset
      dcterms:title "..."
      dcat:distribution fairagro:distribution-<encoded-doi>

  fairagro:distribution-<encoded-doi>  a dcat:Distribution
      dqv:hasQualityMeasurement fairagro:fes_measurement-N__<encoded-doi>
      dqv:hasQualityMeasurement fairagro:fuji_measurement-N__<encoded-doi>
      dcat:accessURL <https://doi.org/...>

  fairagro:fes_measurement-N__<encoded-doi>  a dqv:QualityMeasurement
      dqv:computedBy fairagro:FAIREvaluationServices
      dqv:isMeasurementOf fairagro:FES-SomeMetricName
      dqv:value "0.0"^^xsd:float

  fairagro:fuji_measurement-N__<encoded-doi>  a dqv:QualityMeasurement
      dqv:computedBy fairagro:FUJIAutomatedFAIRDataAssessmentTool
      dqv:isMeasurementOf fairagro:FsF-SomeMetricName-N
      dqv:value "1.0"^^xsd:float

  fairagro:fc_measurement-N__<encoded-doi>  a dqv:QualityMeasurement
      dqv:computedBy fairagro:FAIRChecker
      dqv:isMeasurementOf fairagro:FC-SomeMetricName-<FAIR-principle>
      dqv:value "0.0"^^xsd:float

- dqv:value is xsd:float, AVG(?value) works directly
- Service URIs: fairagro:FAIREvaluationServices, fairagro:FUJIAutomatedFAIRDataAssessmentTool, fairagro:FAIRChecker
- Dimension info is ONLY in FAIR_Metrics dataset, not in measurement datasets
- Dimensions: Findability, Accessibility, Interoperability, Reusability

Useful SPARQL prefixes:
PREFIX dqv: <http://www.w3.org/ns/dqv#>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX fairagro: <https://fairagro.net/ontology#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

WORKING SPARQL EXAMPLES — copy these patterns exactly:

# List all metrics with labels and dimensions from FAIR_Metrics dataset:
PREFIX dqv: <http://www.w3.org/ns/dqv#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?metric ?label ?dimension WHERE {
  ?metric a dqv:Metric .
  OPTIONAL { ?metric skos:prefLabel ?label }
  OPTIONAL { ?metric dqv:inDimension ?dimension }
}

# List all assessed datasets in a measurement dataset (e.g. demo, bonares):
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT ?dataset ?title WHERE {
  ?dataset a dcat:Dataset .
  OPTIONAL { ?dataset dcterms:title ?title }
}

# Get average FAIR score per dataset:
PREFIX dqv: <http://www.w3.org/ns/dqv#>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT ?dataset ?title (AVG(?value) AS ?avgScore) WHERE {
  ?dataset a dcat:Dataset ;
           dcat:distribution ?dist .
  OPTIONAL { ?dataset dcterms:title ?title }
  ?dist dqv:hasQualityMeasurement ?measurement .
  ?measurement dqv:value ?value .
} GROUP BY ?dataset ?title ORDER BY DESC(?avgScore)

# Get all scores for one specific dataset, broken down by service:
PREFIX dqv: <http://www.w3.org/ns/dqv#>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX fairagro: <https://fairagro.net/ontology#>
SELECT ?metric ?service ?value WHERE {
  fairagro:dataset-10.20387%2Fbonares-8186afbb-mnkv-ft18 dcat:distribution ?dist .
  ?dist dqv:hasQualityMeasurement ?measurement .
  ?measurement dqv:isMeasurementOf ?metric ;
               dqv:computedBy ?service ;
               dqv:value ?value .
}
# service values will be one of:
#   fairagro:FAIREvaluationServices  (FES, metric URIs start with fairagro:FES-)
#   fairagro:FUJIAutomatedFAIRDataAssessmentTool  (FUJI, metric URIs start with fairagro:FsF-)
#   fairagro:FAIRChecker  (FC, metric URIs start with fairagro:FC-)

# Get failed metrics (score = 0.0) across all datasets:
PREFIX dqv: <http://www.w3.org/ns/dqv#>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?dataset ?metric ?service WHERE {
  ?dataset a dcat:Dataset ;
           dcat:distribution ?dist .
  ?dist dqv:hasQualityMeasurement ?measurement .
  ?measurement dqv:isMeasurementOf ?metric ;
               dqv:computedBy ?service ;
               dqv:value ?value .
  FILTER(?value = "0.0"^^xsd:float)
}

# Get scores by FAIR dimension (joins measurement dataset with FAIR_Metrics):
# Step 1 — run in measurement dataset (e.g. demo):
PREFIX dqv: <http://www.w3.org/ns/dqv#>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
SELECT ?metric (AVG(?value) AS ?avgScore) WHERE {
  ?dist dqv:hasQualityMeasurement ?measurement .
  ?measurement dqv:isMeasurementOf ?metric ;
               dqv:value ?value .
} GROUP BY ?metric

# Step 2 — run in FAIR_Metrics dataset to get dimension for each metric URI:
PREFIX dqv: <http://www.w3.org/ns/dqv#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?metric ?label ?dimension WHERE {
  ?metric a dqv:Metric .
  OPTIONAL { ?metric skos:prefLabel ?label }
  OPTIONAL { ?metric dqv:inDimension ?dimension }
}

CRITICAL SPARQL RULES:
- Each triple must be on its own line: subject predicate object .
- Never repeat the subject variable as a predicate
- Use OPTIONAL for properties that may not exist on all resources
- Use LIMIT only when explicitly exploring unknown data structure — never when the user asks to list or retrieve all items of something
- Use the exact URI patterns shown above for fairagro datasets
- When unsure about property names, first run a broad SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10 to explore

When answering questions:
- Always query the data rather than making assumptions about scores
- Cross-reference metric URIs between measurement datasets and FAIR_Metrics for labels/definitions
- Be specific about which evaluation service (FES/FUJI/FC) produced each result
- Suggest concrete improvements when scores are low
- When tool results contain tabular data, present ALL rows to the user in a readable format — never summarize or truncate unless there are more than 50 rows, in which case group or summarize meaningfully
- Always state the total number of results returned
- dqv:value is stored as xsd:float — AVG(?value) works directly, no casting needed
- Never use dqv:computedOn — measurements are reached via dcat:distribution then dqv:hasQualityMeasurement
- If a query fails, try a simpler exploratory query first to understand the data structure"""

# ── Tool dispatch ──────────────────────────────────────────────────────────────
def dispatch_tool(name: str, args: dict) -> str:
    if name == "sparql_query":
        return run_sparql(args["dataset"], args["query"])
    elif name == "list_datasets":
        return list_fuseki_datasets()
    return f"Unknown tool: {name}"


# ── Ollama helpers ─────────────────────────────────────────────────────────────
def get_ollama_base_url(ip: str, port: int) -> str:
    return f"http://{ip}:{port}"


def fetch_ollama_models(ip: str, port: int) -> list[str]:
    """Fetch available models from the remote Ollama instance."""
    try:
        resp = requests.get(
            f"{get_ollama_base_url(ip, port)}/api/tags",
            timeout=5,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def ollama_supports_tools(model_name: str) -> bool:
    """Heuristic check: does this model name match a known tool-capable family?"""
    base = model_name.split(":")[0].lower()
    return any(base.startswith(capable) for capable in OLLAMA_TOOL_CAPABLE_MODELS)


# ── LLM API call with tool loop ────────────────────────────────────────────────
def call_llm(messages: list, backend: str, ollama_ip: str, ollama_port: int, ollama_model: str) -> tuple[str, list]:
    """
    Send messages to the selected backend (OpenRouter or Ollama), handle tool calls in a loop.
    Returns (final_text, tool_calls_log).
    """
    if backend == "OpenRouter":
        return _call_openrouter(messages)
    else:
        return _call_ollama(messages, ollama_ip, ollama_port, ollama_model)


def _call_openrouter(messages: list) -> tuple[str, list]:
    if not OPENROUTER_API_KEY:
        return "⚠️ OR_API_KEY environment variable is not set.", []

    tool_log = []
    working_messages = messages.copy()

    for _ in range(10):
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": working_messages,
                "tools": TOOLS,
                "tool_choice": "auto",
                "max_tokens": 4096,
            },
            timeout=60,
        )

        if response.status_code != 200:
            return f"API error HTTP {response.status_code}: {response.text[:500]}", tool_log

        data = response.json()

        if "choices" not in data or not data["choices"]:
            error_msg = data.get("error", {}).get("message", str(data))
            return f"API error: {error_msg}", tool_log

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason")

        working_messages.append(message)

        if finish_reason == "stop" or not message.get("tool_calls"):
            return message.get("content") or "", tool_log

        for tool_call in message["tool_calls"]:
            fn_name = tool_call["function"]["name"]
            try:
                fn_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError as e:
                raw = tool_call["function"]["arguments"]
                working_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": f"Error: malformed tool call arguments (JSON parse error: {e}). Raw: {raw[:300]}"
                })
                tool_log.append({"tool": fn_name, "args": {"error": f"malformed JSON: {raw[:200]}"}, "result_preview": "JSON parse error"})
                continue
            tool_log.append({"tool": fn_name, "args": fn_args})
            result = dispatch_tool(fn_name, fn_args)
            tool_log[-1]["result_preview"] = result[:300]
            working_messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result,
            })

    return "Maximum tool call rounds reached.", tool_log


def _call_ollama(messages: list, ip: str, port: int, model: str) -> tuple[str, list]:
    """
    Call a local Ollama instance using its OpenAI-compatible /v1/chat/completions endpoint.
    Handles tool calling for supported models.
    """
    if not ip:
        return "⚠️ No Ollama host configured. Set OLLAMA_HOST in your .env file.", []
    if not model:
        return "⚠️ No Ollama model selected.", []
    base_url = get_ollama_base_url(ip, port)
    url = f"{base_url}/v1/chat/completions"
    tool_log = []
    working_messages = messages.copy()
    use_tools = ollama_supports_tools(model)

    for _ in range(10):
        payload = {
            "model": model,
            "messages": working_messages,
            "max_tokens": 4096,
        }
        if use_tools:
            payload["tools"] = TOOLS
            payload["tool_choice"] = "auto"

        try:
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=120,  # local models can be slower
            )
        except requests.exceptions.ConnectionError:
            return f"⚠️ Could not connect to Ollama at {base_url}. Check IP, port, and VPN.", tool_log
        except requests.exceptions.Timeout:
            return "⚠️ Request to Ollama timed out. The model may still be loading.", tool_log

        if response.status_code != 200:
            return f"Ollama error HTTP {response.status_code}: {response.text[:500]}", tool_log

        data = response.json()

        if "choices" not in data or not data["choices"]:
            return f"Unexpected Ollama response: {str(data)[:300]}", tool_log

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason")

        working_messages.append(message)

        if not use_tools or finish_reason == "stop" or not message.get("tool_calls"):
            return message.get("content") or "", tool_log

        for tool_call in message["tool_calls"]:
            fn_name = tool_call["function"]["name"]
            try:
                fn_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError as e:
                raw = tool_call["function"]["arguments"]
                working_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": f"Error: malformed tool call arguments (JSON parse error: {e}). Raw: {raw[:300]}"
                })
                tool_log.append({"tool": fn_name, "args": {"error": f"malformed JSON: {raw[:200]}"}, "result_preview": "JSON parse error"})
                continue
            tool_log.append({"tool": fn_name, "args": fn_args})
            result = dispatch_tool(fn_name, fn_args)
            tool_log[-1]["result_preview"] = result[:300]
            working_messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result,
            })

    return "Maximum tool call rounds reached.", tool_log


# ── Streamlit UI ───────────────────────────────────────────────────────────────
st.title("🤖 AI FAIR Analysis Chat")
st.markdown(
    "Ask questions about FAIR evaluation results stored in Fuseki. "
    "The assistant can query any dataset directly to answer your questions."
)

# Session state
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = []
if "tool_logs" not in st.session_state:
    st.session_state["tool_logs"] = []

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("🔧 Backend")

    backend = st.radio(
        "LLM Backend",
        options=["OpenRouter", "Ollama (local)"],
        index=0,
        key="backend",
    )

    if backend == "Ollama (local)":
        st.markdown("**Ollama connection**")
        if OLLAMA_HOST:
            ollama_ip = OLLAMA_HOST
            ollama_port = OLLAMA_PORT
            st.session_state["ollama_ip"] = ollama_ip
            st.session_state["ollama_port"] = ollama_port
            st.caption(f"🖥️ `{ollama_ip}:{ollama_port}` (from .env)")
        else:
            ollama_ip = st.text_input(
                "Office PC IP address",
                value=st.session_state.get("ollama_ip", ""),
                placeholder="e.g. 192.168.1.42",
                key="ollama_ip",
            )
            ollama_port = st.number_input(
                "Port",
                min_value=1,
                max_value=65535,
                value=int(st.session_state.get("ollama_port", 11434)),
                key="ollama_port",
            )

        ollama_model = ""
        if ollama_ip:
            with st.spinner("Fetching models from Ollama…"):
                available_models = fetch_ollama_models(ollama_ip, int(ollama_port))

            if available_models:
                ollama_model = st.selectbox(
                    "Model",
                    options=available_models,
                    key="ollama_model",
                )
                if not ollama_supports_tools(ollama_model):
                    st.warning(
                        f"⚠️ **{ollama_model}** may not support tool calling. "
                        "SPARQL queries won't be available. "
                        "Try llama3.1, qwen2.5, or mistral for full functionality."
                    )
                else:
                    st.success(f"✅ Tool calling supported for `{ollama_model}`")
            else:
                st.error(
                    f"Could not reach Ollama at `{ollama_ip}:{ollama_port}`. "
                    "Check IP, port, and VPN connection."
                )
                ollama_model = st.text_input(
                    "Model name (manual fallback)",
                    placeholder="e.g. llama3.1",
                    key="ollama_model",
                )
        else:
            st.info("Enter the office PC IP address above.")
            ollama_model = st.text_input(
                "Model name",
                placeholder="e.g. llama3.1",
                key="ollama_model",
            )
    else:
        ollama_ip = ""
        ollama_port = 11434
        ollama_model = ""
        st.caption(f"Using OpenRouter model: `{OPENROUTER_MODEL}`")

    st.markdown("---")
    st.subheader("Chat Controls")
    if st.button("🗑️ Clear conversation"):
        st.session_state["chat_messages"] = []
        st.session_state["tool_logs"] = []
        st.rerun()

    st.markdown("---")
    st.subheader("Available Datasets")
    datasets_info = list_fuseki_datasets()
    st.caption(datasets_info)

    st.markdown("---")
    st.subheader("Example Questions")
    examples = [
        "What datasets are in the demo dataset and what are their overall FAIR scores?",
        "Which metrics failed most often across all bonares datasets?",
        "Compare findability scores between FES and FUJI for the demo dataset",
        "What are the top 3 improvements I could make to improve accessibility?",
        "List all metrics in FAIR_Metrics and their dimensions",
        "Which bonares dataset has the highest reusability score?",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex[:20]}"):
            st.session_state["_pending_input"] = ex
            st.rerun()

# ── Chat rendering ─────────────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state["chat_messages"]):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and i < len(st.session_state["tool_logs"]):
            logs = st.session_state["tool_logs"][i]
            if logs:
                with st.expander(f"🔧 {len(logs)} SPARQL query/queries executed"):
                    for log in logs:
                        st.code(
                            f"Tool: {log['tool']}\n"
                            f"Args: {json.dumps(log['args'], indent=2)}\n\n"
                            f"Result preview:\n{log.get('result_preview', '')}",
                            language="text"
                        )

# Handle example button click
pending = st.session_state.pop("_pending_input", None)

# Chat input
user_input = st.chat_input("Ask about your FAIR evaluation results...") or pending

if user_input:
    st.session_state["chat_messages"].append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in st.session_state["chat_messages"]:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply, tool_log = call_llm(
                messages=api_messages,
                backend=st.session_state.get("backend", "OpenRouter"),
                ollama_ip=st.session_state.get("ollama_ip", ""),
                ollama_port=int(st.session_state.get("ollama_port", 11434)),
                ollama_model=st.session_state.get("ollama_model", ""),
            )
        st.markdown(reply)
        if tool_log:
            with st.expander(f"🔧 {len(tool_log)} SPARQL query/queries executed"):
                for log in tool_log:
                    st.code(
                        f"Tool: {log['tool']}\n"
                        f"Args: {json.dumps(log['args'], indent=2)}\n\n"
                        f"Result preview:\n{log.get('result_preview', '')}",
                        language="text"
                    )

    st.session_state["chat_messages"].append({"role": "assistant", "content": reply})
    st.session_state["tool_logs"].append(tool_log)