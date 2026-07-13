"""PR Risk Agent - FastAPI application.

Serves the single-page frontend and a small JSON API that sends PR details to
an LLM for a structured pre-merge risk analysis.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.models import AnalyzeRequest, PRAnalysis
from app.services.analyzer import AnalyzerError, analyze_pr

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pr_risk_agent")

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="PR Risk Agent", description="Know the risk before you merge.")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Keep validation feedback client-friendly; never leak internals.
    messages = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []) if loc != "body")
        messages.append(f"{field}: {error.get('msg')}" if field else error.get("msg"))
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request.", "details": messages},
    )


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/analyze", response_model=PRAnalysis)
async def analyze(payload: AnalyzeRequest):
    logger.info(
        "Analyze request received (title_len=%d, diff_len=%d, context_len=%d)",
        len(payload.pr_title),
        len(payload.diff),
        len(payload.context),
    )
    try:
        result = analyze_pr(payload)
    except AnalyzerError as exc:
        logger.warning("Analyzer error: %s", exc)
        return JSONResponse(status_code=502, content={"error": str(exc)})
    except Exception:  # noqa: BLE001 - defensive boundary, never leak internals
        logger.exception("Unexpected error during PR analysis")
        return JSONResponse(
            status_code=500,
            content={"error": "An unexpected error occurred while analyzing this PR."},
        )
    logger.info("Analyze request completed (risk_level=%s)", result.risk_level)
    return result
