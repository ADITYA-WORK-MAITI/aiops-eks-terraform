import json
from types import SimpleNamespace

import pytest

from aiops.analyzer import GeminiAnalyzer, RuleBasedAnalyzer, build_analyzer
from aiops.config import Settings
from aiops.models import Signal


def make_settings(api_key: str | None = None) -> Settings:
    return Settings(
        gemini_api_key=api_key,
        gemini_model="gemini-2.5-flash",
        gemini_timeout_seconds=5,
        max_events=10,
        log_level="INFO",
    )


def test_rules_diagnose_known_reason():
    signal = Signal(source="pod", namespace="shop", resource="pod/cart-7d9f/app", reason="OOMKilled")
    report = RuleBasedAnalyzer().analyze([signal])

    finding = report.findings[0]
    assert report.engine == "rules"
    assert finding.severity == "critical"
    assert finding.category == "resources"
    assert "kubectl top pod -n shop" in finding.remediation[0]


def test_rules_sort_critical_first_and_handle_unknown_reason():
    signals = [
        Signal(source="event", resource="pod/a", reason="SomethingOdd", message="odd"),
        Signal(source="event", resource="pod/b", reason="FailedScheduling"),
        Signal(source="pod", resource="pod/c/app", reason="CrashLoopBackOff"),
    ]
    report = RuleBasedAnalyzer().analyze(signals)

    assert [f.severity for f in report.findings] == ["critical", "warning", "info"]
    assert report.findings[-1].root_cause == "odd"
    assert report.summary == "3 issue(s) found, 1 critical."


def test_build_analyzer_without_key_uses_rules():
    assert isinstance(build_analyzer(make_settings()), RuleBasedAnalyzer)


class FakeModel:
    def __init__(self, text: str | None = None, error: Exception | None = None):
        self.text, self.error = text, error

    def generate_content(self, prompt, request_options=None):
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


@pytest.fixture
def gemini(monkeypatch):
    def factory(model: FakeModel) -> GeminiAnalyzer:
        monkeypatch.setattr("google.generativeai.configure", lambda **_: None)
        monkeypatch.setattr("google.generativeai.GenerativeModel", lambda *_, **__: model)
        return GeminiAnalyzer(make_settings(api_key="test"))

    return factory


SIGNAL = Signal(source="pod", namespace="default", resource="pod/api/app", reason="OOMKilled")


def test_gemini_response_is_parsed(gemini):
    body = {
        "summary": "Memory pressure on api.",
        "findings": [
            {
                "resource": "pod/api",
                "severity": "critical",
                "category": "resources",
                "root_cause": "Memory leak after deploy.",
                "remediation": ["Roll back the deployment."],
            }
        ],
    }
    report = gemini(FakeModel(text=json.dumps(body))).analyze([SIGNAL])

    assert report.engine == "gemini"
    assert report.findings[0].root_cause == "Memory leak after deploy."


@pytest.mark.parametrize(
    "model",
    [
        FakeModel(error=TimeoutError("deadline exceeded")),
        FakeModel(text="not json"),
        FakeModel(text=json.dumps({"summary": "x", "findings": [{"severity": "bogus"}]})),
    ],
    ids=["api-error", "invalid-json", "schema-mismatch"],
)
def test_gemini_falls_back_to_rules(gemini, model):
    report = gemini(model).analyze([SIGNAL])

    assert report.engine == "rules"
    assert report.findings[0].category == "resources"
