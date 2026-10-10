from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "warning", "info"]


class Signal(BaseModel):
    """A single symptom observed in the cluster (unhealthy pod, warning event, alert)."""

    source: Literal["pod", "event", "alert"]
    namespace: str | None = None
    resource: str
    reason: str
    message: str = ""
    count: int = Field(default=1, ge=1)


class Finding(BaseModel):
    resource: str
    severity: Severity
    category: str
    root_cause: str
    remediation: list[str]


class Report(BaseModel):
    summary: str
    findings: list[Finding]
    engine: Literal["gemini", "rules"]


class AnalyzeRequest(BaseModel):
    signals: list[Signal] = Field(min_length=1, max_length=200)


class AlertmanagerAlert(BaseModel):
    status: str
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}


class AlertmanagerWebhook(BaseModel):
    """Subset of the Alertmanager webhook payload that the analyzer needs."""

    alerts: list[AlertmanagerAlert]

    def to_signals(self) -> list[Signal]:
        return [
            Signal(
                source="alert",
                namespace=alert.labels.get("namespace"),
                resource=alert.labels.get("pod") or alert.labels.get("deployment") or "cluster",
                reason=alert.labels.get("alertname", "UnknownAlert"),
                message=alert.annotations.get("description") or alert.annotations.get("summary", ""),
            )
            for alert in self.alerts
            if alert.status == "firing"
        ]
