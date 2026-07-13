"""Small, focused test suite for PR Risk Agent. No real API calls are made."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import PRAnalysis

client = TestClient(app)

SAMPLE_ANALYSIS = PRAnalysis(
    summary="Adds a search endpoint and a bulk delete endpoint for admin users.",
    risk_level="critical",
    merge_recommendation="block",
    confidence_score=82,
    findings=[
        {
            "category": "security",
            "severity": "critical",
            "title": "SQL injection via string concatenation",
            "explanation": "The search query is built with raw string concatenation of user input.",
            "evidence": "query = \"SELECT id, name, email, active FROM users WHERE name = '\" + name + \"'\"",
            "suggested_fix": "Use parameterized queries.",
        }
    ],
    missing_tests=[
        {"test": "test_cleanup_inactive_users_requires_admin", "reason": "No auth test exists.", "priority": "high"}
    ],
    deployment_considerations=["Deploys directly to production with no staging environment."],
    rollback_plan=["Revert the commit and redeploy the previous image."],
    positive_observations=["Reuses the existing database connection helper."],
    final_reasoning="Multiple critical security issues make this unsafe to merge as-is.",
)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_index_serves_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "PR Risk Agent" in response.text


def test_empty_diff_is_rejected():
    response = client.post(
        "/api/analyze",
        json={"pr_title": "Test", "pr_description": "", "diff": "   ", "context": ""},
    )
    assert response.status_code == 422
    body = response.json()
    assert "error" in body


def test_missing_diff_field_is_rejected():
    response = client.post("/api/analyze", json={"pr_title": "Test"})
    assert response.status_code == 422


def test_diff_too_long_is_rejected():
    response = client.post(
        "/api/analyze",
        json={"diff": "x" * 50_001},
    )
    assert response.status_code == 422


@patch("app.main.analyze_pr", return_value=SAMPLE_ANALYSIS)
def test_valid_request_returns_expected_structure(mock_analyze):
    response = client.post(
        "/api/analyze",
        json={
            "pr_title": "Add bulk cleanup endpoint",
            "pr_description": "Adds admin cleanup tooling.",
            "diff": "diff --git a/app.py b/app.py\n+print('hello')\n",
            "context": "FastAPI service",
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["risk_level"] == "critical"
    assert body["merge_recommendation"] == "block"
    assert body["confidence_score"] == 82
    assert isinstance(body["findings"], list)
    assert body["findings"][0]["category"] == "security"
    assert isinstance(body["missing_tests"], list)
    assert isinstance(body["deployment_considerations"], list)
    assert isinstance(body["rollback_plan"], list)
    assert isinstance(body["positive_observations"], list)
    assert "final_reasoning" in body
    mock_analyze.assert_called_once()


@patch("app.main.analyze_pr", side_effect=Exception("boom"))
def test_unexpected_analyzer_error_is_handled_gracefully(mock_analyze):
    response = client.post(
        "/api/analyze",
        json={"diff": "diff --git a/app.py b/app.py\n+print('hello')\n"},
    )
    assert response.status_code == 500
    body = response.json()
    assert "error" in body
    assert "boom" not in body["error"]