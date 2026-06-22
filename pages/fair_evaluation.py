import os
import threading
from concurrent.futures import ThreadPoolExecutor

import streamlit as st  # Streamlit for UI rendering
from datetime import datetime  # For tracking start and end times
import plotly.graph_objects as go  # For creating grouped bar charts

from pyvis.network import Network  # For RDF graph visualization
import streamlit.components.v1 as components  # To embed HTML in Streamlit
from requests.exceptions import ConnectTimeout

# Direct imports (no try/except) since these modules and attributes are guaranteed to exist
from FES_evaluation import fes_evaluate_to_list, fes_evaluation_result_example
from FUJI_evaluation import fuji_evaluate_to_list, fuji_evaluation_result_example
from FC_evaluation import fairchecker_evaluate_to_list ,fc_evaluation_result_example

from doi_to_dqv import create_dqv_representation  # Function to generate RDF representation
from rdf_utils import extract_scores_from_rdf  # Utility to extract scores from RDF
from rdflib import RDF, Namespace

# Example FES and FUJI evaluation results (use provided examples)
fes_evaluation_result = fes_evaluation_result_example
fuji_evaluation_result = fuji_evaluation_result_example
fc_evaluation_result = fc_evaluation_result_example

# Streamlit UI
st.title("DOI to FAIR Evaluation")

# Development toggle
development_mode = st.checkbox("Use cached result (Development Mode)", value=False)
# Warn if development mode is on but cached examples are unavailable
if development_mode and (not fes_evaluation_result or not fuji_evaluation_result or not fc_evaluation_result):
    st.info("Cached example results are not available; charts may be empty unless live evaluations are run.")

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

# Checkboxes to include FES and FUJI evaluations
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

# Initialize session state for RDF representation and visualization toggle
if "dqv_representation" not in st.session_state:
    st.session_state["dqv_representation"] = None
if "show_rdf" not in st.session_state:
    st.session_state["show_rdf"] = False
if "bar_chart" not in st.session_state:
    st.session_state["bar_chart"] = None
if "evaluation_attempted" not in st.session_state:
    st.session_state["evaluation_attempted"] = False

def build_grouped_bar_chart(extracted_scores: dict, title: str) -> go.Figure:
    fair_dimensions = ["Findability", "Accessibility", "Interoperability", "Reusability"]

    # Always use whatever data exists in the extracted_scores
    fes_dimension_scores = extracted_scores.get("fes", {})
    fuji_dimension_scores = extracted_scores.get("fuji", {})
    fc_dimension_scores = extracted_scores.get("fc", {})

    fes_dimension_values = [
        fes_dimension_scores.get("findability_score", 0),
        fes_dimension_scores.get("accessibility_score", 0),
        fes_dimension_scores.get("interoperability_score", 0),
        fes_dimension_scores.get("reusability_score", 0),
    ]

    fuji_dimension_values = [
        fuji_dimension_scores.get("findability_score", 0),
        fuji_dimension_scores.get("accessibility_score", 0),
        fuji_dimension_scores.get("interoperability_score", 0),
        fuji_dimension_scores.get("reusability_score", 0),
    ]

    fc_dimension_values = [
        fc_dimension_scores.get("findability_score", 0),
        fc_dimension_scores.get("accessibility_score", 0),
        fc_dimension_scores.get("interoperability_score", 0),
        fc_dimension_scores.get("reusability_score", 0),
    ]

    fair_fig = go.Figure()
    if fes_dimension_scores:
        fair_fig.add_trace(go.Bar(x=fair_dimensions, y=fes_dimension_values, name="FES", marker={"color": "skyblue"}))
    if fuji_dimension_scores:
        fair_fig.add_trace(go.Bar(x=fair_dimensions, y=fuji_dimension_values, name="FUJI", marker={"color": "orange"}))
    if fc_dimension_scores:
        fair_fig.add_trace(go.Bar(x=fair_dimensions, y=fc_dimension_values, name="FC", marker={"color": "green"}))

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

    DQV = Namespace("http://www.w3.org/ns/dqv#")

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
            label = f"{short(metric_str)} ({value_str})"
            net.add_node(metric_node_id, label=label, color="blue")
            seen_nodes.add(metric_node_id)

        # connect tool → metric
        net.add_edge(tool_str, metric_node_id)

    net.barnes_hut()

    html = net.generate_html()
    components.html(html, height=500)


# Add per-DOI storage and selection
if "dqv_by_doi" not in st.session_state:
    st.session_state["dqv_by_doi"] = {}
if "selected_doi" not in st.session_state:
    st.session_state["selected_doi"] = None

# Generate FAIR Evaluation button
if st.button("Generate FAIR Evaluation"):
    # Always reset the visualization state on click to avoid showing stale charts if evaluation fails
    st.session_state["dqv_representation"] = None
    st.session_state["bar_chart"] = None
    st.session_state["show_rdf"] = False
    st.session_state["dqv_by_doi"] = {}
    st.session_state["selected_doi"] = None
    st.session_state["evaluation_attempted"] = True

    # Prepare DOI list (sequential processing across DOIs; FES+FUJI run in parallel per DOI)
    dois_to_process = list(data_dois)

    if dois_to_process:
        # Visual feedback placeholders
        status_box = st.empty()
        log_box = st.empty()
        progress = st.progress(0)
        total = len(dois_to_process)

        for idx, current_doi in enumerate(dois_to_process, start=1):
            status_box.info(f"Processing DOI {idx}/{total}: {current_doi}")

            if development_mode:
                fes_evaluation_result_used = fes_evaluation_result if include_fes else None
                fuji_evaluation_result_used = fuji_evaluation_result if include_fuji else None
                fc_evaluation_result_used = fc_evaluation_result if include_fc else None
            else:
                # Run FES and FUJI in parallel (per DOI)
                fes_evaluation_result_used = None
                fuji_evaluation_result_used = None
                fc_evaluation_result_used = None

                def _now_ts():
                    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

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

                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {}
                    if include_fes:
                        futures["fes"] = executor.submit(_fes_task, current_doi)
                    if include_fuji:
                        futures["fuji"] = executor.submit(_fuji_task, current_doi)
                    if include_fc:
                        futures["fc"] = executor.submit(_fc_task, current_doi)

                    # Collect results — all three tasks now share the same error contract:
                    # success → return value, failure → raise RuntimeError or ConnectTimeout
                    for key, label in [("fes", "FES"), ("fuji", "FUJI"), ("fc", "FC")]:
                        if key not in futures:
                            continue
                        try:
                            result = futures[key].result()
                            if key == "fes":
                                fes_evaluation_result_used = result
                            elif key == "fuji":
                                fuji_evaluation_result_used = result
                            else:
                                fc_evaluation_result_used = result
                        except ConnectTimeout:
                            st.error(f"{label} evaluation timed out. Please check your network connection or try again later.")
                        except RuntimeError as e:
                            st.error(f"{label} evaluation failed: {e}")
                        except Exception as e:
                            st.error(f"{label} evaluation failed: {e}")

            # If any result exists for this DOI, build graph and chart (shows last processed DOI)
            if fes_evaluation_result_used or fuji_evaluation_result_used or fc_evaluation_result_used:
                start_time = datetime.now()
                end_time = datetime.now()

                try:
                    dqv_representation = create_dqv_representation(
                        doi=current_doi,
                        fes_evaluation_result=fes_evaluation_result_used or {},
                        fuji_evaluation_result=fuji_evaluation_result_used or {},
                        fc_evaluation_result=fc_evaluation_result_used or {},
                        start_time=start_time,
                        end_time=end_time,
                    )
                    # Save the graph under the DOI and set selection to current DOI
                    st.session_state["dqv_by_doi"][current_doi] = dqv_representation
                    st.session_state["selected_doi"] = current_doi

                    scores_by_metric = extract_scores_from_rdf(dqv_representation)
            # Another duplicated chart-building section
                    chart_figure = build_grouped_bar_chart(
                        extracted_scores=scores_by_metric,
                        title=f"FAIR Dimension Scores (Grouped by FES, FUJI, FC) — {current_doi}"
                    )
                    st.session_state["bar_chart"] = chart_figure

                    log_box.success(f"Finished DOI {idx}/{total}: {current_doi}")
                except Exception as e:
                    st.error(f"Failed to process RDF representation for {current_doi}: {e}")
            else:
                st.error(f"No scores returned for DOI: {current_doi}")

            progress.progress(int(idx / total * 100))
        # Final state message
        status_box.success("All requested DOIs processed.")
    else:
        st.warning("Please enter at least one DOI.")

# Reset button to clear the session state
if st.button("Reset Visualization and Chart"):
    st.session_state["dqv_representation"] = None
    st.session_state["bar_chart"] = None
    st.session_state["show_rdf"] = False
    st.session_state["dqv_by_doi"] = {}
    st.session_state["selected_doi"] = None
    st.success("Visualization and chart reset successfully.")

# Selector and chart for chosen DOI (supports multiple results)
if st.session_state["dqv_by_doi"]:
    doi_options = list(st.session_state["dqv_by_doi"].keys())

    # Ensure a stable initial selection
    if "selected_doi" not in st.session_state or st.session_state["selected_doi"] not in doi_options:
        first_doi = next(iter(st.session_state["dqv_by_doi"].keys()))
        st.session_state["selected_doi"] = first_doi

    # Initialize and clamp doi_index
    if "doi_index" not in st.session_state:
        st.session_state["doi_index"] = 0
    else:
        st.session_state["doi_index"] = min(st.session_state["doi_index"], len(doi_options) - 1)

    # Make sure selected_doi matches index
    st.session_state["selected_doi"] = doi_options[st.session_state["doi_index"]]

    # Anchor to keep the view from jumping to top on rerun
    st.markdown('<div id="results-anchor"></div>', unsafe_allow_html=True)

    # Only show selectbox if multiple DOIs
    if len(doi_options) > 1:
        st.selectbox(
            "Select DOI to view results:",
            doi_options,
            key="selected_doi",
            on_change=lambda: st.session_state.update({"doi_index": doi_options.index(st.session_state["selected_doi"])})
        )

        # Next / Previous buttons below selectbox
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

    # Build chart for selected DOI
    try:
        rdf_graph_sel = st.session_state["dqv_by_doi"][selected_doi]
        scores_by_metric = extract_scores_from_rdf(rdf_graph_sel)
        fes_scores = scores_by_metric.get("fes", {}) if include_fes else {}
        fuji_scores = scores_by_metric.get("fuji", {}) if include_fuji else {}
        fc_scores = scores_by_metric.get("fc", {}) if include_fc else {}

        chart_figure = build_grouped_bar_chart(
            extracted_scores=scores_by_metric,
            title=f"FAIR Dimension Scores (Grouped by FES, FUJI, FC) — {selected_doi}"
        )
        st.plotly_chart(chart_figure)
    except Exception as e:
        st.error(f"Failed to build chart for {selected_doi}: {e}")
elif st.session_state["bar_chart"] and isinstance(st.session_state["bar_chart"], go.Figure):
    # Fallback for single-DOI legacy path
    st.plotly_chart(st.session_state["bar_chart"])
elif st.session_state["evaluation_attempted"]:
    st.warning("No valid chart available.")

# Button to toggle RDF graph visualization
if st.session_state["dqv_representation"] is not None or st.session_state["dqv_by_doi"]:
    if st.button("Visualize RDF Graph"):
        st.session_state["show_rdf"] = not st.session_state["show_rdf"]

    if st.session_state["show_rdf"]:
        rdf_graph = None

        if (
            st.session_state["dqv_by_doi"]
            and st.session_state["selected_doi"] in st.session_state["dqv_by_doi"]
        ):
            rdf_graph = st.session_state["dqv_by_doi"][st.session_state["selected_doi"]]
        else:
            rdf_graph = st.session_state["dqv_representation"]

        if rdf_graph is not None:
            st.subheader("RDF Graph Visualization")
            render_rdf_graph(rdf_graph)

# Initialize download format selection in the session state
if "download_format" not in st.session_state:
    st.session_state["download_format"] = "Turtle"

# Dropdown menu for format selection (always shown if the graph is available)
rdf_graph = None
sel = st.session_state.get("selected_doi")
if st.session_state["dqv_by_doi"] and sel in st.session_state["dqv_by_doi"]:
    rdf_graph = st.session_state["dqv_by_doi"][sel]
elif st.session_state["dqv_representation"]:
    rdf_graph = st.session_state["dqv_representation"]

format_mapping = None

if rdf_graph:
    download_format = st.selectbox(
        "Select the format to download the RDF representation:",
        ["Turtle", "XML", "N-Triples", "JSON-LD"],
        index=0
    )
    st.session_state["download_format"] = download_format
    format_mapping = {
        "Turtle": ("turtle", "ttl"),
        "XML": ("xml", "xml"),
        "N-Triples": ("nt", "nt"),
        "JSON-LD": ("json-ld", "jsonld")
    }
    selected_format, file_extension = format_mapping[st.session_state["download_format"]]
    try:
        rdf_data = rdf_graph.serialize(format=selected_format)
        safe_name = (sel or "current").replace("/", "_") if sel else "current"
        st.download_button(
            label=f"Download RDF Graph for {sel or 'current'}",
            data=rdf_data,
            file_name=f"rdf_graph_{safe_name}.{file_extension}",
            mime="text/plain"
        )
    except Exception as e:
        st.error(f"Failed to serialize RDF graph: {e}")

# --- Add Download All Files button if multiple DOIs exist ---
if len(st.session_state["dqv_by_doi"]) > 1:
    all_zip_name = "all_dqv_files.zip"
    import io, zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for doi, rdf_graph in st.session_state["dqv_by_doi"].items():
            try:
                selected_format, file_extension = format_mapping[st.session_state["download_format"]]
                rdf_data = rdf_graph.serialize(format=selected_format)
                safe_name = doi.replace("/", "_")
                zipf.writestr(f"rdf_graph_{safe_name}.{file_extension}", rdf_data)
            except Exception as e:
                st.warning(f"Skipping {doi} due to serialization error: {e}")
    zip_buffer.seek(0)

    st.download_button(
        label="Download All RDF Graphs as ZIP",
        data=zip_buffer,
        file_name=all_zip_name,
        mime="application/zip"
    )


# --- Upload to Fuseki (demo dataset) ---
if st.session_state["dqv_by_doi"]:
    st.markdown("---")
    st.subheader("Upload to Fuseki")

    FUSEKI_URL = os.environ.get("FUSEKI_URL", "http://fuseki:3030")
    FUSEKI_USER = os.environ.get("FUSEKI_USER", "admin")
    FUSEKI_PASSWORD = os.environ.get("FUSEKI_PASSWORD", "")
    FUSEKI_DATASET = "demo"

    clear_before_upload = st.checkbox("Clear all existing data in demo dataset before uploading", value=True)

    if st.button("⬆ Upload all results to Fuseki (demo dataset)"):
        import requests as _requests

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
                    st.error(f"Failed to clear demo dataset: HTTP {clear_response.status_code}: {clear_response.text[:200]}")
                    st.stop()
            except Exception as e:
                st.error(f"Failed to clear demo dataset: {e}")
                st.stop()

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
                    upload_results.append(("error", doi, f"HTTP {response.status_code}: {response.text[:200]}"))
            except Exception as e:
                upload_results.append(("error", doi, str(e)))

            progress_fuseki.progress(int(i / total_uploads * 100))

        # Show results
        success_count = sum(1 for r in upload_results if r[0] == "success")
        error_count = len(upload_results) - success_count

        if success_count:
            st.success(f"✅ Successfully uploaded {success_count}/{total_uploads} graphs to `{FUSEKI_DATASET}` dataset.")
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