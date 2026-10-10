import pytest
from fastapi.testclient import TestClient

from aiops.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_analyze_returns_report(client):
    body = {"signals": [{"source": "pod", "resource": "pod/web/app", "reason": "ImagePullBackOff"}]}
    resp = client.post("/analyze", json=body)

    assert resp.status_code == 200
    assert resp.json()["findings"][0]["category"] == "image"


def test_analyze_rejects_empty_signal_list(client):
    assert client.post("/analyze", json={"signals": []}).status_code == 422


def test_alertmanager_webhook_ignores_resolved_alerts(client):
    body = {
        "alerts": [
            {"status": "resolved", "labels": {"alertname": "KubePodCrashLooping"}},
            {
                "status": "firing",
                "labels": {"alertname": "OOMKilled", "namespace": "shop", "pod": "cart-1"},
                "annotations": {"description": "Container cart was OOM killed"},
            },
        ]
    }
    findings = client.post("/alerts/alertmanager", json=body).json()["findings"]

    assert len(findings) == 1
    assert findings[0]["resource"] == "cart-1"


def test_cluster_report_returns_503_without_cluster_access(client, monkeypatch):
    def unavailable():
        raise RuntimeError("no kubeconfig")

    monkeypatch.setattr("aiops.main.load_core_api", unavailable)
    assert client.get("/cluster/report").status_code == 503
