"""
Parse defined metrics on redis application. To populate the metrics.json, get the desidered
metric from the cAdvisor stats field (you can do this by checking json structure that the
cAdivsor returns). You should check the json key names needed for this metric to get to the
actual value that will be used for checking the threshold.
"""
# import os, requests

import concurrent.futures

import json
import logging
from urllib.request import urlopen

import boto3

CONTAINER_NAME = "redis"
DEFAULT_THRESHOLD = 3
DEFAULT_WINDOW = 5


def check_value(container_info: dict, metric: dict):
    """TO-DO"""
    logging.info("Collecting metric %s/%s", metric.name, metric.key)
    metric_info = {}
    try:
        info = container_info.values()
        if CONTAINER_NAME in info.get("aliases"):
            stats = info.get("stats")

            metric_value = stats.get(metric.name)
            # Not elegant (probably there's a better way of doing it)
            for key in metric.keys:
                metric_value = metric_value.get(key)

            metric_info["value"] = metric_value
            metric_info["timestamp"] = stats.get("timestamp")
        else:
            logging.info(
                "cAdvisor doesn't have information for %s container", CONTAINER_NAME
            )

        return metric_info

    except Exception as e:
        logging.error("Failed to collect metric. Cause: %s", e)

        return None


def collect_metrics(container_info: dict, metrics: dict):
    """
    For each metric defined in the metrics.json, collect its values
    from the cAdvisor collected container information
    """
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as executor:
        results = [
            executor.submit(check_value, container_info, metric) for metric in metrics
        ]

        for future in concurrent.futures.as_completed(results):
            result = future.result()
            print(result)


def main():
    """Main function"""
    logging.info("Parsing metrics for container: %s", CONTAINER_NAME)

    parsing_url = f"http://localhost:8080/api/v1.3/docker/{CONTAINER_NAME}"
    response = urlopen(parsing_url)
    container_info = json.loads(response.read())

    with open("metrics.json", encoding="utf-8") as f:
        metrics = f.read()

    collect_metrics(container_info, metrics)


if __name__ == "__main__":
    main()
