import streamlit as st

st.title("About This App")
st.write(
    "This application is designed to provide tools and resources for FAIR data evaluation. "
    "It supports agricultural research by enabling users to assess and improve the FAIRness of their data."
)

st.subheader("Features")
st.markdown(
    """
    - **FAIR Evaluation**: Assess the FAIRness of one or more datasets by DOI with three independent
      tools (FAIR Maturity Evaluation Service, F-UJI and FAIR-Checker), compare their scores per FAIR
      dimension, and download the results as RDF using the Data Quality Vocabulary (Turtle, RDF/XML,
      N-Triples or JSON-LD).
    - **AI Analysis**: Ask questions about stored evaluation results in natural language. The assistant
      answers by querying the triplestore with SPARQL.
    - **SPARQL Explorer**: Query and explore the linked data of the FAIR metrics and the evaluated
      repositories.
    - **RDI Evaluation**: Sample FAIR scores for research data infrastructures (RDIs).
    - **Resource Uploader**: Publish an RDF file and get a URL under which it can be retrieved.
    - **GitHub Repository**: Access the source code and documentation.
    """
)

st.subheader("How the scores are computed")
st.write(
    "Each tool tests a set of metrics, and every metric result is stored as a quality measurement with a "
    "score between 0 and 1. The metrics are assigned to the four FAIR dimensions "
    "(Findability, Accessibility, Interoperability, Reusability) in the FAIRagro metric vocabulary, "
    "and the dimension score is the average of its metric scores. Because the tools use different metrics, "
    "their results are shown side by side and are not meant to be merged into a single number."
)

st.subheader("FAIR Maturity Evaluation Service")
st.write(
    "The [FAIR Maturity Evaluation Service](https://fairsharing.github.io/FAIR-Evaluator-FrontEnd/) is an online platform developed by the FAIRmetrics and FAIRsharing groups. "
    "It provides resources and guidelines to assess the FAIRness—Findability, Accessibility, Interoperability, and Reusability—of digital resources. "
    "The service was significantly supported by the DBCLS BioHackathon series, during which much of the back-end code was prototyped. "
)

st.subheader("F-UJI Automated FAIR Data Assessment Tool")
st.write(
    "[F-UJI](https://www.f-uji.net/) is a web service designed to programmatically assess the FAIRness of research data objects at the dataset level. "
    "Developed under the umbrella of the FAIRsFAIR project, F-UJI evaluates datasets based on the FAIRsFAIR Data Object Assessment Metrics. "
    "Users can input a dataset's persistent identifier or URL to receive an assessment of how well it aligns with FAIR principles. "
    "This tool aids researchers in identifying areas where their datasets meet FAIR criteria and highlights aspects that may require improvement."
)

st.subheader("FAIR-Checker")
st.write(
    "[FAIR-Checker](https://fair-checker.france-bioinformatique.fr/) is a web tool and API for assessing how FAIR "
    "digital resources are, and for helping data providers improve the quality of their resources. "
    "It is developed by the interoperability working group of the French Institute for Bioinformatics (IFB), "
    "the French node of ELIXIR, and is open source under the MIT license. "
    "FAIR-Checker works on the metadata of a resource, with a focus on Semantic Web and Knowledge Graph standards: "
    "it looks for structured RDF metadata, checks whether the terms used are known in major ontology registries, "
    "and tests for licence, provenance and access-rights information. "
    "Several of its metrics have a weak and a strong level; this app rescales the raw results to a 0–1 range "
    "so that they can be compared with the other tools. "
    "For details, see the "
    "[FAIR-Checker about page](https://fair-checker.france-bioinformatique.fr/about) and the publication "
    "by Gaignard et al. (2023) in the Journal of Biomedical Semantics "
    "([doi:10.1186/s13326-023-00289-5](https://doi.org/10.1186/s13326-023-00289-5))."
)

st.subheader("Contact")
st.write("For more information, visit the [FAIRagro GitHub repository](https://github.com/fairagro/fair-er).")

# Footer
st.markdown("---")