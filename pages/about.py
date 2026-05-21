import streamlit as st

# Main content of your about.py
st.title("About This App")
st.write(
    "This application is designed to provide tools and resources for FAIR data evaluation. "
    "It supports agricultural research by enabling users to assess and improve the FAIRness of their data."
)

st.subheader("Features")
st.markdown(
    """
    - **FAIR Evaluation**: Assess the FAIRness of datasets.
    - **SPARQL Explorer**: Query and explore linked data.
    - **GitHub Repository**: Access the source code and documentation.
    """
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

st.subheader("Contact")
st.write("For more information, visit the [FAIRagro GitHub repository](https://github.com/fairagro/fair-er).")

# Footer
st.markdown("---")
