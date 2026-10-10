"""Turns raw signals into a diagnosis, using Gemini when available and rules otherwise."""

import json
import logging
from typing import Protocol

from .config import Settings
from .models import Finding, Report, Severity, Signal

logger = logging.getLogger(__name__)


class Analyzer(Protocol):
    def analyze(self, signals: list[Signal]) -> Report: ...


# reason -> (severity, category, root cause, remediation steps)
RULES: dict[str, tuple[Severity, str, str, list[str]]] = {
    "OOMKilled": (
        "critical",
        "resources",
        "The container exceeded its memory limit and was killed by the kernel.",
        [
            "Check memory usage: kubectl top pod -n {ns}",
            "Raise resources.limits.memory or fix the memory leak in the application.",
        ],
    ),
    "CrashLoopBackOff": (
        "critical",
        "application",
        "The container starts and exits repeatedly.",
        [
            "Read the previous logs: kubectl logs {name} -n {ns} --previous",
            "Check the command, environment variables and liveness probe settings.",
        ],
    ),
    "ImagePullBackOff": (
        "critical",
        "image",
        "The node cannot pull the container image.",
        [
            "Verify the image name and tag exist in the registry.",
            "Confirm the node IAM role has ECR read access (AmazonEC2ContainerRegistryReadOnly).",
        ],
    ),
    "CreateContainerConfigError": (
        "critical",
        "configuration",
        "A referenced ConfigMap or Secret is missing or invalid.",
        ["Run kubectl describe pod {name} -n {ns} and create the missing ConfigMap or Secret."],
    ),
    "Unschedulable": (
        "warning",
        "capacity",
        "No node has enough free CPU or memory, or the pod's constraints cannot be met.",
        [
            "Check pending reasons: kubectl describe pod {name} -n {ns}",
            "Cluster Autoscaler should add a node; if not, check node_max_size and its logs.",
        ],
    ),
    "FailedScheduling": (
        "warning",
        "capacity",
        "The scheduler could not place the pod on any node.",
        ["Review resource requests, node selectors, taints and the node group's max size."],
    ),
    "BackOff": (
        "warning",
        "application",
        "Kubernetes is backing off restarts of a failing container.",
        ["Read the previous logs: kubectl logs {name} -n {ns} --previous"],
    ),
    "Unhealthy": (
        "warning",
        "probes",
        "Liveness or readiness probes are failing.",
        ["Check the probe path, port and initialDelaySeconds against the app's startup time."],
    ),
    "FailedCreatePodSandBox": (
        "warning",
        "networking",
        "The VPC CNI could not set up pod networking, often because the subnet ran out of IPs.",
        ["Check free IPs in the private subnets and the aws-node logs in kube-system."],
    ),
}
RULES["ErrImagePull"] = RULES["ImagePullBackOff"]
RULES["InvalidImageName"] = RULES["ImagePullBackOff"]

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


class RuleBasedAnalyzer:
    """Deterministic analyzer covering the most common Kubernetes failure modes."""

    def analyze(self, signals: list[Signal]) -> Report:
        findings = [self._diagnose(s) for s in signals]
        findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
        return Report(summary=_summarize(findings), findings=findings, engine="rules")

    @staticmethod
    def _diagnose(signal: Signal) -> Finding:
        severity, category, cause, steps = RULES.get(
            signal.reason,
            ("info", "unknown", signal.message or f"Unrecognized reason '{signal.reason}'.", []),
        )
        name = signal.resource.split("/")[1] if "/" in signal.resource else signal.resource
        ns = signal.namespace or "default"
        return Finding(
            resource=signal.resource,
            severity=severity,
            category=category,
            root_cause=cause,
            remediation=[step.format(name=name, ns=ns) for step in steps],
        )


PROMPT = """You are an SRE assistant for an Amazon EKS cluster.
Analyze the following signals collected from the cluster. Group related signals,
identify the most likely root cause of each problem, and give concrete remediation
steps (kubectl or AWS CLI commands where useful).

Respond with JSON only, matching this schema:
{{
  "summary": "one or two sentence overview",
  "findings": [
    {{
      "resource": "kind/name",
      "severity": "critical" | "warning" | "info",
      "category": "short label, e.g. resources, image, networking",
      "root_cause": "explanation",
      "remediation": ["step", "..."]
    }}
  ]
}}

Signals:
{signals}
"""


class GeminiAnalyzer:
    """LLM-backed analyzer using Google Gemini, with a rule-based fallback."""

    def __init__(self, settings: Settings, fallback: Analyzer | None = None):
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(
            settings.gemini_model,
            generation_config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        self._timeout = settings.gemini_timeout_seconds
        self._fallback = fallback or RuleBasedAnalyzer()

    def analyze(self, signals: list[Signal]) -> Report:
        payload = json.dumps([s.model_dump(exclude_none=True) for s in signals], indent=2)
        try:
            response = self._model.generate_content(
                PROMPT.format(signals=payload),
                request_options={"timeout": self._timeout},
            )
            data = json.loads(response.text)
            return Report(summary=data["summary"], findings=data["findings"], engine="gemini")
        except Exception:
            logger.exception("Gemini analysis failed; falling back to rules")
            return self._fallback.analyze(signals)


def build_analyzer(settings: Settings) -> Analyzer:
    if settings.gemini_api_key:
        return GeminiAnalyzer(settings)
    logger.warning("GEMINI_API_KEY not set; using rule-based analyzer")
    return RuleBasedAnalyzer()


def _summarize(findings: list[Finding]) -> str:
    if not findings:
        return "No problems detected."
    critical = sum(f.severity == "critical" for f in findings)
    return f"{len(findings)} issue(s) found, {critical} critical."
