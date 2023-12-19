"""
Parse defined metrics on redis application. To populate the metrics.json, get the desidered
metric from the cAdvisor stats field (you can do this by checking json structure that the
cAdivsor returns). You should check the json key names needed for this metric to get to the
actual value that will be used for checking the threshold.
"""
import concurrent.futures
import os
import time

import json
import logging
from urllib.request import urlopen

import boto3

AWS_DEFAULT_REGION = "eu-west-1"
ASG_NAME = "bryj-app"

VALUES_FILE_NAME = "metric_values.json"
CONTAINER_NAME = "redis"

DEFAULT_WINDOW = 4
MINUTE_PERIOD = 2
MAX_METRICS = 10

asg_client = boto3.client("autoscaling", region_name=AWS_DEFAULT_REGION)
s3_client = boto3.client("s3", region_name=AWS_DEFAULT_REGION)

logging.basicConfig(level=logging.INFO)


def alarm_action(metric_name: str, upload: bool = False):
    """Execute an specific action depending of the alarm triggered"""
    logging.info("Alarm triggered for metric %s", metric_name)

    # Add more conditions and actions for specific metric names
    if metric_name == "cpu_usage_total":
        try:
            response = asg_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[ASG_NAME]
            )
            current_desired = response.get("AutoScalingGroups")[0].get(
                "DesiredCapacity"
            )

            if condition == "bigger":
                desired_capacity = current_desired + 1
            elif current_desired != 0:
                desired_capacity = current_desired - 1

            response = asg_client.set_desired_capacity(
                AutoScalingGroupName=ASG_NAME,
                DesiredCapacity=desired_capacity,
                HonorCooldown=True,
            )
            logging.info(
                "Auto Scaling Group %s updated. New desired capacity set to %s",
                ASG_NAME,
                desired_capacity,
            )
        except Exception as e:
            logging.error("Failed to scale ASG %s. Cause: %s", ASG_NAME, e)


def check_value(container_info: dict, metric: dict):
    """TO-DO"""
    metric_name = metric.get("name")
    metric_threshold = metric.get("threshold")
    metric_compare = metric.get("compare")

    logging.info("Collecting metric %s...", metric_name)
    metric_info = {}
    try:
        info = list(container_info.values())[0]
        if CONTAINER_NAME in info.get("aliases"):
            # Always get the most recent metrics status
            stats = info.get("stats")[-1]
            metric_value = stats.get(metric.get("area"))

            # Not elegant (probably there's a better way of doing it)
            for key in metric.get("keys"):
                metric_value = metric_value.get(key)

            metric_info["name"] = metric_name
            metric_info["value"] = metric_value
            metric_info["alarm"] = False
            metric_info["window"] = metric.get("window", DEFAULT_WINDOW)
            metric_info["timestamp"] = stats.get("timestamp")
            metric_info["alarm"] = False

            if metric_compare == "bigger" and metric_value > metric_threshold:
                metric_info["alarm"] = True
            elif metric_compare == "lower" and metric_value < metric_threshold:
                metric_info["alarm"] = True

            if metric_info["alarm"]:
                logging.info(
                    "Metric value %s than threshold (%s) for metric %s.",
                    metric_compare,
                    metric_threshold,
                    metric_name,
                )

            logging.info(
                "Metric collected! %s: %s (%s)",
                metric_info["name"],
                metric_info["value"],
                metric_info["timestamp"],
            )
        else:
            logging.info(
                "cAdvisor doesn't have information for %s container", CONTAINER_NAME
            )

        return metric_info

    except Exception as e:
        logging.error("Failed to collect metric. Cause: %s", e)

        return None


def collect_metrics(container_info: dict, metrics: list[dict], alarm: dict):
    """
    For each metric defined in the metrics.json, collect its values
    from the cAdvisor collected container information
    """
    # Condition to not allow a very big number of metrics. This can be changed by
    # simply updating MAX_METRICS global variable
    max_workers = len(metrics)
    if max_workers > MAX_METRICS:
        max_workers = MAX_METRICS

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = [
            executor.submit(check_value, container_info, metric) for metric in metrics
        ]

        for future in concurrent.futures.as_completed(results):
            result = future.result()
            # Make the result have only the metric value and timestamp to save to the json file
            metric_name = result.pop("name")

            if result.get("alarm") and not alarm.get(metric_name):
                alarm[metric_name] = {"status": result.get("alarm"), "period": 0}
            elif result.get("alarm") and alarm[metric_name]["status"]:
                alarm[metric_name]["period"] += MINUTE_PERIOD
            elif result.get("alarm"):
                alarm[metric_name] = {"status": True, "period": MINUTE_PERIOD}
            else:
                alarm[metric_name] = {"status": False, "period": 0}

            if alarm[metric_name].get("period") >= result.get("window"):
                alarm_action(metric_name)

            if os.path.exists(VALUES_FILE_NAME):
                with open(VALUES_FILE_NAME, "r", encoding="utf-8") as f:
                    metric_values = json.load(f)

                metric_values[metric_name].append(result)
            else:
                logging.info(
                    "Creating new JSON file called %s for saving metric values.",
                    VALUES_FILE_NAME,
                )
                metric_values = {metric_name: [result]}

            # overwrite/create file
            with open(VALUES_FILE_NAME, "w", encoding="utf-8") as f:
                json.dump(metric_values, f)

    return alarm


def main():
    """Main function"""
    logging.info("Parsing metrics for container: %s", CONTAINER_NAME)

    parsing_url = f"http://localhost:8080/api/v1.3/docker/{CONTAINER_NAME}"
    response = urlopen(parsing_url)
    container_info = json.loads(response.read())

    with open("src/metrics.json", encoding="utf-8") as f:
        metrics = json.load(f)
    metrics = metrics.get("metrics")

    alarm = {}
    while True:
        alarm = collect_metrics(container_info, metrics, alarm)
        time.sleep(MINUTE_PERIOD * 60)


if __name__ == "__main__":
    main()
