"""
Regression tests for the stage-3 audit fixes: DOCX and PDF agree on optional lines.
"""
import io

import fitz  # PyMuPDF
from docx import Document

from docx_generator import create_docx_from_structured_cv
from pdf_generator import create_pdf_from_structured_cv
from test_stage1 import make_cv


def docx_text(cv) -> str:
    """Returns all paragraph text of the generated DOCX."""
    doc = Document(io.BytesIO(create_docx_from_structured_cv(cv).getvalue()))
    return "\n".join(p.text for p in doc.paragraphs)


def pdf_text(cv) -> str:
    """Returns all text of the generated PDF."""
    pdf = fitz.open(stream=create_pdf_from_structured_cv(cv).getvalue(), filetype="pdf")
    return "".join(page.get_text() for page in pdf)


def test_empty_languages_and_other_skills_are_left_out():
    cv = make_cv()
    cv.skills[0].category = "Programming"  # avoid a false "Languages:" match from the skills section
    cv.languages_other.languages = ""
    cv.languages_other.other_skills = ""
    for text in (docx_text(cv), pdf_text(cv)):
        assert "Languages & Other Skills" not in text
        assert "Languages:" not in text
        assert "Other Skills:" not in text


def test_only_filled_line_is_printed():
    cv = make_cv()
    cv.languages_other.other_skills = ""
    for text in (docx_text(cv), pdf_text(cv)):
        assert "Languages: Tiếng Việt" in text.replace("\n", " ")
        assert "Other Skills:" not in text
