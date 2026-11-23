# Security & Data Safety Fixes

Changes made after a code audit. Each item says what changed and why.

## CORS allow-list (`backend/main.py`)

The API used to accept browser requests from any website (`allow_origins=["*"]`).
Because the API has no login, any page the user visited while the backend was running
could read and overwrite the Master Profile and spend the Gemini quota.

Now only the local frontend is allowed: `http://localhost:5173` and `http://127.0.0.1:5173`.
If the frontend runs on another address, set `ALLOWED_ORIGINS` in `backend/.env`
as a comma-separated list, for example:

```
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

## Docker ports bound to localhost (`docker-compose.yml`)

Ports are now published as `127.0.0.1:8000` and `127.0.0.1:5173`, so other devices on
the same network can no longer reach the app.

## Safe Master Profile read/write (`backend/main.py`)

- `GET /profile` now returns **500** with a clear message if `master_profile.json`
  exists but cannot be parsed. Before, it silently returned an empty profile, and saving
  from the UI would overwrite the real file with empty data.
- `POST /profile` writes to `master_profile.json.tmp` and then swaps it in with
  `os.replace`, so a crash mid-write cannot leave a half-written file.
- The file is saved as UTF-8 without `\u` escapes, so it stays readable when edited by hand.

## Unicode text in PDF output (`backend/pdf_generator.py`)

The PDF generator used the built-in Times font, which only supports Latin-1, and
silently dropped every other character (`Nguyễn` became `Nguyn`).

It now embeds **Liberation Serif** (metric-compatible with Times New Roman) from
`backend/fonts/`. It covers Latin (including Vietnamese, Polish, Turkish, etc.),
Greek and Cyrillic. Chinese, Japanese and Korean are still not covered.
The font is licensed under the SIL Open Font License; see
`backend/fonts/LICENSE-LiberationFonts`.

## Tests

Regression tests live in `backend/tests/`. Run them with:

```bash
cd backend
uv pip install pytest httpx
.venv/Scripts/python -m pytest tests    # Windows
.venv/bin/python -m pytest tests        # macOS/Linux
```
