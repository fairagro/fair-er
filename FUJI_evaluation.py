import os
import json
from dotenv import load_dotenv
import requests
import csv
from typing import Dict, Any, Optional
from requests.exceptions import ConnectTimeout
from config import fuji_testing

# Load dotenv
load_dotenv()

USE_FUJI_AUTH = os.getenv("USE_FUJI_AUTH", "false").lower() == "true"
USERNAME = os.getenv("FUJI_USERNAME")
PASSWORD = os.getenv("FUJI_PASSWORD")

fuji_auth: Optional[tuple[str, str]] = (USERNAME, PASSWORD) if USE_FUJI_AUTH else None

if fuji_testing:
    FUJI_URL = os.getenv("FUJI_LOCAL")
else:
    FUJI_URL = os.getenv("FUJI_URL")
if not FUJI_URL:
    raise RuntimeError("FUJI_URL is not set in .env file")
headers = {
    'accept': '*/*',
    'Content-Type': 'application/json'
}

data_example = {
    "object_identifier": "10.20387/bonares-zyd4-w9c2",
    "test_debug": True,
    "metadata_service_endpoint": "",
    "metadata_service_type": "oai_pmh",
    "use_datacite": True,
    "use_github": False,
    "metric_version": "metrics_v0.8"
}

fuji_evaluation_result_example_v05 = {
    'FsF-F1-01D-1': 1.0, 'FsF-F1-01D-2': 0.0,
    'FsF-F1-02D-1': 0.5, 'FsF-F1-02D-2': 0.5,
    'FsF-F2-01M-1': 0.5, 'FsF-F2-01M-2': 0.5, 'FsF-F2-01M-3': 0.0,
    'FsF-F3-01M-1': 0.0, 'FsF-F3-01M-2': 0.0,
    'FsF-F4-01M-1': 0.0, 'FsF-F4-01M-2': 1.0,
    'FsF-A1-01M-1': 0.0, 'FsF-A1-01M-2': 0.0, 'FsF-A1-01M-3': 0.0,
    'FsF-A1-02M-1': 1.0,
    'FsF-A1-03D-1': 0.0,
    'FsF-I1-01M-1': 0.0, 'FsF-I1-01M-2': 1.0,
    'FsF-I2-01M-1': 0.0, 'FsF-I2-01M-2': 0.0,
    'FsF-I3-01M-1': 0.0, 'FsF-I3-01M-2': 0.0,
    'FsF-R1-01MD-1': 0.25, 'FsF-R1-01MD-1a': 0.25, 'FsF-R1-01MD-1b': 0.25,
    'FsF-R1-01MD-2': 0.25, 'FsF-R1-01MD-2a': 0.25, 'FsF-R1-01MD-2b': 0.25,
    'FsF-R1-01MD-3': 0.25, 'FsF-R1-01MD-4': 0.25,
    'FsF-R1.1-01M-1': 0.0, 'FsF-R1.1-01M-2': 0.0,
    'FsF-R1.2-01M-1': 1.0, 'FsF-R1.2-01M-2': 0.0,
    'FsF-R1.3-01M-1': 0.0, 'FsF-R1.3-01M-2': 0.0, 'FsF-R1.3-01M-3': 1.0,
    'FsF-R1.3-02D-1': 0.0, 'FsF-R1.3-02D-1a': 0.0, 'FsF-R1.3-02D-1b': 0.0, 'FsF-R1.3-02D-1c': 0.0
}

fuji_evaluation_result_example_v08 = {
    'FsF-F1-01MD-1': 1.0, 'FsF-F1-01MD-2': 0.0,
    'FsF-F1-02MD-1': 0.5, 'FsF-F1-02MD-2': 0.5, 'FsF-F1-02MD-4': 0.0, 'FsF-F1-02MD-5': 0.0,
    'FsF-F2-01M-2': 1.0, 'FsF-F2-01M-3': 0.0,
    'FsF-F3-01M-2': 0.0,
    'FsF-F4-01M-1': 0.0,
    'FsF-A1-01M-1': 0.0,
    'FsF-A1-02MD-1': 1.0, 'FsF-A1-02MD-2': 0.0,
    'FsF-A1.1-01MD-1': 1.0, 'FsF-A1.1-01MD-2': 0.0,
    'FsF-A1.2-01MD-1': 1.0, 'FsF-A1.2-01MD-2': 0.0,
    'FsF-I1-01M-1': 0.0, 'FsF-I1-01M-2': 1.0,
    'FsF-I2-01M-2': 0.0,
    'FsF-I3-01M-1': 0.0, 'FsF-I3-01M-2': 0.0,
    'FsF-R1-01M-1': 1.0, 'FsF-R1-01M-2': 0.0,
    'FsF-R1.1-01M-1': 0.0,
    'FsF-R1.2-01M-1': 1.0, 'FsF-R1.2-01M-2': 0.0,
    'FsF-R1.3-01M-1': 0.0, 'FsF-R1.3-01M-3': 1.0,
    'FsF-R1.3-02D-1': 0.0
}

# Standardmäßig wird die alte Version 0.5 verwendet (für Kompatibilität)
fuji_evaluation_result_example = fuji_evaluation_result_example_v08

# ------------------------------------------------------------
# Mapping für Version 0.5 (alt)
# ------------------------------------------------------------
def map_json_to_metrics_v05(json_input: Dict[str, Any]) -> Dict[str, float]:
    metric_test_mapping = {
        "FsF-F1-01D": ["FsF-F1-01D-1", "FsF-F1-01D-2"],
        "FsF-F1-02D": ["FsF-F1-02D-1", "FsF-F1-02D-2"],
        "FsF-F2-01M": ["FsF-F2-01M-1", "FsF-F2-01M-2", "FsF-F2-01M-3"],
        "FsF-F3-01M": ["FsF-F3-01M-1", "FsF-F3-01M-2"],
        "FsF-F4-01M": ["FsF-F4-01M-1", "FsF-F4-01M-2"],
        "FsF-A1-01M": ["FsF-A1-01M-1", "FsF-A1-01M-2", "FsF-A1-01M-3"],
        "FsF-A1-02M": ["FsF-A1-02M-1"],
        "FsF-A1-03D": ["FsF-A1-03D-1"],
        "FsF-I1-01M": ["FsF-I1-01M-1", "FsF-I1-01M-2"],
        "FsF-I2-01M": ["FsF-I2-01M-1", "FsF-I2-01M-2"],
        "FsF-I3-01M": ["FsF-I3-01M-1", "FsF-I3-01M-2"],
        "FsF-R1-01MD": ["FsF-R1-01MD-1", "FsF-R1-01MD-1a", "FsF-R1-01MD-1b", "FsF-R1-01MD-2", "FsF-R1-01MD-2a", "FsF-R1-01MD-2b", "FsF-R1-01MD-3", "FsF-R1-01MD-4"],
        "FsF-R1.1-01M": ["FsF-R1.1-01M-1", "FsF-R1.1-01M-2"],
        "FsF-R1.2-01M": ["FsF-R1.2-01M-1", "FsF-R1.2-01M-2"],
        "FsF-R1.3-01M": ["FsF-R1.3-01M-1", "FsF-R1.3-01M-2", "FsF-R1.3-01M-3"],
        "FsF-R1.3-02D": ["FsF-R1.3-02D-1", "FsF-R1.3-02D-1a", "FsF-R1.3-02D-1b", "FsF-R1.3-02D-1c"]
    }

    mapped_results = {}
    for result in json_input.get("results", []):
        metric_id = result["metric_identifier"]
        if metric_id in metric_test_mapping:
            for sub_metric in metric_test_mapping[metric_id]:
                score = result["score"]["earned"] / result["score"]["total"] if result["score"]["total"] > 0 else 0.0
                mapped_results[sub_metric] = score
    return mapped_results

# ------------------------------------------------------------
# Mapping für Version 0.8 (neu)
# ------------------------------------------------------------
def map_json_to_metrics_v08(json_input: Dict[str, Any]) -> Dict[str, float]:
    """
    Extrahiert die Punktzahlen für alle Sub-Tests aus einem F-UJI Ergebnis-JSON der Version 0.8.
    """
    # Mapping von Metrik-IDs zu ihren Sub-Test-IDs (basierend auf dem bereitgestellten v0.8-JSON)
    metric_test_mapping = {
        "FsF-F1-01MD": ["FsF-F1-01MD-1", "FsF-F1-01MD-2"],
        "FsF-F1-02MD": ["FsF-F1-02MD-1", "FsF-F1-02MD-2", "FsF-F1-02MD-4", "FsF-F1-02MD-5"],
        "FsF-F2-01M": ["FsF-F2-01M-2", "FsF-F2-01M-3"],
        "FsF-F3-01M": ["FsF-F3-01M-2"],
        "FsF-F4-01M": ["FsF-F4-01M-1"],
        "FsF-A1-01M": ["FsF-A1-01M-1"],
        "FsF-A1-02MD": ["FsF-A1-02MD-1", "FsF-A1-02MD-2"],
        "FsF-A1.1-01MD": ["FsF-A1.1-01MD-1", "FsF-A1.1-01MD-2"],
        "FsF-A1.2-01MD": ["FsF-A1.2-01MD-1", "FsF-A1.2-01MD-2"],
        "FsF-I1-01M": ["FsF-I1-01M-1", "FsF-I1-01M-2"],
        "FsF-I2-01M": ["FsF-I2-01M-2"],        # Test -1 hat total=0, wird ignoriert
        "FsF-I3-01M": ["FsF-I3-01M-1", "FsF-I3-01M-2"],
        "FsF-R1-01M": ["FsF-R1-01M-1", "FsF-R1-01M-2"],
        "FsF-R1.1-01M": ["FsF-R1.1-01M-1"],
        "FsF-R1.2-01M": ["FsF-R1.2-01M-1", "FsF-R1.2-01M-2"],
        "FsF-R1.3-01M": ["FsF-R1.3-01M-1", "FsF-R1.3-01M-3"],
        "FsF-R1.3-02D": ["FsF-R1.3-02D-1"],
    }

    mapped_results = {}
    for result in json_input.get("results", []):
        metric_id = result["metric_identifier"]
        if metric_id in metric_test_mapping:
            expected_subtests = metric_test_mapping[metric_id]
            # Sub-Test-Daten aus metric_tests extrahieren
            for sub_test_id in expected_subtests:
                sub_test_data = result.get("metric_tests", {}).get(sub_test_id)
                if sub_test_data:
                    earned = sub_test_data["metric_test_score"]["earned"]
                    total = sub_test_data["metric_test_score"]["total"]
                    score = earned / total if total > 0 else 0.0
                    mapped_results[sub_test_id] = score
                else:
                    # Sub-Test nicht vorhanden (z.B. weil nicht ausgeführt) -> 0 Punkte
                    mapped_results[sub_test_id] = 0.0
    return mapped_results

# ------------------------------------------------------------
# Dispatcher: wählt automatisch die richtige Version anhand des Feldes "metric_version"
# ------------------------------------------------------------
def map_json_to_metrics(json_input: Dict[str, Any]) -> Dict[str, float]:
    metric_version = json_input.get("metric_version", "0.5")
    # Erweiterte Erkennung: sowohl "0.8" als auch "metrics_v0.8"
    if metric_version in ("0.8", "metrics_v0.8"):
        return map_json_to_metrics_v08(json_input)
    else:
        return map_json_to_metrics_v05(json_input)

# ------------------------------------------------------------
# Die übrigen Funktionen (get_result_score, write_result_to_csv, evaluate, fuji_evaluate_to_list) bleiben fast identisch.
# Einzige Anpassung: fuji_evaluate_to_list verwendet jetzt den Dispatcher.
# ------------------------------------------------------------
def get_result_score(name_of_fuji_result_json: str = "fuji_result.json") -> Dict[str, float]:
    with open(name_of_fuji_result_json, "r", encoding="utf-8") as file:
        json_data = json.load(file)
        score_percent = json_data["summary"]["score_percent"]
        object_identifier = json_data["request"]["object_identifier"]
        # write_result_to_csv(object_identifier, score_percent)  # ggf. auskommentiert
        return score_percent

def write_result_to_csv(object_identifier, score_percent):
    with open("fuji_result.csv", "w", newline='', encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=';')
        writer.writerow(["Object Identifier"] + list(score_percent.keys()))
        formatted_scores = [f'{score:.2f}' for score in score_percent.values()]
        writer.writerow([object_identifier] + formatted_scores)

def evaluate(data_doi=None):
    data = data_example.copy()
    if data_doi:
        data["object_identifier"] = data_doi
    print(f"running fuji evaluation for {data}")

    try:
        response = requests.post(FUJI_URL, json=data, headers=headers, auth=fuji_auth, timeout=30)
        response.raise_for_status()
    except ConnectTimeout:
        print(f"Request timed out when trying to connect to {FUJI_URL}")
        return
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return

    if response.status_code == 200:
        print("Request successful!")
        parsed_response = json.loads(response.text)
        with open('fuji_result.json', 'w+', encoding="utf-8") as file:
            file.write(json.dumps(parsed_response, indent=4))
            print("Result saved to 'fuji_result.json'")
    else:
        print(f"Request failed with status code {response.status_code}")
        print(response.text)

def fuji_evaluate_to_list(data_doi=None) -> Dict[str, float]:
    data = data_example.copy()
    if data_doi:
        data["object_identifier"] = data_doi
    print(f"Running F-UJI evaluation for {data}")

    # Debug: Zeige gesendeten Request-Body
    print("REQUEST BODY (sending):", json.dumps(data, indent=2))

    try:
        response = requests.post(FUJI_URL, json=data, headers=headers, auth=fuji_auth, timeout=30)
        response.raise_for_status()
    except ConnectTimeout:
        print(f"Request timed out when trying to connect to {FUJI_URL}")
        raise RuntimeError("FUJI API is unreachable (timeout).")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        raise RuntimeError(f"FUJI API request failed: {e}")

    if response.status_code == 200:
        print("Request successful!")
        parsed_response = response.json()
        # Debug: Zeige die ersten Felder der Antwort
        print("RESPONSE metric_version:", parsed_response.get("metric_version"))
        print("RESPONSE software_version:", parsed_response.get("software_version"))
        # Zeige die ersten paar Ergebnis-Metriken
        results = parsed_response.get("results", [])
        if results:
            first_result = results[0]
            print("First result metric_identifier:", first_result.get("metric_identifier"))
            print("First result test_status:", first_result.get("test_status"))
            metric_tests = first_result.get("metric_tests", {})
            print("Sample metric_test keys:", list(metric_tests.keys())[:3])
        else:
            print("No results in response")

        # Verwende den Dispatcher, um automatisch die korrekte Version zu wählen
        return map_json_to_metrics(parsed_response)
    else:
        print(f"Request failed with status code {response.status_code}")
        raise RuntimeError(f"FUJI API request failed with status {response.status_code}")

def example_fuji_results() -> Any:
    file_path = "output/examples/FUJI_10.20387_bonares-1ttx-ng98.json"
    with open(file_path, 'r', encoding='utf-8') as file:
        parsed_response = json.load(file)
    return map_json_to_metrics(parsed_response)

if __name__ == "__main__":
    # Test
    scores = fuji_evaluate_to_list("10.20387/bonares-jmqh-hzbe")
    for metric, score in scores.items():
        print(f"{metric}: {score}")