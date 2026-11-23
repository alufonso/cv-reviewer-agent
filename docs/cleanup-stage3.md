# Small Cleanups (Stage 3)

Last round of audit fixes. No new features.

## Empty "Languages & Other Skills" section (`backend/docx_generator.py`, `backend/pdf_generator.py`)

`StructuredCV.languages_other` is always an object, so `if cv_data.languages_other:` was always true.

- DOCX printed the heading plus empty `Languages:` and `Other Skills:` lines.
- PDF printed the heading with nothing under it.

Both generators now print the section only if at least one line has text, and print each line
only when it is filled. Tests: `backend/tests/test_stage3.py`.

## Removed unused dependencies (`frontend/package.json`)

`clsx`, `tailwind-merge`, `autoprefixer` and `postcss` were installed but never imported.
Tailwind CSS v4 runs through `@tailwindcss/vite` and does not need PostCSS or Autoprefixer.

## Removed unused imports

- `AnimatePresence` in `frontend/src/components/ImportReviewer.jsx`
- `os` in `backend/list_models.py`
- `Optional` in `backend/schemas.py`

## Running tests from anywhere

`backend/pytest.ini` sets the import path, so tests run both from `backend/`
(`pytest`) and from the repo root (`pytest backend/tests`).
