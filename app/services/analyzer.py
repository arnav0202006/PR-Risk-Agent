"""LLM integration for PR Risk Agent.

Isolated so the model/provider can be swapped without touching API routes.
"""
from __future__ import annotations

import json
import logging
import os

from openai import APIError, APITimeoutError, OpenAI
from pydantic import ValidationError

from app.models import AnalyzeRequest, PRAnalysis

logger = logging.getLogger("pr_risk_agent.analyzer")

DEFAULT_MODEL = "gpt-4.1-mini"
REQUEST_TIMEOUT_SECONDS = 45
MAX_OUTPUT_TOKENS = 2000

SYSTEM_PROMPT = """You are PR Risk Agent, a cautious, senior software engineer performing an \
automated pre-merge review of a proposed code change.

Ground rules:
- Analyze ONLY the evidence provided (PR title, description, diff, and optional context). \
Never invent files, repository conventions, frameworks, or history that are not present in \
the evidence.
- Clearly distinguish confirmed issues (visible directly in the diff) from possible risks \
(plausible but uncertain given limited context). Do not exaggerate low-confidence concerns.
- Consider correctness, edge cases, security, performance, reliability, maintainability, \
testing, deployment, and rollback safety.
- Pay special attention to: authentication, authorization, input validation, database changes, \
concurrency, resource leaks, secret exposure, API compatibility, null/None handling, exception \
handling, and destructive operations (deletes, drops, migrations, mass updates).
- Recognize good engineering decisions as well as risks. If the diff includes tests, defensive \
checks, or clear naming, call that out as a positive observation.
- Cite relevant file names or changed lines from the diff whenever possible in "evidence" fields.
- Assign an honest confidence_score (0-100) based on how much context you actually have. A tiny \
diff with no repository context should yield a lower confidence score than a large, well-described \
change.
- This is an automated assistant, not a replacement for human code review or testing. Do not \
claim certainty.
- Output MUST be a single JSON object matching the schema below exactly. No markdown, no prose \
outside the JSON, no trailing commentary.

JSON schema:
{
  "summary": "string - concise summary of what changed",
  "risk_level": "low | medium | high | critical",
  "merge_recommendation": "approve | approve_with_caution | request_changes | block",
  "confidence_score": 0-100 number,
  "findings": [
    {
      "category": "correctness | security | performance | reliability | maintainability",
      "severity": "info | low | medium | high | critical",
      "title": "string",
      "explanation": "string",
      "evidence": "string - file name / line / snippet from the diff if possible",
      "suggested_fix": "string"
    }
  ],
  "missing_tests": [
    {"test": "string", "reason": "string", "priority": "low | medium | high"}
  ],
  "deployment_considerations": ["string"],
  "rollback_plan": ["string"],
  "positive_observations": ["string"],
  "final_reasoning": "string - short explanation tying the recommendation together"
}

Return findings=[] and missing_tests=[] (empty arrays) if none apply. Keep every field concise \
and specific. Do not wrap the JSON in markdown code fences."""


class AnalyzerError(Exception):
    """Raised when the analyzer cannot produce a usable analysis."""


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise AnalyzerError("Server is not configured with an OpenAI API key.")
    return OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)


def _get_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)


def _build_user_prompt(request: AnalyzeRequest) -> str:
    parts = [
        f"PR Title:\n{request.pr_title or '(not provided)'}",
        f"PR Description:\n{request.pr_description or '(not provided)'}",
        f"Repository / System Context:\n{request.context or '(not provided)'}",
        f"Diff / Code Change:\n{request.diff}",
    ]
    return "\n\n".join(parts)


def _extract_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _call_model(client: OpenAI, model: str, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    content = response.choices[0].message.content
    if not content:
        raise AnalyzerError("The model returned an empty response.")
    return content


def analyze_pr(request: AnalyzeRequest) -> PRAnalysis:
    """Send the PR details to the LLM and return a validated PRAnalysis.

    Performs a single controlled retry if the first response is not valid JSON
    or fails schema validation.
    """
    client = _get_client()
    model = _get_model()
    user_prompt = _build_user_prompt(request)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw_content = _call_model(client, model, user_prompt)
            data = _extract_json(raw_content)
            return PRAnalysis.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            logger.warning(
                "Analyzer produced invalid structured output on attempt %d: %s",
                attempt + 1,
                type(exc).__name__,
            )
            continue
        except APITimeoutError as exc:
            logger.error("OpenAI request timed out: %s", exc)
            raise AnalyzerError("The analysis request timed out. Please try again.") from exc
        except APIError as exc:
            logger.error("OpenAI API error: %s", exc)
            raise AnalyzerError(
                "The analysis service is temporarily unavailable. Please try again shortly."
            ) from exc

    logger.error("Analyzer failed after retry: %s", last_error)
    raise AnalyzerError(
        "The model returned a response that could not be validated. Please try again."
    )
