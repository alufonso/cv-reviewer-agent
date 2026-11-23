"""
Main entry point for the CVSight FastAPI backend.
Defines the API routes for CV analysis.
"""
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import os
import json
from typing import Optional
from schemas import AnalysisResponse, MasterProfile, StructuredCV
from parser import extract_text_from_pdf, extract_text_from_docx
from analyzer import analyze_cv, extract_profile_from_cv, generate_cv_from_profile, apply_suggestion_to_cv
from docx_generator import create_docx_from_structured_cv
from pdf_generator import create_pdf_from_structured_cv
import hashlib
import time

# Load environment variables from .env if present
load_dotenv()

app = FastAPI(
    title="CVSight MVP API",
    description="API for analyzing CVs against Job Descriptions using Gemini.",
    version="1.0.0"
)

MASTER_PROFILE_PATH = "master_profile.json"

# --- Apply Suggestion: Cache & Rate Limiting ---
# In-memory cache keyed by hash(suggestion + profile + job description + baseline CV + language).
# Prevents duplicate API calls when user clicks the same suggestion twice.
suggestion_cache: dict[str, dict] = {}

# Simple per-IP rate limiter: tracks timestamps of recent /apply-suggestion calls.
# Format: { ip_string: [timestamp1, timestamp2, ...] }
APPLY_RATE_LIMIT = 5       # max calls per window
APPLY_RATE_WINDOW = 60     # window in seconds
rate_limit_tracker: dict[str, list[float]] = {}

# Only the local frontend may call this API from a browser. A wildcard would let
# any website the user visits read and overwrite the Master Profile.
# Override with a comma-separated list in ALLOWED_ORIGINS if the frontend runs elsewhere.
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    """
    Health check endpoint.
    
    Returns:
        dict: A welcome message indicating the API is running.
    """
    return {"message": "Welcome to CVSight API. Go to /docs for Swagger UI."}

def _read_profile_dict() -> Optional[dict]:
    """
    Reads the saved Master Profile JSON.

    Returns:
        dict | None: The profile data, or None when no profile has been saved yet.

    Raises:
        HTTPException: 500 if the file exists but cannot be read. Treating a broken
            file as "no profile" would let the UI save an empty profile over it.
    """
    if not os.path.exists(MASTER_PROFILE_PATH):
        return None
    try:
        with open(MASTER_PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"{MASTER_PROFILE_PATH} exists but could not be read ({e}). Fix or remove the file.",
        )


def _require_profile() -> dict:
    """
    Returns the saved Master Profile data.

    Raises:
        HTTPException: 400 if no (or an empty) profile is saved, 500 if it is unreadable.
    """
    data = _read_profile_dict()
    if not data:
        raise HTTPException(status_code=400, detail="Master Profile not found. Please create one first.")
    return data


def _file_response(stream, media_type: str, filename: str) -> StreamingResponse:
    """Wraps a generated file stream as a browser download."""
    return StreamingResponse(
        stream,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@app.get("/profile", response_model=MasterProfile)
def get_master_profile():
    """
    Retrieves the local Master Profile.
    If it doesn't exist, returns an empty profile.

    Raises:
        HTTPException: 500 if the file exists but cannot be read.
    """
    data = _read_profile_dict()
    return MasterProfile(**data) if data is not None else MasterProfile()

@app.post("/profile")
def update_master_profile(profile: MasterProfile):
    """
    Updates the local Master Profile and saves it to a JSON file.

    Writes to a temporary file first and then swaps it in, so a crash mid-write
    never leaves a half-written profile behind.
    """
    tmp_path = MASTER_PROFILE_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, MASTER_PROFILE_PATH)
        return {"status": "success", "message": "Master Profile updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_endpoint(
    cv_file: Optional[UploadFile] = File(None),
    job_description: str = Form(default="")
):
    """
    Endpoint to upload a CV (PDF) and an optional job description for analysis.
    If no CV is uploaded, it analyzes the saved Master Profile instead.

    The Gemini call runs in a worker thread so the server keeps answering
    other requests while it waits.

    Args:
        cv_file (UploadFile, optional): The uploaded PDF file containing the CV.
        job_description (str, optional): The job description to compare against. Defaults to "".

    Returns:
        AnalysisResponse: The structured analysis result from the AI.

    Raises:
        HTTPException: If the file is not a PDF, or if parsing/analysis fails.
    """
    cv_text = ""
    if cv_file:
        if cv_file.content_type not in ["application/pdf", DOCX_MEDIA_TYPE] and not cv_file.filename.endswith((".pdf", ".docx")):
            raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")

        try:
            file_bytes = await cv_file.read()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

        try:
            if cv_file.filename.endswith(".pdf") or cv_file.content_type == "application/pdf":
                cv_text = extract_text_from_pdf(file_bytes)
            else:
                cv_text = extract_text_from_docx(file_bytes)

            if not cv_text.strip():
                raise ValueError("No text could be extracted from the file.")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"File parsing error: {str(e)}")

    master_profile_data = _read_profile_dict()

    if not cv_text and not master_profile_data:
        raise HTTPException(status_code=400, detail="Must provide either a CV file or have a saved Master Profile.")

    try:
        return await run_in_threadpool(analyze_cv, cv_text, job_description, master_profile_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/profile/extract", response_model=MasterProfile)
async def extract_profile_endpoint(cv_file: UploadFile = File(...)):
    """
    Endpoint to upload a CV (PDF, DOCX or JSON) and extract its data into a Master Profile schema.
    The Gemini call runs in a worker thread so the server stays responsive.
    """
    if cv_file.content_type not in ["application/pdf", DOCX_MEDIA_TYPE, "application/json", "text/json"] and not cv_file.filename.endswith((".pdf", ".docx", ".json")):
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and JSON files are supported.")

    try:
        file_bytes = await cv_file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    try:
        if cv_file.filename.endswith(".pdf") or cv_file.content_type == "application/pdf":
            cv_text = extract_text_from_pdf(file_bytes)
        elif cv_file.filename.endswith(".docx") or cv_file.content_type == DOCX_MEDIA_TYPE:
            cv_text = extract_text_from_docx(file_bytes)
        else:
            # Assume JSON or text
            cv_text = file_bytes.decode('utf-8')

        if not cv_text.strip():
            raise ValueError("No text could be extracted from the file.")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"File parsing error: {str(e)}")

    try:
        return await run_in_threadpool(extract_profile_from_cv, cv_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profile extraction failed: {str(e)}")

@app.post("/generate/preview", response_model=StructuredCV)
def generate_cv_preview_endpoint(job_description: str = Form(default=""), language: str = Form(default="English")):
    """
    Endpoint to generate an ATS-friendly CV preview (JSON) based on the Master Profile and a Job Description.
    A plain `def` endpoint: FastAPI runs it in a worker thread, so the Gemini wait does not block the server.
    """
    master_profile_data = _require_profile()
    try:
        return generate_cv_from_profile(job_description, master_profile_data, language=language)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV preview generation failed: {str(e)}")

@app.post("/generate/docx/from-json")
def generate_cv_docx_from_json_endpoint(structured_cv: StructuredCV):
    """
    Endpoint to generate an ATS-friendly CV (.docx) directly from a provided StructuredCV JSON object.
    """
    try:
        return _file_response(create_docx_from_structured_cv(structured_cv), DOCX_MEDIA_TYPE, "Tailored_CV.docx")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV DOCX generation failed: {str(e)}")

@app.post("/generate/pdf/from-json")
def generate_cv_pdf_from_json_endpoint(structured_cv: StructuredCV):
    """
    Endpoint to generate an ATS-friendly CV (.pdf) directly from a provided StructuredCV JSON object.
    """
    try:
        return _file_response(create_pdf_from_structured_cv(structured_cv), "application/pdf", "Tailored_CV.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV PDF generation failed: {str(e)}")


def _check_rate_limit(client_ip: str) -> None:
    """
    Enforces a simple per-IP rate limit for apply-suggestion calls.
    Raises HTTPException 429 if the limit is exceeded.
    """
    now = time.time()
    timestamps = rate_limit_tracker.get(client_ip, [])
    # Prune timestamps outside the window
    timestamps = [t for t in timestamps if now - t < APPLY_RATE_WINDOW]
    if len(timestamps) >= APPLY_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {APPLY_RATE_LIMIT} fix requests per {APPLY_RATE_WINDOW}s."
        )
    timestamps.append(now)
    rate_limit_tracker[client_ip] = timestamps


def _make_cache_key(*parts: str) -> str:
    """
    Creates a deterministic cache key from every input that changes the result
    (suggestion, profile, job description, baseline CV, language).
    Parts are joined with a separator that cannot appear in normal text.
    """
    raw = "\x1f".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@app.post("/apply-suggestion", response_model=StructuredCV)
def apply_suggestion_endpoint(
    request: Request,
    suggestion: str = Form(...),
    job_description: str = Form(default=""),
    original_cv: str = Form(default=""),
    language: str = Form(default="English")
):
    """
    Applies a single analysis suggestion to generate an improved StructuredCV.

    The Master Profile is NOT modified. Instead, a new CV is generated that
    incorporates the specified suggestion fix.

    Includes in-memory caching (same inputs = cached result) and per-IP rate
    limiting to prevent API abuse. A plain `def` endpoint, so the Gemini wait
    runs in a worker thread.

    Args:
        request: The FastAPI Request object (for client IP).
        suggestion: The suggestion text to apply.
        job_description: Optional job description for context.
        original_cv: Optional JSON string of the current StructuredCV before fix.
        language: Target language for the CV output.

    Returns:
        StructuredCV: The improved CV with the suggestion applied.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    master_profile_data = _require_profile()

    profile_json_str = json.dumps(master_profile_data, sort_keys=True)
    cache_key = _make_cache_key(suggestion, profile_json_str, job_description, original_cv, language)
    if cache_key in suggestion_cache:
        print(f"Cache hit for suggestion: {suggestion[:50]}...")
        return StructuredCV(**suggestion_cache[cache_key])

    original_cv_data = None
    if original_cv.strip():
        try:
            original_cv_data = json.loads(original_cv)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in original_cv field.")

    try:
        result = apply_suggestion_to_cv(
            suggestion=suggestion,
            master_profile=master_profile_data,
            job_description=job_description,
            original_cv=original_cv_data,
            language=language
        )
        suggestion_cache[cache_key] = result.model_dump()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply suggestion: {str(e)}")
