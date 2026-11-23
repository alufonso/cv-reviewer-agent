"""
Regression tests for the stage-2 audit fixes:
Gemini model fallback, apply-suggestion cache key, and removed unused endpoints.
"""
import pytest
from fastapi.testclient import TestClient

import analyzer
import main
from schemas import AnalysisResponse
from test_stage1 import make_cv

ANALYSIS_JSON = AnalysisResponse(
    ats_score=80,
    section_feedback={"summary": "s", "experience": "e", "skills": "k"},
).model_dump_json()


class FakeModels:
    """Stands in for client.models: raises the queued errors, then returns ANALYSIS_JSON."""

    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = []

    def generate_content(self, model, contents, config):
        """Records the model name and either raises the next queued error or answers."""
        self.calls.append(model)
        if self.errors:
            raise self.errors.pop(0)
        return type("Resp", (), {"text": ANALYSIS_JSON})()


def use_fake_gemini(monkeypatch, errors):
    """Replaces genai.Client with a fake and returns its FakeModels for inspection."""
    fake = FakeModels(errors)
    monkeypatch.setattr(analyzer.genai, "Client", lambda: type("C", (), {"models": fake})())
    return fake


def test_falls_back_to_next_model_when_busy(monkeypatch):
    fake = use_fake_gemini(monkeypatch, [RuntimeError("503 UNAVAILABLE")])
    result = analyzer.analyze_cv("cv text")
    assert result.ats_score == 80
    assert fake.calls == analyzer.MODELS[:2]


def test_other_errors_stop_immediately(monkeypatch):
    fake = use_fake_gemini(monkeypatch, [RuntimeError("400 INVALID_ARGUMENT")])
    with pytest.raises(RuntimeError, match="INVALID_ARGUMENT"):
        analyzer.analyze_cv("cv text")
    assert fake.calls == analyzer.MODELS[:1]


def test_all_models_busy_raises(monkeypatch):
    use_fake_gemini(monkeypatch, [RuntimeError("429 RESOURCE_EXHAUSTED")] * len(analyzer.MODELS))
    with pytest.raises(RuntimeError, match="All models failed"):
        analyzer.analyze_cv("cv text")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with a saved profile, empty cache and a counting fake apply_suggestion_to_cv."""
    monkeypatch.setattr(main, "MASTER_PROFILE_PATH", str(tmp_path / "master_profile.json"))
    main.suggestion_cache.clear()
    main.rate_limit_tracker.clear()
    c = TestClient(main.app)
    c.post("/profile", json={"basic_info": {"name": "Ana"}})

    calls = []

    def fake_apply(**kwargs):
        calls.append(kwargs)
        return make_cv()

    monkeypatch.setattr(main, "apply_suggestion_to_cv", fake_apply)
    c.apply_calls = calls
    return c


def test_cache_separates_language_and_baseline(client):
    base = {"suggestion": "Add metrics", "job_description": "JD"}
    client.post("/apply-suggestion", data={**base, "language": "English"})
    client.post("/apply-suggestion", data={**base, "language": "English"})  # cache hit
    client.post("/apply-suggestion", data={**base, "language": "Indonesian"})
    client.post("/apply-suggestion", data={**base, "language": "English",
                                           "original_cv": make_cv("Other").model_dump_json()})
    assert len(client.apply_calls) == 3


@pytest.mark.anyio
async def test_slow_gemini_call_does_not_block_other_requests(client, monkeypatch):
    """While one request waits 1.5s on Gemini, GET /profile must still answer quickly."""
    import time

    import anyio
    import httpx

    def slow_generate(*args, **kwargs):
        time.sleep(1.5)
        return make_cv()

    monkeypatch.setattr(main, "generate_cv_from_profile", slow_generate)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        profile_took = None

        async def get_profile():
            nonlocal profile_took
            await anyio.sleep(0.2)  # let the slow request start first
            await ac.get("/profile")
            profile_took = time.perf_counter() - start

        # Start the clock before either request: if the event loop is blocked,
        # the GET task cannot even begin until the slow call ends.
        start = time.perf_counter()
        async with anyio.create_task_group() as tg:
            tg.start_soon(ac.post, "/generate/preview")
            tg.start_soon(get_profile)

    assert profile_took < 0.8, f"GET /profile waited {profile_took:.2f}s behind the Gemini call"


@pytest.fixture
def anyio_backend():
    """Run async tests on asyncio only."""
    return "asyncio"


@pytest.mark.parametrize("path", ["/generate/docx", "/generate/pdf"])
def test_unused_generate_endpoints_are_gone(client, path):
    assert client.post(path).status_code == 404


@pytest.mark.parametrize("path,kind", [("/generate/docx/from-json", "wordprocessingml"),
                                       ("/generate/pdf/from-json", "pdf")])
def test_from_json_downloads_still_work(client, path, kind):
    response = client.post(path, json=make_cv().model_dump())
    assert response.status_code == 200
    assert kind in response.headers["content-type"]
    assert "Tailored_CV" in response.headers["content-disposition"]
