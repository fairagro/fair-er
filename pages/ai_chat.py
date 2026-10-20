import os
import re
import hmac
import json
import requests
import streamlit as st

def _env_int(name: str, default: int) -> int:
    """Read an int from the environment; empty or invalid values fall back to the default."""
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        print(f"[ai_chat] Invalid value for {name}: using default {default}")
        return default


# ── Config ─────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OR_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/free"

FUSEKI_URL = os.environ.get("FUSEKI_URL", "http://fuseki:3030")
# Prefer a READ-ONLY Fuseki user for the chat; falls back to the admin credentials.
FUSEKI_USER = os.environ.get("FUSEKI_CHAT_USER") or os.environ.get("FUSEKI_USER", "admin")
FUSEKI_PASSWORD = os.environ.get("FUSEKI_CHAT_PASSWORD") or os.environ.get("FUSEKI_PASSWORD", "")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "")
OLLAMA_PORT = _env_int("OLLAMA_PORT", 11434)
# Optional: comma-separated allowlist of models visitors may choose, e.g. "llama3.1:8b,qwen2.5:14b"
OLLAMA_ALLOWED_MODELS = {
    m.strip() for m in os.environ.get("OLLAMA_ALLOWED_MODELS", "").split(",") if m.strip()
}

# Optional shared password for this page. If unset, the page is open.
CHAT_PASSWORD = os.environ.get("CHAT_PASSWORD", "")
# Per-session limits (best effort; a browser refresh starts a new session)
MAX_USER_MESSAGES = _env_int("CHAT_MAX_MESSAGES", 30)
MAX_HISTORY = 20  # number of chat messages sent to the LLM

# Datasets the LLM / sidebar may touch
ALLOWED_DATASETS = {"FAIR_Metrics", "bonares", "openagrar", "e!dal", "nsfi", "publisso", "demo"}

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

# ── SPARQL safety ──────────────────────────────────────────────────────────────
# Best-effort filter. The real protection is a read-only Fuseki user (see above).
FORBIDDEN_SPARQL = re.compile(
    r"\b(SERVICE|INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|COPY|MOVE|ADD|WITH|USING)\b", re.IGNORECASE
)
_COMMENT_LINE = re.compile(r"^\s*#.*$", re.MULTILINE)
_PREFIX_LINE = re.compile(r"^\s*(PREFIX\s+\S*\s*<[^>]*>|BASE\s+<[^>]*>)\s*", re.IGNORECASE | re.MULTILINE)


def is_safe_sparql(query: str) -> bool:
    stripped = _PREFIX_LINE.sub("", _COMMENT_LINE.sub("", query)).strip()
    if not re.match(r"(SELECT|ASK)\b", stripped, re.IGNORECASE):
        return False
    return not FORBIDDEN_SPARQL.search(stripped)


# ── SPARQL tool implementation ─────────────────────────────────────────────────
def run_sparql(dataset: str, query: str) -> str:
    """Execute a SPARQL SELECT/ASK query against an allowed Fuseki dataset."""
    if dataset not in ALLOWED_DATASETS:
        return f"Unknown dataset. Allowed datasets: {', '.join(sorted(ALLOWED_DATASETS))}"
    if not is_safe_sparql(query):
        return "Only plain SELECT or ASK queries are allowed (no SERVICE, updates, etc.)."
    try:
        response = requests.post(
            f"{FUSEKI_URL}/{dataset}/sparql",
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            auth=(FUSEKI_USER, FUSEKI_PASSWORD),
            timeout=30,
        )
        if response.status_code == 400:
            # Syntax errors: useful for the LLM to correct its query
            return f"SPARQL syntax error: {response.text[:300]}"
        if response.status_code != 200:
            print(f"[ai_chat] SPARQL HTTP {response.status_code}: {response.text[:500]}")
            return f"SPARQL query failed (HTTP {response.status_code})."
        results = response.json()
        if "boolean" in results:  # ASK query
            return f"Result: {results['boolean']}"
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
        print(f"[ai_chat] SPARQL execution error: {e}")
        return "SPARQL execution failed. The triplestore may be temporarily unavailable."


@st.cache_data(ttl=60)
def _fetch_fuseki_datasets() -> list[str]:
    """Raises on failure so that failures are not cached."""
    response = requests.get(
        f"{FUSEKI_URL}/$/datasets",
        auth=(FUSEKI_USER, FUSEKI_PASSWORD),
        timeout=10,
    )
    response.raise_for_status()
    names = [d["ds.name"].lstrip("/") for d in response.json().get("datasets", [])]
    return sorted(n for n in names if n in ALLOWED_DATASETS)


def list_fuseki_datasets() -> str:
    """List the available (allowed) datasets on the Fuseki server."""
    try:
        return "Available datasets: " + ", ".join(_fetch_fuseki_datasets())
    except Exception as e:
        print(f"[ai_chat] Error listing datasets: {e}")
        return "Dataset list is currently unavailable."


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
    if not isinstance(args, dict):
        return "Error: tool arguments must be a JSON object."
    if name == "sparql_query":
        return run_sparql(str(args.get("dataset", "")), str(args.get("query", "")))
    elif name == "list_datasets":
        return list_fuseki_datasets()
    return f"Unknown tool: {name}"


# ── Ollama helpers ─────────────────────────────────────────────────────────────
def get_ollama_base_url(ip: str, port: int) -> str:
    return f"http://{ip}:{port}"


@st.cache_data(ttl=60)
def _fetch_ollama_models_cached(ip: str, port: int) -> list[str]:
    """Raises on failure so that failures are not cached (cache lives server-side only)."""
    resp = requests.get(f"{get_ollama_base_url(ip, port)}/api/tags", timeout=5)
    resp.raise_for_status()
    return [m["name"] for m in resp.json().get("models", [])]


def fetch_ollama_models(ip: str, port: int) -> list[str]:
    """Fetch available models from the Ollama instance, filtered by the optional allowlist."""
    try:
        models = _fetch_ollama_models_cached(ip, port)
    except Exception as e:
        print(f"[ai_chat] Could not fetch Ollama models: {e}")
        return []
    if OLLAMA_ALLOWED_MODELS:
        models = [m for m in models if m in OLLAMA_ALLOWED_MODELS]
    return models


def ollama_supports_tools(model_name: str) -> bool:
    """Heuristic check: does this model name match a known tool-capable family?"""
    base = model_name.split(":")[0].lower()
    return any(base.startswith(capable) for capable in OLLAMA_TOOL_CAPABLE_MODELS)


# ── LLM API call with tool loop ────────────────────────────────────────────────
def call_llm(messages: list, backend: str, ollama_model: str) -> tuple[str, list]:
    """
    Send messages to the selected backend (OpenRouter or Ollama), handle tool calls in a loop.
    Returns (final_text, tool_calls_log).
    """
    if backend == "OpenRouter":
        return _call_openrouter(messages)
    return _call_ollama(messages, ollama_model)


def _parse_tool_args(tool_call: dict, working_messages: list, tool_log: list):
    """Parse tool call arguments. Returns dict or None (after logging the error to the LLM)."""
    fn_name = tool_call["function"]["name"]
    raw = tool_call["function"].get("arguments") or "{}"
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
        return args
    except (json.JSONDecodeError, ValueError) as e:
        working_messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": f"Error: malformed tool call arguments ({e}). Raw: {str(raw)[:300]}"
        })
        tool_log.append({"tool": fn_name, "args": {"error": f"malformed JSON: {str(raw)[:200]}"},
                         "result_preview": "JSON parse error"})
        return None


def _run_tool_calls(message: dict, working_messages: list, tool_log: list) -> None:
    for tool_call in message["tool_calls"]:
        fn_name = tool_call["function"]["name"]
        fn_args = _parse_tool_args(tool_call, working_messages, tool_log)
        if fn_args is None:
            continue
        tool_log.append({"tool": fn_name, "args": fn_args})
        result = dispatch_tool(fn_name, fn_args)
        tool_log[-1]["result_preview"] = result[:300]
        working_messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": result,
        })


def _call_openrouter(messages: list) -> tuple[str, list]:
    if not OPENROUTER_API_KEY:
        return "⚠️ The OpenRouter backend is not configured on this server.", []

    tool_log = []
    working_messages = messages.copy()

    for _ in range(10):
        try:
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
        except requests.exceptions.Timeout:
            return "⚠️ The request to the LLM service timed out. Please try again.", tool_log
        except requests.exceptions.RequestException as e:
            print(f"[ai_chat] OpenRouter request failed: {e}")
            return "⚠️ Could not reach the LLM service. Please try again later.", tool_log

        if response.status_code != 200:
            print(f"[ai_chat] OpenRouter HTTP {response.status_code}: {response.text[:500]}")
            return f"⚠️ The LLM service returned an error (HTTP {response.status_code}).", tool_log

        try:
            data = response.json()
        except ValueError:
            print(f"[ai_chat] OpenRouter returned non-JSON: {response.text[:300]}")
            return "⚠️ The LLM service returned an invalid response.", tool_log

        if "choices" not in data or not data["choices"]:
            print(f"[ai_chat] OpenRouter unexpected response: {str(data)[:500]}")
            return "⚠️ The LLM service returned an unexpected response.", tool_log

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason")

        working_messages.append(message)

        if finish_reason == "stop" or not message.get("tool_calls"):
            return message.get("content") or "", tool_log

        _run_tool_calls(message, working_messages, tool_log)

    return "Maximum tool call rounds reached.", tool_log


def _call_ollama(messages: list, model: str) -> tuple[str, list]:
    """
    Call the configured Ollama instance using its OpenAI-compatible /v1/chat/completions endpoint.
    Handles tool calling for supported models. The host never appears in any returned message.
    """
    if not OLLAMA_HOST:
        return "⚠️ Local Ollama is not configured on this server.", []
    if not model:
        return "⚠️ No Ollama model selected.", []
    if OLLAMA_ALLOWED_MODELS and model not in OLLAMA_ALLOWED_MODELS:
        return "⚠️ This model is not allowed.", []

    url = f"{get_ollama_base_url(OLLAMA_HOST, OLLAMA_PORT)}/v1/chat/completions"
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
        except requests.exceptions.Timeout:
            return "⚠️ The request to the local model timed out. The model may still be loading.", tool_log
        except requests.exceptions.ConnectionError as e:
            print(f"[ai_chat] Ollama connection error: {e}")
            return "⚠️ The local model is currently unavailable.", tool_log
        except requests.exceptions.RequestException as e:
            print(f"[ai_chat] Ollama request failed: {e}")
            return "⚠️ The request to the local model failed.", tool_log

        if response.status_code != 200:
            print(f"[ai_chat] Ollama HTTP {response.status_code}: {response.text[:500]}")
            return f"⚠️ The local model returned an error (HTTP {response.status_code}).", tool_log

        try:
            data = response.json()
        except ValueError:
            print(f"[ai_chat] Ollama returned non-JSON: {response.text[:300]}")
            return "⚠️ The local model returned an invalid response.", tool_log

        if "choices" not in data or not data["choices"]:
            print(f"[ai_chat] Ollama unexpected response: {str(data)[:500]}")
            return "⚠️ The local model returned an unexpected response.", tool_log

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason")

        working_messages.append(message)

        if not use_tools or finish_reason == "stop" or not message.get("tool_calls"):
            return message.get("content") or "", tool_log

        _run_tool_calls(message, working_messages, tool_log)

    return "Maximum tool call rounds reached.", tool_log


# ── UI helpers ─────────────────────────────────────────────────────────────────
def require_password() -> None:
    """Optional shared-password gate. Active only if CHAT_PASSWORD is set."""
    if not CHAT_PASSWORD or st.session_state.get("chat_authed"):
        return
    st.info("This page is password protected.")
    pw = st.text_input("Password", type="password")
    if pw:
        if hmac.compare_digest(pw.encode("utf-8"), CHAT_PASSWORD.encode("utf-8")):
            st.session_state["chat_authed"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


def render_tool_log(logs: list) -> None:
    if not logs:
        return
    with st.expander(f"🔧 {len(logs)} SPARQL query/queries executed"):
        for log in logs:
            st.code(
                f"Tool: {log['tool']}\n"
                f"Args: {json.dumps(log['args'], indent=2)}\n\n"
                f"Result preview:\n{log.get('result_preview', '')}",
                language="text"
            )


# ── Streamlit UI ───────────────────────────────────────────────────────────────
st.title("🤖 AI FAIR Analysis Chat")
require_password()

st.markdown(
    "Ask questions about FAIR evaluation results stored in Fuseki. "
    "The assistant can query any dataset directly to answer your questions."
)

# Session state
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = []
if "user_message_count" not in st.session_state:
    st.session_state["user_message_count"] = 0  # not reset by "Clear conversation"

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("🔧 Backend")

    backend = st.radio(
        "LLM Backend",
        options=["OpenRouter", "Ollama (local)"],
        index=0,
        key="backend",
    )

    ollama_model = ""
    if backend == "Ollama (local)":
        if not OLLAMA_HOST:
            st.warning("Local Ollama is not configured on this server.")
        else:
            st.caption("🖥️ Local Ollama server")
            with st.spinner("Fetching models…"):
                available_models = fetch_ollama_models(OLLAMA_HOST, OLLAMA_PORT)

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
                st.error("The local Ollama server is currently unavailable.")
    else:
        st.caption(f"Using OpenRouter model: `{OPENROUTER_MODEL}`")

    st.markdown("---")
    st.subheader("Chat Controls")
    if st.button("🗑️ Clear conversation"):
        st.session_state["chat_messages"] = []
        st.rerun()

    st.markdown("---")
    st.subheader("Available Datasets")
    st.caption(list_fuseki_datasets())

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
for msg in st.session_state["chat_messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_tool_log(msg.get("tool_log"))

# Handle example button click
pending = st.session_state.pop("_pending_input", None)

# Chat input (disabled once the per-session limit is reached)
limit_reached = st.session_state["user_message_count"] >= MAX_USER_MESSAGES
if limit_reached:
    st.warning("Message limit for this session reached. Please reload the page to start a new session.")
user_input = st.chat_input("Ask about your FAIR evaluation results...", disabled=limit_reached) or pending

if user_input and not limit_reached:
    st.session_state["user_message_count"] += 1
    st.session_state["chat_messages"].append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    # Only send the last MAX_HISTORY messages (role + content only), starting with a user message
    history = st.session_state["chat_messages"][-MAX_HISTORY:]
    while history and history[0]["role"] != "user":
        history = history[1:]
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    api_messages += [{"role": m["role"], "content": m["content"]} for m in history]

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply, tool_log = call_llm(
                messages=api_messages,
                backend=st.session_state.get("backend", "OpenRouter"),
                ollama_model=ollama_model,
            )
        st.markdown(reply)
        render_tool_log(tool_log)

    st.session_state["chat_messages"].append(
        {"role": "assistant", "content": reply, "tool_log": tool_log}
    )