# Use the official Python image as the base image
FROM python:3.14-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements_docker.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements_docker.txt

# Copy specific application files into the container
COPY main.py .
COPY FES_evaluation.py .
COPY FUJI_evaluation.py .
COPY doi_to_dqv.py .
COPY doi_info_fetcher.py .
COPY metric_mappings.py .
COPY query_templates.py .
COPY rdf_utils.py .
COPY rdf_cache.py .

# Copy directories into the container
COPY DataQualityVocabulary/ ./DataQualityVocabulary/
COPY pages/ ./pages/

# Copy the .streamlit configuration directory
COPY .streamlit/ /app/.streamlit/

# Set environment variable to unbuffer Python output
ENV PYTHONUNBUFFERED=1

# Expose the port that Streamlit uses
EXPOSE 8501

# Run the Streamlit application
ENV BASE_URL_PATH=""
CMD ["sh", "-c", "streamlit run main.py --server.port=8501 --server.address=0.0.0.0 ${BASE_URL_PATH:+--server.baseUrlPath=$BASE_URL_PATH}"]

