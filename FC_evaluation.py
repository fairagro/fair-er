import os
import json
from dotenv import load_dotenv
import requests
from typing import Dict, Any, List
from requests.exceptions import ConnectTimeout

# Load dotenv
load_dotenv()

FAIRCHECKER_URL = os.getenv("FAIRCHECKER_URL", "https://fair-checker.france-bioinformatique.fr/api/check/metrics_all")

headers = {
    'accept': '*/*',
    'Content-Type': 'application/json'
}

# Example FUJI evaluation results
fc_evaluation_result_example = {
    'https://fair-checker.france-bioinformatique.fr/data/R1.3': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/I2': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/F2B': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/R1.2': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/F1B': 0.0,
    'https://fair-checker.france-bioinformatique.fr/data/A1.2': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/F1A': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/I3': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/A1.1': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/R1.1': 1.0,
    'https://fair-checker.france-bioinformatique.fr/data/I1': 0.5,
    'https://fair-checker.france-bioinformatique.fr/data/F2A': 0.5
}


def fairchecker_evaluate_to_list(data_doi: str) -> Dict[str, float]:
    if not data_doi:
        raise ValueError("data_doi is required")

    checker_url = FAIRCHECKER_URL
    params = {"url": f"https://doi.org/{data_doi}"}

    print(f"Running FAIR-Checker evaluation for DOI {data_doi}")

    try:
        response = requests.get(
            checker_url,
            params=params,
            headers={"accept": "application/json"},
            timeout=30
        )
        response.raise_for_status()
    except ConnectTimeout:
        print(f"Request timed out when trying to connect to {checker_url}")
        raise RuntimeError("FAIR-Checker API is unreachable (timeout).")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        raise RuntimeError(f"FAIR-Checker API request failed for {data_doi}: {e}")

    if response.status_code == 200:
        print("Request successful!")
        parsed_response = response.json()
        # write_jsonld(parsed_response, data_doi)
        return map_fairchecker_to_metrics(parsed_response)
    else:
        print(f"Request failed with status code {response.status_code}")
        raise RuntimeError(f"FAIR-Checker API request failed with status {response.status_code}")


def map_fairchecker_to_metrics(data: List[dict]) -> Dict[str, float]:
    results: Dict[str, float] = {}

    for entry in data:
        metric_list = entry.get("http://www.w3.org/ns/dqv#isMeasurementOf", [])
        value_list = entry.get("http://www.w3.org/ns/dqv#value", [])

        if not metric_list or not value_list:
            continue

        metric_id = metric_list[0].get("@id")
        value_raw = value_list[0].get("@value")

        if metric_id is None or value_raw is None:
            continue

        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            continue

        results[metric_id] = value / 2
    print(results)
    return results


def write_jsonld(data: Any, doi: str) -> None:
    safe = doi.replace("/", "_")
    path = f"output/{safe}.jsonld"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    fairchecker_evaluate_to_list("10.20387/BONARES-42HW-3J53")
