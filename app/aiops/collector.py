"""Collects failure signals from the Kubernetes API."""

from collections.abc import Iterable
from typing import Any

from .models import Signal

WAITING_REASONS = {
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
    "CreateContainerConfigError",
    "InvalidImageName",
}
TERMINATED_REASONS = {"OOMKilled", "Error"}


def load_core_api() -> Any:
    """Return a CoreV1Api client using in-cluster config, falling back to kubeconfig."""
    from kubernetes import client, config

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CoreV1Api()


def pod_signals(pods: Iterable[Any]) -> list[Signal]:
    signals: list[Signal] = []
    for pod in pods:
        name = f"pod/{pod.metadata.name}"
        namespace = pod.metadata.namespace

        if pod.status.phase == "Pending":
            for cond in pod.status.conditions or []:
                if cond.type == "PodScheduled" and cond.status == "False":
                    signals.append(
                        Signal(
                            source="pod",
                            namespace=namespace,
                            resource=name,
                            reason=cond.reason or "Unschedulable",
                            message=cond.message or "",
                        )
                    )

        for cs in pod.status.container_statuses or []:
            waiting = cs.state.waiting if cs.state else None
            last = cs.last_state.terminated if cs.last_state else None
            restarts = max(cs.restart_count or 0, 1)

            if waiting and waiting.reason in WAITING_REASONS:
                reason, message = waiting.reason, waiting.message or ""
                # A crash loop is a symptom; the last termination usually holds the cause.
                if reason == "CrashLoopBackOff" and last and last.reason == "OOMKilled":
                    reason, message = "OOMKilled", f"exit code {last.exit_code}"
            elif last and last.reason in TERMINATED_REASONS:
                reason, message = last.reason, f"exit code {last.exit_code}"
            else:
                continue

            signals.append(
                Signal(
                    source="pod",
                    namespace=namespace,
                    resource=f"{name}/{cs.name}",
                    reason=reason,
                    message=message,
                    count=restarts,
                )
            )
    return signals


def event_signals(events: Iterable[Any], limit: int) -> list[Signal]:
    warnings = [e for e in events if e.type == "Warning"]
    warnings.sort(key=lambda e: e.count or 1, reverse=True)
    return [
        Signal(
            source="event",
            namespace=e.involved_object.namespace,
            resource=f"{e.involved_object.kind.lower()}/{e.involved_object.name}",
            reason=e.reason or "Warning",
            message=e.message or "",
            count=e.count or 1,
        )
        for e in warnings[:limit]
    ]


def collect_signals(core_api: Any, max_events: int) -> list[Signal]:
    pods = core_api.list_pod_for_all_namespaces().items
    events = core_api.list_event_for_all_namespaces(field_selector="type=Warning").items
    return deduplicate(pod_signals(pods) + event_signals(events, max_events))


def deduplicate(signals: list[Signal]) -> list[Signal]:
    seen: dict[tuple[str | None, str, str], Signal] = {}
    for signal in signals:
        key = (signal.namespace, signal.resource, signal.reason)
        if key not in seen or signal.count > seen[key].count:
            seen[key] = signal
    return list(seen.values())
