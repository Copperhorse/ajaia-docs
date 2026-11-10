# Ajaia Docs

A small Google-Docs-style web app: sign in, write rich-text documents, import files, share them with other people, and keep working when someone else edits the same document.

Built for the Ajaia take-home assessment (Junior AI Engineer). FastAPI + Postgres on the back, plain HTML/CSS/JS and the Quill editor on the front.

- **Live demo:** `<LIVE_URL>` (see [SUBMISSION.md](SUBMISSION.md) for the demo password)
- **How it is built:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Spec the work followed:** [SPEC.md](SPEC.md)

## What it does

- **Accounts:** email + password sign-in, and open sign-up (email, display name, password). Names can have spaces and capitals; two names that differ only by capitals count as the same.
- **Documents:** create, rename, edit, delete. Everything autosaves one second after you stop typing, and `Ctrl+S` saves at once.
- **Rich text:** headings 1-3, bold, italic, underline, bulleted and numbered lists.
- **Import:** turn a `.txt`, `.md` or `.docx` file into a new, editable document.
- **Sharing:** the owner shares by email as **viewer** or **editor**, changes a role, or removes access. The list has two tabs, "Owned by me" and "Shared with me", with a role badge on every card.
- **Change detection, not real-time editing:** while you edit, the page checks every 10 seconds whether someone else saved a newer version. If so, a banner names who and when, autosave pauses, and you choose: **Load their version**, **Keep mine and overwrite**, or **Download my copy**.
- **Permissions are checked on the server.** A user with no access to a document gets a 404, as if it did not exist.

## Supported import files

| Type | Result | Notes |
|---|---|---|
| `.txt` | Paragraphs (blank line = new paragraph) | UTF-8, UTF-16 with a byte-order mark, or Latin-1 |
| `.md` | Headings, bold, italic, lists, links | Raw HTML inside the Markdown is cleaned, not kept |
| `.docx` | Headings, bold, italic | Converted with mammoth; warnings are shown after import. **Underline is dropped** (mammoth's default). Lists and links are passed through by mammoth, but I have only tested `.docx` files I built by hand, not real Word documents. |

Limits: 2 MB per file, 500,000 characters per document. **Not imported:** images, tables, comments, tracked changes, headers and footers. Any other file type is refused with a clear message.

## Demo accounts

The first start creates three users and two documents when the database is empty:

| Email | Role in the demo |
|---|---|
| `alice@example.com` | Owns "Welcome", shared with Bob (editor) and Carol (viewer) |
| `bob@example.com` | Owns "Bob's notes", shared with Alice (editor) |
| `carol@example.com` | Viewer of "Welcome" |

All three use the password you set in `SEED_PASSWORD`. It is not stored in this repository.

Quick tour: sign in as Alice in one window and as Bob in another (a private window works). Edit "Welcome" in both and watch the change banner appear. Open "Welcome" as Carol to see the read-only view.

## Run it locally

Needs Python 3.14 (see `.python-version`).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root (it is git-ignored):

```bash
SECRET_KEY=<a long random string>
SEED_PASSWORD=<the password for the three demo users>
# DATABASE_URL=postgresql://...    leave this out to use a local SQLite file (dev.db)
# COOKIE_SECURE=1                  set this when serving over HTTPS
```

Make a secret key with `python -c "import secrets; print(secrets.token_hex(32))"`. Then:

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000. Tables are created and the demo data is seeded on first start.

| Variable | Needed | Meaning |
|---|---|---|
| `DATABASE_URL` | No | Postgres connection string. Without it the app uses `./dev.db` (SQLite). |
| `SECRET_KEY` | Yes in production | Signs the login cookie. If missing, a random key is used and everyone is signed out on each restart. |
| `SEED_PASSWORD` | On the first start with an empty database | Password for the demo users. The app refuses to start an empty database without it. |
| `COOKIE_SECURE` | In production | Set to `1` so the login cookie is only sent over HTTPS. |

## Run the tests

```bash
pytest -q
```

76 tests, about 5 seconds. They run on in-memory SQLite, and `tests/conftest.py` forces that, so they can never touch the database in `DATABASE_URL`. They cover:

- sign-in, sign-up and sessions
- the permission matrix (owner / editor / viewer / stranger)
- save semantics: identical content changes nothing, a stale hash gives 409, overwrite works
- the HTML sanitizer, password hashing and the import rules (types, sizes, corrupt files, zip bombs)

The in-browser behavior (editor, autosave, banner, dialogs) was checked with a scripted Firefox run during development. That script is **not** part of this repository.

## Deploy (Vercel with Supabase)

The database lives in Supabase and the app runs as a Vercel function. Both have free plans that need no credit card (check at sign-up, as providers change their rules).

**1. Supabase.** Create a project and copy the **pooler** connection string (Project settings, Database). Use the pooler URL: the direct connection can be IPv6-only. The app creates its three tables on first start and turns on Row Level Security for them, so there is no SQL to run.

**2. Vercel.** Sign in with GitHub, then Add New, Project, and import this repository. Vercel detects FastAPI by itself: it finds `app/main.py`, installs `requirements.txt` and reads the Python version from `.python-version` (3.14). No Dockerfile or build settings are needed.

**3. Environment variables** (Project settings, before the first deploy): `DATABASE_URL` (the Supabase pooler string), `SECRET_KEY`, `SEED_PASSWORD`, and `COOKIE_SECURE` = `1`. Never put these in the repository.

**4. Deploy,** then open the `*.vercel.app` address. The first request creates the tables and the demo users, so it is slow.

Good to know:
- Vercel runs the app as a serverless function. Start-up (tables, index, "are there users?") runs again whenever a new instance starts, so the first visit after a quiet period is slower than the rest.
- **Region matters.** Every request makes several database round trips. Keep the function region close to the Supabase region, or pages take 1.5-2 seconds (see "Performance" in ARCHITECTURE.md). Check the function region in the Vercel project settings.
- Each open editor asks the server for changes every 10 seconds, and each of those is a function call.
- Not tested on Vercel before deployment: this was written from Vercel's documentation.

**Other hosts.** The included `Dockerfile` runs the app anywhere Docker runs: it listens on port 7860 (or `$PORT`) as user 1000, which is what a Hugging Face Space expects. A Docker Space on Hugging Face needs a paid plan, so it was not used. A Render web service also works: build command `pip install -r requirements.txt`, start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, the same environment variables.

## Project layout

```
app/        FastAPI backend (main, auth, documents, sharing, importers, sanitize, security, seed, db)
static/     The frontend: index.html, app.js, style.css, and Quill 2.0.3 in vendor/
tests/      pytest suite
SPEC.md     The plan this was built from
```

## Known limits

- **No real-time co-editing.** Two people can edit at once, but the second save is stopped and the person chooses what to keep. There is no merge and no version history.
- **No "what changed" highlighting** in the change banner. The banner says who and when, not which words.
- **Open sign-up with no email verification, CAPTCHA or rate limiting.** Anyone with the link can create accounts. There is no password reset.
- **Import keeps basic formatting only** (see the table above).
- **Speed depends on where the database is.** See ARCHITECTURE.md.
- Tested in Firefox only.

## What I would build next

- Real-time collaboration (shared cursors, merging of simultaneous edits) and a version history to go back to.
- A "what changed" view in the banner.
- Tables, images and comments; PDF import and export; share links.
- Email verification and password reset, with rate limiting on sign-up and sign-in.
- Fewer database round trips per request.
- A browser test suite (for example Playwright) kept in the repository.
