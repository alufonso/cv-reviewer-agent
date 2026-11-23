# Backend & Frontend Cleanup (Stage 2)

Second round of audit fixes: responsiveness, error messages, caching, and removing duplicate or unused code.

## Server no longer freezes during Gemini calls (`backend/main.py`)

Endpoints were declared `async def` but called the Gemini SDK synchronously. That blocked
the event loop, so for 10–60 seconds per AI call no other request (not even `GET /profile`)
was answered.

- Endpoints that do not need `await` are now plain `def`. FastAPI runs them in a worker thread.
- `/analyze` and `/profile/extract` stay `async` (they `await` the upload) and run the Gemini
  call with `await run_in_threadpool(...)`.

Test: `test_slow_gemini_call_does_not_block_other_requests`.

## One Gemini helper (`backend/analyzer.py`)

The "try the next model when busy" loop was copied four times. It is now one function,
`_generate(prompt, schema, temperature, task)`, and the model list is one constant, `MODELS`.
Behaviour is unchanged: 503/429 errors try the next model, any other error stops immediately.

## One profile loader (`backend/main.py`)

The code that reads `master_profile.json` was copied six times. It is now `_read_profile_dict()`
(returns `None` if no profile is saved, 500 if the file is broken) and `_require_profile()`
(400 if no profile is saved). `/analyze` now also reports a broken file instead of silently
ignoring it.

## Apply-suggestion cache key (`backend/main.py`)

The cache key ignored the baseline CV and the output language, so a repeated Fix could return
a result built from an older baseline. The key now includes suggestion, profile, job description,
baseline CV and language.

## Removed unused endpoints

`POST /generate/docx` and `POST /generate/pdf` were not called by the frontend (it always uses
`/generate/preview` followed by `/generate/{docx,pdf}/from-json`). They are removed, together
with the unused `generateCV` function in `frontend/src/services/api.js`.

## Frontend error messages (`frontend/src/services/api.js`)

- The three copies of the "download a file" code are one helper, `downloadFile`.
- Download errors now show the backend's real reason. Before, the `throw` sat inside its own
  `try`, so the message was always replaced with a generic one.
- `getProfile` now passes on the backend's message (for example, a broken profile file).

## Saving blocked when the profile failed to load (`frontend/src/components/MasterProfile.jsx`)

If loading the profile failed, the page kept an empty placeholder profile, and Save or
Import → Merge would overwrite the real file with it. Saving is now refused until the
profile loads successfully.
