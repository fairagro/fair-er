import io
import os
import threading
import zipfile
import hmac
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime  # For tracking start and end times

import plotly.graph_objects as go  # For creating grouped bar charts
import requests
import streamlit as st  # Streamlit for UI rendering
import streamlit.components.v1 as components  # To embed HTML in Streamlit
from pyvis.network import Network  # For RDF graph visualization
from rdflib import RDF, Namespace
from requests.exceptions import ConnectTimeout

# Direct imports (no try/except) since these modules and attributes are guaranteed to exist
from FES_evaluation import fes_evaluate_to_list, fes_evaluation_result_example
from FUJI_evaluation import fuji_evaluate_to_list, fuji_evaluation_result_example
from FC_evaluation import fairchecker_evaluate_to_list, fc_evaluation_result_example

from doi_to_dqv import create_dqv_representation  # Function to generate RDF representation
from rdf_utils import extract_scores_from_rdf  # Utility to extract scores from RDF

DQV = Namespace("http://www.w3.org/ns/dqv#")

# Download label -> (rdflib serialization format, file extension)
FORMAT_MAPPING = {
    "Turtle": ("turtle", "ttl"),
    "XML": ("xml", "xml"),
    "N-Triples": ("nt", "nt"),
    "JSON-LD": ("json-ld", "jsonld"),
}

FUSEKI_URL = os.environ.get("FUSEKI_URL", "http://fuseki:3030")
FUSEKI_USER = os.environ.get("FUSEKI_USER", "admin")
FUSEKI_PASSWORD = os.environ.get("FUSEKI_PASSWORD", "")
FUSEKI_DATASET = "demo"


# ── Helpers ────────────────────────────────────────────────────────────────────
def build_grouped_bar_chart(extracted_scores: dict, title: str) -> go.Figure:
    fair_dimensions = ["Findability", "Accessibility", "Interoperability", "Reusability"]
    score_keys = ["findability_score", "accessibility_score", "interoperability_score", "reusability_score"]
    services = [
        ("fes", "FES", "skyblue"),
        ("fuji", "FUJI", "orange"),
        ("fc", "FC", "green"),
    ]

    fair_fig = go.Figure()
    for key, name, color in services:
        dimension_scores = extracted_scores.get(key, {})
        if not dimension_scores:
            continue
        values = [dimension_scores.get(k, 0) for k in score_keys]
        fair_fig.add_trace(go.Bar(x=fair_dimensions, y=values, name=name, marker={"color": color}))

    fair_fig.update_layout(
        title=title,
        xaxis_title="FAIR Dimensions",
        yaxis_title="Scores",
        barmode="group",
        legend_title="Source",
        yaxis=dict(range=[0, 1]),
    )
    return fair_fig


def render_rdf_graph(rdf_graph):
    def short(uri: str) -> str:
        return uri.split("/")[-1].split("#")[-1]

    net = Network(height="500px", width="100%")
    seen_nodes: set[str] = set()

    for measurement in rdf_graph.subjects(RDF.type, DQV.QualityMeasurement):
        metric = rdf_graph.value(measurement, DQV.isMeasurementOf)
        value = rdf_graph.value(measurement, DQV.value)
        tool = rdf_graph.value(measurement, DQV.computedBy)

        if not metric or value is None or not tool:
            continue

        tool_str = str(tool)
        metric_str = str(metric)
        value_str = str(value)

        # create unique node id per tool+metric
        metric_node_id = f"{tool_str}__{metric_str}"

        # tool node
        if tool_str not in seen_nodes:
            net.add_node(tool_str, label=short(tool_str), color="orange")
            seen_nodes.add(tool_str)

        # metric node with value in label
        if metric_node_id not in seen_nodes:
            net.add_node(metric_node_id, label=f"{short(metric_str)} ({value_str})", color="blue")
            seen_nodes.add(metric_node_id)

        # connect tool → metric
        net.add_edge(tool_str, metric_node_id)

    net.barnes_hut()
    components.html(net.generate_html(), height=500)


def clear_results():
    """Reset all evaluation results and derived state."""
    st.session_state["show_rdf"] = False
    st.session_state["dqv_by_doi"] = {}
    st.session_state["scores_by_doi"] = {}
    st.session_state["selected_doi"] = None


def _now_ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# ── Session state ──────────────────────────────────────────────────────────────
if "show_rdf" not in st.session_state:
    st.session_state["show_rdf"] = False
if "evaluation_attempted" not in st.session_state:
    st.session_state["evaluation_attempted"] = False
if "dqv_by_doi" not in st.session_state:
    st.session_state["dqv_by_doi"] = {}
if "scores_by_doi" not in st.session_state:
    # Extracted dimension scores per DOI; computed once after evaluation, reused on every rerun
    st.session_state["scores_by_doi"] = {}
if "selected_doi" not in st.session_state:
    st.session_state["selected_doi"] = None
if "download_format" not in st.session_state:
    st.session_state["download_format"] = "Turtle"

# ── UI: inputs ─────────────────────────────────────────────────────────────────
st.title("DOI to FAIR Evaluation")

# Development toggle: use the cached example results instead of calling the services
development_mode = st.checkbox("Use cached result (Development Mode)", value=False)

# Input field for DOI(s): one per line (also supports a single DOI)
st.markdown("Enter one or more DOIs, one per line.")
data_dois_text = st.text_area(
    "DOI(s)",
    placeholder="10.1000/xyz123\n10.2000/abc456",
    height=120
)
data_dois = [line.strip() for line in data_dois_text.splitlines() if line.strip()]

# Provide a default DOI in developer mode if no input is provided
if development_mode and not data_dois:
    st.warning("Using default DOI for development mode.")
    data_dois = ["10.1000/xyz123"]

# Checkboxes to select the evaluation services
include_fes = st.checkbox(
    "FAIR Evaluation Services (FES)",
    value=True,
    help=(
        "FES is the Wilkinson FAIR Maturity Evaluation Service. It runs a set of "
        "automated 'Maturity Indicator' tests against a dataset's metadata to "
        "check compliance with the FAIR principles."
    ),
)
include_fuji = st.checkbox(
    "F-UJI Automated FAIR Data Assessment Tool",
    value=True,
    help=(
        "F-UJI ('UJI' means 'test' in Malay) is a web service that programmatically "
        "assesses the FAIRness of a dataset based on the FAIRsFAIR Data Object "
        "Assessment Metrics."
    ),
)
include_fc = st.checkbox(
    "FAIR Checker (FC)",
    value=True,
    help=(
        "FAIR Checker inspects a dataset's metadata for FAIR-relevant signals "
        "(identifiers, licenses, vocabularies, provenance, etc.) and reports a "
        "score per FAIR principle."
    ),
)

# ── Evaluation ─────────────────────────────────────────────────────────────────
if st.button("Generate FAIR Evaluation"):
    # Always reset on click to avoid showing stale results if the evaluation fails
    clear_results()
    st.session_state["evaluation_attempted"] = True

    # DOIs are processed sequentially; the three services run in parallel per DOI
    dois_to_process = list(data_dois)

    if dois_to_process:
        status_box = st.empty()
        log_box = st.empty()
        progress = st.progress(0)
        total = len(dois_to_process)

        for idx, current_doi in enumerate(dois_to_process, start=1):
            status_box.info(f"Processing DOI {idx}/{total}: {current_doi}")

            fes_result_used = None
            fuji_result_used = None
            fc_result_used = None

            if development_mode:
                fes_result_used = fes_evaluation_result_example if include_fes else None
                fuji_result_used = fuji_evaluation_result_example if include_fuji else None
                fc_result_used = fc_evaluation_result_example if include_fc else None
            else:
                def _fes_task(doi_1):
                    print(f"[{_now_ts()}] [Thread {threading.current_thread().name}] FES start for DOI: {doi_1}")
                    result, error = fes_evaluate_to_list(doi_1)
                    print(f"[{_now_ts()}] [Thread {threading.current_thread().name}] FES end for DOI: {doi_1}")
                    if error:
                        raise RuntimeError(error)
                    return result

                def _fuji_task(doi_2):
                    print(f"[{_now_ts()}] [Thread {threading.current_thread().name}] FUJI start for DOI: {doi_2}")
                    res = fuji_evaluate_to_list(doi_2)
                    print(f"[{_now_ts()}] [Thread {threading.current_thread().name}] FUJI end for DOI: {doi_2}")
                    return res

                def _fc_task(doi_3):
                    print(f"[{_now_ts()}] [Thread {threading.current_thread().name}] FC start for DOI: {doi_3}")
                    res = fairchecker_evaluate_to_list(doi_3)
                    print(f"[{_now_ts()}] [Thread {threading.current_thread().name}] FC end for DOI: {doi_3}")
                    return res

                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = {}
                    if include_fes:
                        futures["fes"] = executor.submit(_fes_task, current_doi)
                    if include_fuji:
                        futures["fuji"] = executor.submit(_fuji_task, current_doi)
                    if include_fc:
                        futures["fc"] = executor.submit(_fc_task, current_doi)

                    # All three tasks share the same error contract:
                    # success → return value, failure → raise RuntimeError or ConnectTimeout
                    for key, label in [("fes", "FES"), ("fuji", "FUJI"), ("fc", "FC")]:
                        if key not in futures:
                            continue
                        try:
                            result = futures[key].result()
                            if key == "fes":
                                fes_result_used = result
                            elif key == "fuji":
                                fuji_result_used = result
                            else:
                                fc_result_used = result
                        except ConnectTimeout:
                            st.error(f"{label} evaluation timed out. Please check your network connection or try again later.")
                        except Exception as e:
                            st.error(f"{label} evaluation failed: {e}")

            # If any result exists for this DOI, build the graph and extract its scores once
            if fes_result_used or fuji_result_used or fc_result_used:
                try:
                    now = datetime.now()
                    dqv_representation = create_dqv_representation(
                        doi=current_doi,
                        fes_evaluation_result=fes_result_used or {},
                        fuji_evaluation_result=fuji_result_used or {},
                        fc_evaluation_result=fc_result_used or {},
                        start_time=now,
                        end_time=now,
                    )
                    st.session_state["dqv_by_doi"][current_doi] = dqv_representation
                    st.session_state["scores_by_doi"][current_doi] = extract_scores_from_rdf(dqv_representation)
                    st.session_state["selected_doi"] = current_doi

                    log_box.success(f"Finished DOI {idx}/{total}: {current_doi}")
                except Exception as e:
                    st.error(f"Failed to process RDF representation for {current_doi}: {e}")
            else:
                st.error(f"No scores returned for DOI: {current_doi}")

            progress.progress(int(idx / total * 100))

        status_box.success("All requested DOIs processed.")
    else:
        st.warning("Please enter at least one DOI.")

# Reset button to clear the session state
if st.button("Reset Visualization and Chart"):
    clear_results()
    st.success("Visualization and chart reset successfully.")

# ── Results: selector and chart ────────────────────────────────────────────────
selected_doi = None

if st.session_state["dqv_by_doi"]:
    doi_options = list(st.session_state["dqv_by_doi"].keys())

    # Initialize and clamp doi_index; it is the source of truth for the selected DOI
    if "doi_index" not in st.session_state:
        st.session_state["doi_index"] = 0
    st.session_state["doi_index"] = min(st.session_state["doi_index"], len(doi_options) - 1)
    st.session_state["selected_doi"] = doi_options[st.session_state["doi_index"]]

    # Anchor to keep the view from jumping to top on rerun
    st.markdown('<div id="results-anchor"></div>', unsafe_allow_html=True)

    # Only show selectbox and navigation if multiple DOIs
    if len(doi_options) > 1:
        st.selectbox(
            "Select DOI to view results:",
            doi_options,
            key="selected_doi",
            on_change=lambda: st.session_state.update({"doi_index": doi_options.index(st.session_state["selected_doi"])})
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("⬅ Previous") and st.session_state.doi_index > 0:
                st.session_state.doi_index -= 1
        with col2:
            if st.button("Next ➡") and st.session_state.doi_index < len(doi_options) - 1:
                st.session_state.doi_index += 1

    # Current selected DOI
    selected_doi = doi_options[st.session_state["doi_index"]]
    st.write("DOI:", selected_doi)

    # Keep the viewport near results after rerun
    st.markdown(
        '<script>document.getElementById("results-anchor").scrollIntoView({behavior: "instant", block: "start"});</script>',
        unsafe_allow_html=True
    )

    # Build chart for selected DOI (scores were extracted once after evaluation)
    try:
        scores_by_metric = st.session_state["scores_by_doi"].get(selected_doi)
        if scores_by_metric is None:
            # Fallback, e.g. for a session that predates the scores cache
            scores_by_metric = extract_scores_from_rdf(st.session_state["dqv_by_doi"][selected_doi])
            st.session_state["scores_by_doi"][selected_doi] = scores_by_metric

        st.plotly_chart(build_grouped_bar_chart(
            extracted_scores=scores_by_metric,
            title=f"FAIR Dimension Scores (Grouped by FES, FUJI, FC) — {selected_doi}"
        ))
    except Exception as e:
        st.error(f"Failed to build chart for {selected_doi}: {e}")
elif st.session_state["evaluation_attempted"]:
    st.warning("No valid chart available.")

# ── Results: RDF graph visualization ───────────────────────────────────────────
rdf_graph = st.session_state["dqv_by_doi"].get(selected_doi) if selected_doi else None

if rdf_graph is not None:
    if st.button("Visualize RDF Graph"):
        st.session_state["show_rdf"] = not st.session_state["show_rdf"]

    if st.session_state["show_rdf"]:
        st.subheader("RDF Graph Visualization")
        render_rdf_graph(rdf_graph)

    # ── Downloads ──────────────────────────────────────────────────────────────
    download_format = st.selectbox(
        "Select the format to download the RDF representation:",
        list(FORMAT_MAPPING.keys()),
        index=0
    )
    st.session_state["download_format"] = download_format
    selected_format, file_extension = FORMAT_MAPPING[download_format]
    try:
        st.download_button(
            label=f"Download RDF Graph for {selected_doi}",
            data=rdf_graph.serialize(format=selected_format),
            file_name=f"rdf_graph_{selected_doi.replace('/', '_')}.{file_extension}",
            mime="text/plain"
        )
    except Exception as e:
        st.error(f"Failed to serialize RDF graph: {e}")

    # Download all files if multiple DOIs exist
    if len(st.session_state["dqv_by_doi"]) > 1:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for doi, graph in st.session_state["dqv_by_doi"].items():
                try:
                    zipf.writestr(
                        f"rdf_graph_{doi.replace('/', '_')}.{file_extension}",
                        graph.serialize(format=selected_format),
                    )
                except Exception as e:
                    st.warning(f"Skipping {doi} due to serialization error: {e}")
        zip_buffer.seek(0)

        st.download_button(
            label="Download All RDF Graphs as ZIP",
            data=zip_buffer,
            file_name="all_dqv_files.zip",
            mime="application/zip"
        )

# --- Upload to Fuseki (demo dataset) ---
# Disabled unless UPLOAD_PASSWORD is set in the environment (secure by default).
if st.session_state["dqv_by_doi"]:
    st.markdown("---")
    st.subheader("Upload to Fuseki")

    FUSEKI_URL = os.environ.get("FUSEKI_URL", "http://fuseki:3030")
    # Prefer dedicated write credentials for the demo dataset; fall back to the admin account.
    FUSEKI_USER = os.environ.get("FUSEKI_UPLOAD_USER") or os.environ.get("FUSEKI_USER", "admin")
    FUSEKI_PASSWORD = os.environ.get("FUSEKI_UPLOAD_PASSWORD") or os.environ.get("FUSEKI_PASSWORD", "")
    FUSEKI_DATASET = "demo"  # fixed on purpose: never taken from user input
    UPLOAD_PASSWORD = os.environ.get("UPLOAD_PASSWORD", "")

    upload_allowed = False
    if not UPLOAD_PASSWORD:
        st.info("Upload to Fuseki is disabled on this server.")
    elif st.session_state.get("upload_authed"):
        upload_allowed = True
    else:
        upload_pw = st.text_input("Upload password", type="password", key="upload_pw_input")
        if upload_pw:
            if hmac.compare_digest(upload_pw.encode("utf-8"), UPLOAD_PASSWORD.encode("utf-8")):
                st.session_state["upload_authed"] = True
                st.rerun()
            else:
                st.error("Wrong password.")

    if upload_allowed:
        clear_before_upload = st.checkbox("Clear all existing data in demo dataset before uploading", value=True)

        if st.button("⬆ Upload all results to Fuseki (demo dataset)"):
            import requests as _requests

            clear_ok = True

            # Optionally clear all existing data in the demo dataset first
            if clear_before_upload:
                try:
                    clear_response = _requests.post(
                        f"{FUSEKI_URL}/{FUSEKI_DATASET}/update",
                        data="CLEAR ALL",
                        headers={"Content-Type": "application/sparql-update"},
                        auth=(FUSEKI_USER, FUSEKI_PASSWORD),
                        timeout=30,
                    )
                    if clear_response.status_code not in (200, 201, 204):
                        print(f"[upload] clear failed: HTTP {clear_response.status_code}: {clear_response.text[:300]}")
                        st.error(f"Failed to clear the demo dataset (HTTP {clear_response.status_code}).")
                        clear_ok = False
                except Exception as e:
                    print(f"[upload] clear failed: {e}")
                    st.error("Failed to clear the demo dataset: the triplestore is not reachable.")
                    clear_ok = False

            if clear_ok:
                upload_results = []
                progress_fuseki = st.progress(0)
                total_uploads = len(st.session_state["dqv_by_doi"])

                for i, (doi, rdf_g) in enumerate(st.session_state["dqv_by_doi"].items(), start=1):
                    try:
                        turtle_data = rdf_g.serialize(format="turtle")

                        response = _requests.post(
                            f"{FUSEKI_URL}/{FUSEKI_DATASET}/data",
                            data=turtle_data.encode("utf-8") if isinstance(turtle_data, str) else turtle_data,
                            headers={"Content-Type": "text/turtle"},
                            auth=(FUSEKI_USER, FUSEKI_PASSWORD),
                            timeout=30,
                        )
                        if response.status_code in (200, 201, 204):
                            upload_results.append(("success", doi, f"HTTP {response.status_code}"))
                        else:
                            print(f"[upload] {doi}: HTTP {response.status_code}: {response.text[:300]}")
                            upload_results.append(("error", doi, f"HTTP {response.status_code}"))
                    except Exception as e:
                        print(f"[upload] {doi}: {e}")
                        upload_results.append(("error", doi, "upload failed (see server log)"))

                    progress_fuseki.progress(int(i / total_uploads * 100))

                # Show results
                success_count = sum(1 for r in upload_results if r[0] == "success")
                error_count = len(upload_results) - success_count

                if success_count:
                    st.success(
                        f"✅ Successfully uploaded {success_count}/{total_uploads} graphs to the `{FUSEKI_DATASET}` dataset.")
                    with st.expander("Uploaded graphs"):
                        for status, doi, detail in upload_results:
                            if status == "success":
                                st.write(f"**{doi}** → `{detail}`")
                if error_count:
                    st.error(f"❌ {error_count} upload(s) failed.")
                    with st.expander("Upload errors"):
                        for status, doi, detail in upload_results:
                            if status == "error":
                                st.write(f"**{doi}**: {detail}")

# Footer
st.markdown("---")