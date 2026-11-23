"""
Module responsible for communicating with the Gemini AI model.
Handles prompt construction and parsing the structured response.
"""
import json
from typing import Type, TypeVar
from google import genai
from google.genai import types
from schemas import AnalysisResponse, MasterProfile, StructuredCV
from pydantic import BaseModel

# Models tried in order. When one is overloaded (503) or out of quota (429),
# the next one is used. Any other error stops right away.
MODELS = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
RETRYABLE_MARKERS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")

T = TypeVar("T", bound=BaseModel)


def _generate(prompt: str, schema: Type[T], temperature: float, task: str) -> T:
    """
    Sends a prompt to Gemini and parses the JSON answer into the given Pydantic schema.

    Tries each model in MODELS until one answers. The client reads GEMINI_API_KEY
    from the environment.

    Args:
        prompt: The full prompt text.
        schema: Pydantic model the response must match.
        temperature: Sampling temperature (low = more consistent).
        task: Short label used in logs and error messages.

    Raises:
        RuntimeError: On a non-retryable error, or when every model is busy.
    """
    client = genai.Client()
    last_error = None
    for model_name in MODELS:
        try:
            print(f"Trying model ({task}): {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature,
                ),
            )
            return schema.model_validate_json(response.text)
        except Exception as e:
            last_error = str(e)
            if any(marker in last_error for marker in RETRYABLE_MARKERS):
                print(f"Model {model_name} is busy or out of quota. Trying the next one...")
                continue
            raise RuntimeError(f"Failed to {task} with Gemini API ({model_name}): {last_error}")
    raise RuntimeError(f"All models failed due to high demand. Last error: {last_error}")


def analyze_cv(cv_text: str, job_description: str = "", master_profile: dict = None) -> AnalysisResponse:
    """
    Analyzes the CV text against the job description using Gemini API.
    Returns a structured AnalysisResponse.
    """
    
    master_profile_str = ""
    if master_profile:
        master_profile_str = f"\n\nMaster Profile (User's complete background):\n{json.dumps(master_profile, indent=2)}\n"

    if job_description.strip():
        prompt = f"""
You are an expert technical recruiter and an advanced Applicant Tracking System (ATS).
Your task is to analyze the following CV against the provided Job Description.

Job Description:
{job_description}

CV Text:
{cv_text}{master_profile_str}

Provide a detailed analysis including:
1. An ATS compatibility score (0-100) based on keyword matching, experience alignment, and overall fit.
2. A list of important keywords or skills from the Job Description that are missing in the CV.
3. Feedback specific to the CV's sections: Professional Summary, Work Experience, and Skills. If a section is missing, point it out. Focus on quantifiable achievements and clarity.
4. Specific, actionable suggestions to improve the CV for this specific job. Do not provide generic advice.
5. (If Master Profile is provided) Suggest specific experiences, projects, or certificates from the Master Profile that should be added to or swapped into the CV to better match the Job Description.

Ensure your response is highly specific to the provided CV content.
"""
    else:
        prompt = f"""
You are an expert technical recruiter and an advanced Applicant Tracking System (ATS).
Your task is to analyze the following CV and evaluate its general quality, structure, and ATS-friendliness.

CV Text:
{cv_text}{master_profile_str}

Provide a detailed analysis including:
1. An ATS compatibility score (0-100) based on general best practices, formatting, and clarity.
2. A list of general keywords or skills that are expected for the role implied by the CV but are missing.
3. Feedback specific to the CV's sections: Professional Summary, Work Experience, and Skills. If a section is missing, point it out. Focus on quantifiable achievements and clarity.
4. Specific, actionable suggestions to improve the CV. Do not provide generic advice.
5. (If Master Profile is provided) Suggest specific experiences, projects, or certificates from the Master Profile that could strengthen the CV.

Ensure your response is highly specific to the provided CV content.
"""

    return _generate(prompt, AnalysisResponse, temperature=0.2, task="analyze CV")

def extract_profile_from_cv(cv_text: str) -> MasterProfile:
    """
    Extracts structured profile information from CV text using Gemini API.
    Returns a MasterProfile object.
    """
    
    prompt = f"""
You are an expert data extractor. Your task is to extract structured information from the following CV text and map it to a Master Profile schema.
Extract basic information (including github, linkedin, portfolio if available), education, work experiences, organization/volunteer experiences, projects, publications, and certificates.
If a piece of information is missing, leave the corresponding field empty or as an empty list.

CRITICAL INSTRUCTIONS:
1. For ANY 'description' field across all sections, you MUST format the text as a list of bullet points using a hyphen and a space ('- ') for each point, separated by newlines.
   Example description format:
   - Developed a new feature
   - Increased performance by 20%
2. If extracting from JSON data, make sure to map any 'demoUrl', 'repoUrl', 'credentialUrl', or similar link fields to the corresponding 'link' or 'repo' fields in the output schema.

CV Text:
{cv_text}
"""

    return _generate(prompt, MasterProfile, temperature=0.1, task="extract profile")

def generate_cv_from_profile(job_description: str, master_profile: dict, language: str = "English") -> StructuredCV:
    """
    Generates an ATS-friendly CV structure based on the master profile and a job description.
    """
    
    prompt = f"""
You are an expert technical resume writer. Your task is to extract and tailor information from the provided Master Profile to perfectly match the Job Description below.
You must output a highly professional, ATS-friendly structured CV according to the provided JSON schema.

GROUND-TRUTH RULE (most important — violating this makes the output unusable):
The Master Profile is the ONLY source of truth about the candidate. The Job Description is exclusively a lens for choosing what to emphasize, reorder, or de-prioritize — it is NEVER a source of facts about the candidate.
- Do NOT attribute any tool, technology, language, certification, employer, location, or skill to the candidate unless it is explicitly present in the Master Profile.
- Matching a keyword from the Job Description is NOT sufficient justification to add it. If the JD mentions "GitHub Copilot" and the Master Profile does not, GitHub Copilot must NOT appear anywhere in the output — not in skills, not in summary, not in "other skills".
- You may rephrase, reframe, reorder, and select a subset of real Master Profile content to sound more relevant to the JD. You may NOT introduce new named tools/technologies/skills, invent metrics, invent responsibilities, or upgrade a "certificate/exposure" into a "proficiency" claim it doesn't support.
- If the Master Profile has a certificate or brief exposure to something (e.g. a "Prompt Engineering" course), describe it at that level of confidence — do not inflate it into "proficient in daily AI-assisted workflows" unless the Master Profile itself describes regular hands-on use.
- Before finalizing, silently self-check every skill/tool/technology term in your draft output against the Master Profile JSON. If a term cannot be located in the Master Profile, delete it or replace it with the closest true equivalent.

LOCATION HONESTY:
- Use the candidate's actual location/address exactly as given in the Master Profile's basic_info. NEVER replace it with the job's location, even if the candidate is open to relocating.
- If relocation is relevant to the JD, you may append "(open to relocation)" after the real location — do not silently substitute the job's city.

OTHER INSTRUCTIONS:
1. Tailor the Summary and select the most relevant real experiences, projects, and skills from the Master Profile to match the Job Description.
2. Ensure bullet points start with strong action verbs. Only include quantifiable achievements/metrics that are explicitly stated in the Master Profile — never fabricate numbers (%, counts, time saved, etc.).
3. Categorize the skills intelligently (e.g. "Systems & Infrastructure", "Programming Languages", "AI / ML") just like the user's template, using only categories/items grounded in the Master Profile.
4. Extract a strong Headline for the header based on the candidate's real background (e.g. "Fresh Graduate | AI Infrastructure & Systems Support") — the headline may reframe emphasis but must not claim a specialization unsupported by the Master Profile.
5. Format the header links without https:// (e.g. github.com/user).
6. Pay close attention to the candidate's education description and status. If the profile states they have "graduated", do NOT label them as a "Student" in the headline or summary. Use "Graduate", "Fresh Graduate", or a professional title.
7. CRITICAL: The ENTIRE CV output (all fields, descriptions, headings, etc.) MUST be written in the {language} language. Translate any content from the Master Profile into {language} if necessary.
8. LANGUAGE NEUTRALITY: The language parameter only changes the output language — it must NOT change which experiences, projects, or certificates are selected, the level of bullet-point detail, or the professional tone. Apply the same confident, action-verb-driven style and the same content selection criteria regardless of whether the output is in English, Indonesian, or any other language. Do NOT adopt a more humble or academic tone for non-English outputs.

Job Description:
{job_description}

Master Profile:
{json.dumps(master_profile, indent=2)}
"""

    return _generate(prompt, StructuredCV, temperature=0.15, task="generate CV")

def apply_suggestion_to_cv(
    suggestion: str,
    master_profile: dict,
    job_description: str = "",
    original_cv: dict = None,
    language: str = "English"
) -> StructuredCV:
    """
    Generates a new StructuredCV that incorporates a specific suggestion fix.

    The Master Profile remains the single source of truth. The suggestion is used
    as an instruction to Gemini for what to improve in the generated CV.
    If an original_cv is provided, Gemini will use it as a baseline and apply
    targeted modifications rather than generating from scratch.

    Args:
        suggestion: The specific suggestion text to apply.
        master_profile: The user's Master Profile data as a dict.
        job_description: Optional job description for context.
        original_cv: Optional StructuredCV dict representing the CV before fix.
        language: Target language for the CV output.

    Returns:
        StructuredCV: A new CV with the suggestion incorporated.
    """

    original_cv_section = ""
    if original_cv:
        original_cv_section = f"""
CURRENT CV (before fix):
{json.dumps(original_cv, indent=2)}

IMPORTANT: Use this current CV as the baseline. Apply ONLY the requested fix below.
Keep all other sections, wording, and structure as close to the current CV as possible.
Do NOT rewrite sections that are unrelated to the fix.
"""

    jd_section = ""
    if job_description.strip():
        jd_section = f"""
Job Description (for context):
{job_description}
"""

    prompt = f"""
You are an expert technical resume writer. Your task is to generate an improved version of a CV by applying ONE specific improvement suggestion.

GROUND-TRUTH RULE (most important — violating this makes the output unusable):
The Master Profile is the ONLY source of truth about the candidate.
- Do NOT attribute any tool, technology, language, certification, employer, location, or skill to the candidate unless it is explicitly present in the Master Profile.
- You may rephrase, reframe, reorder, and select a subset of real Master Profile content. You may NOT introduce new facts.
- Before finalizing, silently self-check every skill/tool/technology term in your draft against the Master Profile JSON. If a term cannot be located, delete it or replace it with the closest true equivalent.

LOCATION HONESTY:
- Use the candidate's actual location exactly as given in the Master Profile's basic_info.

THE SPECIFIC FIX TO APPLY:
"{suggestion}"

Apply this fix thoroughly but surgically. Only change what is necessary to address this specific suggestion. Preserve the rest of the CV structure and content.
{original_cv_section}{jd_section}
Master Profile:
{json.dumps(master_profile, indent=2)}

OUTPUT LANGUAGE: The ENTIRE CV output MUST be written in {language}.
"""

    return _generate(prompt, StructuredCV, temperature=0.15, task="apply suggestion")