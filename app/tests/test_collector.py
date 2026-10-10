from types import SimpleNamespace as NS

from aiops.collector import collect_signals, deduplicate, event_signals, pod_signals
from aiops.models import Signal


def container(name="app", waiting=None, terminated=None, restarts=0):
    return NS(
        name=name,
        restart_count=restarts,
        state=NS(waiting=waiting),
        last_state=NS(terminated=terminated),
    )


def pod(name, phase="Running", containers=(), conditions=None, namespace="default"):
    return NS(
        metadata=NS(name=name, namespace=namespace),
        status=NS(phase=phase, container_statuses=list(containers), conditions=conditions),
    )


def test_crashloop_caused_by_oom_is_reported_as_oom():
    p = pod(
        "api",
        containers=[
            container(
                waiting=NS(reason="CrashLoopBackOff", message="back-off"),
                terminated=NS(reason="OOMKilled", exit_code=137),
                restarts=4,
            )
        ],
    )
    [signal] = pod_signals([p])

    assert signal.reason == "OOMKilled"
    assert signal.resource == "pod/api/app"
    assert signal.count == 4


def test_pending_unschedulable_pod_is_reported():
    cond = NS(type="PodScheduled", status="False", reason="Unschedulable", message="0/2 nodes available")
    [signal] = pod_signals([pod("worker", phase="Pending", conditions=[cond])])

    assert signal.reason == "Unschedulable"
    assert "0/2 nodes" in signal.message


def test_healthy_pod_produces_no_signals():
    assert pod_signals([pod("ok", containers=[container()])]) == []


def event(reason, count, kind="Pod", name="api", type_="Warning"):
    return NS(
        type=type_,
        reason=reason,
        message=f"{reason} happened",
        count=count,
        involved_object=NS(kind=kind, name=name, namespace="default"),
    )


def test_event_signals_keep_most_frequent_warnings():
    events = [event("BackOff", 2), event("Unhealthy", 9), event("Scheduled", 1, type_="Normal")]
    signals = event_signals(events, limit=1)

    assert [s.reason for s in signals] == ["Unhealthy"]
    assert signals[0].resource == "pod/api"


def test_deduplicate_keeps_highest_count():
    a = Signal(source="event", resource="pod/x", reason="BackOff", count=1)
    b = Signal(source="event", resource="pod/x", reason="BackOff", count=7)
    assert deduplicate([a, b]) == [b]


def test_collect_signals_queries_only_warning_events():
    calls = {}

    class FakeCoreApi:
        def list_pod_for_all_namespaces(self):
            return NS(items=[])

        def list_event_for_all_namespaces(self, field_selector):
            calls["field_selector"] = field_selector
            return NS(items=[event("FailedScheduling", 3)])

    signals = collect_signals(FakeCoreApi(), max_events=10)

    assert calls["field_selector"] == "type=Warning"
    assert [s.reason for s in signals] == ["FailedScheduling"]
