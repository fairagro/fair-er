import streamlit as st

st.title("FAIR Evaluation Repository")

# GitHub Repository Link
repo_url = "https://github.com/fairagro/fair-er"
st.markdown(f"[🔗 Visit the FAIR Evaluation Repository on GitHub]({repo_url})")

# Additional Information
st.subheader("About the Repository")
st.write(
    "The FAIR Evaluation Repository is part of the FAIRagro initiative and provides tools and resources for FAIR data assessment. "
    "It contains evaluation methods, guidelines, and implementations to support FAIR principles in agricultural research."
)

# Footer
st.markdown("---")
