"""Data class to manipulate metrics information"""
import os
from dataclasses import dataclass
from typing import Any, List
from dotenv import load_dotenv

load_dotenv()

DEFAULT_WINDOW = int(os.getenv("DEFAULT_WINDOW"))


@dataclass
class MetricInfo:
    """Actual state of metric"""

    value: Any
    timestamp: str
    alarm: bool = False

    def set_alarm(self):
        """Set alarm metric to True"""
        self.alarm = True


@dataclass
class MetricConfig:
    """Metric configuration that will be used to parse cAdvisor response"""

    # TODO: Validate that 'compare' has a valide value
    name: str
    keys: list
    threshold: Any
    compare: str
    window: int = DEFAULT_WINDOW


@dataclass
class TargetMetric:
    """List of MetricConfig objects containing all the metrics that the app will monitor"""

    metrics: List[MetricConfig] = None

    def __post_init__(self):
        """Define all the metrics that you want to monitor"""
        self.metrics = [
            MetricConfig(
                name="cpu_usage_total",
                keys=["cpu", "usage", "total"],
                threshold=500,
                compare="bigger",
                window=3,
            )
        ]
