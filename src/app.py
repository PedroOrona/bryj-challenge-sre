"""
Application wich parses metrics, trigger alarms and also make specific actions depending on the
target metric.

For specific metrics, please update the TargetMetric data class. Instructions are the following:

1. Check the json structure for the desidered metric in the cAdvisor response (you can collect the
URL response by acessing the CADVISOR_URL environment or running this application in Debug mode).
The metric values will be inside the 'stats' key.

2. Check the json key names needed for this metric to get to the actual value that will be used
for checking the threshold. So, for example, to get get the CPU Usage Total, you can see in the
stats field that you have to access, 'cpu', 'usage' and 'total', so you should define all these
3 keys in the 'keys' field for the MetricConfig.

For more information about how to run the application, read the repository README.
"""
import argparse
import asyncio
import concurrent.futures
import os
import time

import json
import logging

from urllib.request import urlopen
from dataclasses import asdict
from dotenv import load_dotenv
from slack_sdk.webhook.async_client import AsyncWebhookClient

import boto3
from metrics import TargetMetric, MetricInfo, MetricConfig


load_dotenv()

AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION")
AUTO_SCALING_GROUP_NAME = os.getenv("AUTO_SCALING_GROUP_NAME")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
CADVISOR_URL = os.getenv("CADVISOR_URL")
METRIC_VALUES_FILENAME = os.getenv("METRIC_VALUES_FILENAME")
METRICS_CONFIG_FILENAME = os.getenv("METRICS_CONFIG_FILENAME")
CONTAINER_NAME = os.getenv("CONTAINER_NAME")

MAX_METRICS = int(os.getenv("MAX_METRICS"))
MINUTE_PERIOD = float(os.getenv("MINUTE_PERIOD"))

# TODO: Define boto3 Session
asg_client = boto3.client("autoscaling", region_name=AWS_DEFAULT_REGION)
s3_client = boto3.client("s3", region_name=AWS_DEFAULT_REGION)

logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser()
parser.add_argument(
    "--upload",
    dest="upload",
    help="Uploaded to a S3 Bucket when alarm is triggered (default is False)",
    default=False,
)
args = parser.parse_args()


async def send_message_via_webhook(metric_name: str, metric_value: int):
    """
    Execute an specific action depending of the alarm triggered.

    Parameters:
        metric_name (str): Metric name that will appear in the alarm message text.
        metric_value (int): Metric name that will appear in the alarm message text.
    """
    try:
        webhook = AsyncWebhookClient(SLACK_WEBHOOK_URL)
        await webhook.send(
            blocks=[
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Alarm Triggered"},
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Alarm for metric {metric_name} triggered now. Current value is {metric_value}.",
                    },
                },
            ]
        )
    except Exception as e:
        logging.error("Failed to send alert to Slack Channel. Cause: %s.", e)
        raise e


def alarm_action(metric: MetricConfig, metric_info: MetricInfo):
    """
    Execute an specific action depending of the alarm triggered.

    Parameters:
        metric (MetricConfig):
            Dictionary containing information about how to collect and evaluate an specific metric.
        metric_info (dict):
            MetricInfo object with information about collected metric.

    Returns:
        response (Any): Response got from applying the requested action.
    """

    logging.info("Alarm triggered for metric %s", metric.name)

    if args.upload:
        try:
            s3_client.upload_file(
                METRIC_VALUES_FILENAME, S3_BUCKET_NAME, METRIC_VALUES_FILENAME
            )
            logging.info(
                "Uploaded metric_values.json file to S3 Bucket %s.", S3_BUCKET_NAME
            )
        except Exception as e:
            logging.error(
                "Failed to upload metric_values.json to S3 Bucket %s. Cause: %s.",
                S3_BUCKET_NAME,
                e,
            )
            raise e

    asyncio.run(send_message_via_webhook(metric.name, metric_info.value))

    # Add here more conditions and actions for specific metric names
    if metric.name == "cpu_usage_total":
        try:
            response = asg_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[AUTO_SCALING_GROUP_NAME]
            )
            current_desired = response.get("AutoScalingGroups")[0].get(
                "DesiredCapacity"
            )

            if metric.compare == "bigger":
                desired_capacity = current_desired + 1
            elif current_desired != 0:
                desired_capacity = current_desired - 1

            response = asg_client.set_desired_capacity(
                AutoScalingGroupName=AUTO_SCALING_GROUP_NAME,
                DesiredCapacity=desired_capacity,
                HonorCooldown=True,
            )
            logging.info(
                "Auto Scaling Group %s updated. New desired capacity set to %s.",
                AUTO_SCALING_GROUP_NAME,
                desired_capacity,
            )

            return response

        except Exception as e:
            logging.error(
                "Failed to scale ASG %s. Cause: %s.", AUTO_SCALING_GROUP_NAME, e
            )
            return None


def check_value(container_info: dict, metric: MetricConfig):
    """
    Parse cAdvisor response for requested container and return
    metric informations like current value and timestamp.
    Also checks if the metric alarm should be trigger.

    Parameters:
        container_info (dict):
            Dictionary with information about requested container collected by cAdivsor.
        metric (MetricConfig):
            MetricConfig oject containing information about how to collect and evaluate an specific metric.

    Returns:
        metric (dict):
            Dictionary containing information about how to collect and evaluate an specific metric.
        metric_info (MetricInfo):
            Object of MetricInfo data class containing information about the requested metric.
    """
    metric_name = metric.name
    metric_threshold = metric.threshold
    metric_compare = metric.compare

    logging.info("Collecting metric %s...", metric_name)
    metric_info = {}
    try:
        info = list(container_info.values())[0]
        if CONTAINER_NAME in info.get("aliases"):
            # Always get the most recent metrics status
            # TODO: Check if value collected is a new one
            stats = info.get("stats")[-1]
            metric_value = stats.get(metric.area)

            # Not elegant (probably there's a better way of doing it)
            for key in metric.keys:
                metric_value = metric_value.get(key)

            metric_info = MetricInfo(
                value=metric_value, timestamp=stats.get("timestamp")
            )

            logging.info(
                "Metric collected! %s: %s (%s)",
                metric_name,
                metric_info.value,
                metric_info.timestamp,
            )

            if metric_compare == "bigger" and metric_value > metric_threshold:
                metric_info.set_alarm()
            elif metric_compare == "lower" and metric_value < metric_threshold:
                metric_info.set_alarm()

            if metric_info.alarm:
                logging.info(
                    "Metric value %s than threshold (%s) for metric %s.",
                    metric_compare,
                    metric_threshold,
                    metric_name,
                )

        else:
            logging.info(
                "cAdvisor doesn't have information for %s container.", CONTAINER_NAME
            )

        return metric, metric_info

    except Exception as e:
        logging.error("Failed to collect metric. Cause: %s.", e)

        return None


def collect_metrics(
    container_info: dict, metrics: list[MetricConfig], alarm: dict = None
):
    """
    For each metric defined in the metrics.json, collect its values
    using information provided by cAdvisor, save them into the
    METRIC_VALUES_FILENAME json file and returns the necessary
    information about the alarm status. It will look for the
    container specified in the CONTAINER_NAME environment variable.

    Parameters:
        container_info (dict):
            Dictionary with information about requested container collected by cAdivsor.
        metrics (list[MetricConfig]):
            List of metric configurations defined in the TargetMetric data class.
        alarm (dict):
            Dictionary containing information about metric alarm. Keys are 'status' and 'period'.
            Default value is None.

    Returns:
        alarm (dict):
            Dictionary containing information about metric alarm. Keys are 'status' and 'period'.
    """
    max_workers = min(len(metrics), MAX_METRICS)

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = [
            executor.submit(check_value, container_info, metric) for metric in metrics
        ]

        for future in concurrent.futures.as_completed(results):
            metric, metric_info = future.result()
            metric_name = metric.name
            metric_alarm = metric_info.alarm

            if alarm is None:
                alarm = {}

            if metric_alarm and not alarm.get(metric_name):
                alarm[metric_name] = {"status": metric_alarm, "period": 0}
            elif metric_alarm and alarm[metric_name]["status"]:
                alarm[metric_name]["period"] += MINUTE_PERIOD
            elif metric_alarm:
                alarm[metric_name] = {"status": True, "period": MINUTE_PERIOD}
            else:
                alarm[metric_name] = {"status": False, "period": 0}

            if alarm[metric_name].get("period") >= metric.window:
                response = alarm_action(metric, metric_info)
                if response:
                    alarm[metric_name] = {"status": False, "period": 0}

            metric_info_dict = json.loads(json.dumps(asdict(metric_info)))
            if os.path.exists(METRIC_VALUES_FILENAME):
                with open(METRIC_VALUES_FILENAME, "r", encoding="utf-8") as f:
                    metric_values = json.load(f)

                metric_values[metric_name].append(metric_info_dict)
            else:
                logging.info(
                    "Creating new JSON file called %s for saving metric values.",
                    METRIC_VALUES_FILENAME,
                )
                metric_values = {metric_name: [metric_info_dict]}

            # overwrite/create file
            with open(METRIC_VALUES_FILENAME, "w", encoding="utf-8") as f:
                json.dump(metric_values, f, indent=3)

    return alarm


def main():
    """Main function"""
    logging.info("Parsing metrics for container: %s.", CONTAINER_NAME)

    parsing_url = f"{CADVISOR_URL}/{CONTAINER_NAME}"
    with urlopen(parsing_url) as u:
        response = u.read()
    container_info = json.loads(response)

    target_metrics = TargetMetric()
    metrics = target_metrics.metrics

    if os.path.exists(METRIC_VALUES_FILENAME):
        os.remove(METRIC_VALUES_FILENAME)

    alarm = {}
    while True:
        alarm = collect_metrics(container_info, metrics, alarm)
        time.sleep(MINUTE_PERIOD * 60)


if __name__ == "__main__":
    main()
