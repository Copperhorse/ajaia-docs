# CLAUDE.md

Project: **Ajaia Docs**, a lightweight collaborative document editor built for a timed take-home assessment (Ajaia, Junior AI Engineer). Read `SPEC.md` first. It is the source of truth for scope, data model, API and build order. If code and spec disagree, ask the user which is right, then update the spec.

## How to work with this user

- The user (Copper) must understand, verify and present every part of this code in a video. Keep code simple and small. Prefer boring, readable code over clever code.
- Go **one milestone at a time** (SPEC section 14). Before each milestone, say in two or three sentences what you are about to build and why. After it, say how to check it works. Do not build ahead.
- Explain briefly in plain English. No walls of text. Reply in English only.
- Separate what you verified (ran it, saw output) from what you assume. Say so explicitly.
- Do not add features, dependencies or files that are not in the spec without asking.
- Never invent results. If a test was not run, say it was not run.
- The assignment evaluates honest AI use. Tell the user when you made a non-obvious choice so they can record it in `AI_WORKFLOW.md`.

## Stack (details in SPEC.md)

FastAPI + SQLAlchemy 2.0 Core + Supabase Postgres (tests on SQLite), Quill 2.0.3 vendored in `static/vendor/`, HTML content sanitized with `nh3`, imports via `mammoth` / `markdown`, tests with pytest.

## Commands

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # run locally
pytest -q                                      # run tests
```

Environment (`.env`, never committed): `DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE`, `SEED_PASSWORD`.
If `DATABASE_URL` is unset, fall back to a local SQLite file for development.

## Rules that matter

- Content is HTML, sanitized on the server before it is stored or returned. Never render user HTML without that.
- Permission checks happen on the server for every endpoint. Users without access get **404**.
- Saves use the content-hash compare-and-swap in SPEC section 7. No version counter.
- Errors are `{"detail": "message"}`. The UI must show them.
- Passwords: scrypt from the standard library. Never log or return password hashes.
- Do not commit secrets or `.env`. Do not put real credentials in docs.

## Status

The backend (`app/`), the frontend (`static/`, Quill 2.0.3 vendored), `tests/` (72 pytest tests), `README.md`, `ARCHITECTURE.md` and a draft `SUBMISSION.md` are written. See ARCHITECTURE.md for how the pieces fit.

Not done yet: deployment on Render and its smoke test, `AI_WORKFLOW.md` (the user writes it in their own words), the demo video.

Deployment: Render builds from the GitHub repo (no Docker, no Dockerfile). Build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

Leftover from the `uv init` scaffold: `pyproject.toml` and `src/text_editor/` are unused by the app.

## Definition of done for a milestone

It runs, the relevant tests pass, and the user has seen it work. Update the checklist in SPEC section 13 when deliverables are finished.
