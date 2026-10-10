import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from . import __version__
from .analyzer import build_analyzer
from .collector import collect_signals, load_core_api
from .config import Settings
from .models import AlertmanagerWebhook, AnalyzeRequest, Report

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app.state.settings = settings
    app.state.analyzer = build_analyzer(settings)
    yield


app = FastAPI(title="AIOps Incident Analyzer", version=__version__, lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
def analyze(body: AnalyzeRequest, request: Request) -> Report:
    """Diagnose signals supplied by the caller."""
    return request.app.state.analyzer.analyze(body.signals)


@app.post("/alerts/alertmanager")
def alertmanager_webhook(body: AlertmanagerWebhook, request: Request) -> Report:
    """Receiver for Prometheus Alertmanager webhooks."""
    signals = body.to_signals()
    if not signals:
        return Report(summary="No firing alerts.", findings=[], engine="rules")
    return request.app.state.analyzer.analyze(signals)


@app.get("/cluster/report")
def cluster_report(request: Request) -> Report:
    """Scan the cluster for unhealthy pods and warning events, then diagnose them."""
    settings: Settings = request.app.state.settings
    try:
        signals = collect_signals(load_core_api(), settings.max_events)
    except Exception as exc:
        logger.exception("Failed to read cluster state")
        raise HTTPException(status_code=503, detail="Kubernetes API unavailable") from exc

    if not signals:
        return Report(summary="No problems detected.", findings=[], engine="rules")
    return request.app.state.analyzer.analyze(signals)
