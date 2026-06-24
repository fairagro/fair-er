import streamlit as st
import pandas as pd
from SPARQLWrapper import SPARQLWrapper, JSON
from query_templates import FAIR_QUERIES, RDI_QUERIES
from dotenv import load_dotenv
import os
from config import testing

# Load environment variables
load_dotenv()

# Retrieve Fuseki base URL from environment variables
if not testing:
    fuseki_base_url = os.getenv("FUSEKI_BASE_URL")# Retrieve Fuseki base URL from environment variables
else:
    fuseki_base_url = os.getenv("FUSEKI_LOCAL")# for testing

# Define SPARQL endpoints
endpoints = {
    "FAIR_Metrics": f"{fuseki_base_url}/FAIR_Metrics/sparql",
    "e!DAL": f"{fuseki_base_url}/e!dal/sparql",
    "BonaRes": f"{fuseki_base_url}/bonares/sparql",
    "openagrar": f"{fuseki_base_url}/openagrar/sparql",
    "nsfi": f"{fuseki_base_url}/nsfi/sparql",
    "publisso": f"{fuseki_base_url}/publisso/sparql",
    "demo": f"{fuseki_base_url}/demo/sparql",
}

# Streamlit UI components
st.title("SPARQL Explorer")

# Dropdown for selecting the endpoint
selected_endpoint = st.selectbox("Select SPARQL Endpoint:", list(endpoints.keys()))

# Load correct query templates based on the selected endpoint
template_queries = FAIR_QUERIES if selected_endpoint == "FAIR_Metrics" else RDI_QUERIES

# Use the selected endpoint for queries
SPARQL_ENDPOINT = endpoints[selected_endpoint]

st.write(f"Querying endpoint: {SPARQL_ENDPOINT}")

# Dropdown menu for selecting a template query
template_names = list(template_queries.keys())
selected_template = st.selectbox("Choose a template query:", template_names)

# Retrieve the selected template query
default_query = template_queries[selected_template]

# Full-width query input box
user_query = st.text_area("Enter your SPARQL query here:", value=default_query, height=500)

# Initialize session state for query results and page number
if "query_results" not in st.session_state:
    st.session_state.query_results = None
if "page_number" not in st.session_state:
    st.session_state.page_number = 1

# Function to execute SPARQL queries
def execute_sparql_query(query: str) -> pd.DataFrame:
    sparql = SPARQLWrapper(SPARQL_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    cols = results["head"]["vars"]
    rows = [
        {col: result.get(col, {}).get("value", None) for col in cols}
        for result in results["results"]["bindings"]
    ]
    return pd.DataFrame(rows, columns=cols)

# Execute Query button placed immediately after the query input
execute_query = st.button("Execute Query")

# Placeholder for displaying query results
results_placeholder = st.empty()

# Execute the query if the button is clicked
if execute_query:
    if user_query.strip():
        try:
            # Run the query and store results in session state
            st.session_state.query_results = execute_sparql_query(user_query)
            st.session_state.page_number = 1  # Reset to first page on new query
        except Exception as e:
            st.error(f"An error occurred: {e}")

# Display query results if available
if st.session_state.query_results is not None:
    df = st.session_state.query_results
    total_rows = len(df)
    rows_per_page = 500  # Adjust as needed

    if total_rows > rows_per_page:
        # Page selector, persistent with session state
        max_pages = (total_rows // rows_per_page) + 1
        st.session_state.page_number = st.number_input(
            "Page number", min_value=1, max_value=max_pages, value=st.session_state.page_number, step=1
        )

        # Paginate results
        start_row = (st.session_state.page_number - 1) * rows_per_page
        end_row = start_row + rows_per_page
        df_paginated = df.iloc[start_row:end_row]

        results_placeholder.dataframe(df_paginated, use_container_width=True)
    else:
        # Display full results if small
        results_placeholder.dataframe(df, use_container_width=True)

# Footer
st.markdown("---")
