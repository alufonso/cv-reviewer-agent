"""
Regression tests for the stage-1 audit fixes:
CORS origin allow-list, safe Master Profile read/write, and Unicode text in PDFs.
"""
import json

import fitz  # PyMuPDF
import pytest
from fastapi.testclient import TestClient

import main
from pdf_generator import create_pdf_from_structured_cv
from schemas import StructuredCV

NON_LATIN_NAME = "Nguyễn Văn Đức"


def make_cv(name: str = NON_LATIN_NAME) -> StructuredCV:
    """Builds a small StructuredCV with every section filled."""
    return StructuredCV(
        header={"name": name, "headline": "Engineer", "location": "Hà Nội",
                "phone": "1", "email": "a@b.c", "portfolio": "p", "linkedin": "l", "github": "g"},
        summary="Résumé with “smart quotes” – and dashes.",
        skills=[{"category": "Languages", "items": "Python, Go"}],
        experience=[{"role": "Dev", "company": "Łódź Ltd", "duration": "2024", "location": "PL",
                     "bullets": ["Built things"]}],
        projects=[{"name": "P", "context": "Personal", "technologies": "Py", "link": "x",
                   "bullets": ["Did it"]}],
        publications=[{"citation": "Some paper"}],
        certifications=[{"name": "Cert", "issuer": "Org"}],
        education=[{"institution": "Uni", "degree": "BSc", "duration": "2020", "gpa": "3.9"}],
        languages_other={"languages": "Tiếng Việt", "other_skills": "Teamwork"},
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client whose Master Profile lives in a temp folder."""
    monkeypatch.setattr(main, "MASTER_PROFILE_PATH", str(tmp_path / "master_profile.json"))
    return TestClient(main.app)


def test_pdf_keeps_non_latin_characters():
    pdf_bytes = create_pdf_from_structured_cv(make_cv()).getvalue()
    text = "".join(page.get_text() for page in fitz.open(stream=pdf_bytes, filetype="pdf"))
    assert NON_LATIN_NAME.upper() in text
    assert "Łódź Ltd" in text
    assert "Tiếng Việt" in text
    assert "“smart quotes”" in text


def test_cors_allows_frontend_only(client):
    ok = client.get("/profile", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"

    evil = client.get("/profile", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil.headers


def test_corrupt_profile_is_an_error_not_an_empty_profile(client):
    with open(main.MASTER_PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write('{"basic_info": {"name": "Ana"},')  # truncated JSON

    response = client.get("/profile")
    assert response.status_code == 500


def test_missing_profile_returns_empty_profile(client):
    response = client.get("/profile")
    assert response.status_code == 200
    assert response.json()["basic_info"]["name"] == ""


def test_save_profile_round_trip_leaves_no_temp_file(client, tmp_path):
    profile = {"basic_info": {"name": "Ana"}, "skills": ["Python"]}
    assert client.post("/profile", json=profile).status_code == 200

    assert client.get("/profile").json()["basic_info"]["name"] == "Ana"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["master_profile.json"]
    with open(main.MASTER_PROFILE_PATH, encoding="utf-8") as f:
        assert json.load(f)["skills"] == ["Python"]
