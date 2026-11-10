# SPEC: Ajaia Docs (lightweight collaborative document editor)

Status: v1 spec, written with the user on Tue 10 Nov 2026. Time-boxed build, deadline about 15:30 PKT (check the portal timer).
Anything marked **OPEN** needs a decision from the user. Anything marked **VERIFY** is a belief that must be tested, not assumed.

## 1. Goal

A small Google-Docs-like web app running in the browser: sign in, create and edit rich-text documents, import files, share with other users, and have changes persist. It must be deployed at a public URL with test credentials.

Mapping to the assignment:

| Requirement | Where it is handled |
|---|---|
| Create, rename, edit, save, reopen | Sections 6, 7 |
| Rich text: bold, italic, underline, headings, lists | Section 9 |
| Upload .txt / .md / .docx into an editable doc | Section 8 |
| Sharing: owner, grant access, owned vs shared view | Sections 5, 6 |
| Persistence, validation, error handling | Sections 4, 7, 10 |
| At least one automated test | Section 11 |
| Public URL, README, architecture note, AI workflow note, video | Sections 12, 13 |

## 2. Scope

**In:**
- Email + password login with seeded demo users.
- Open sign-up (email, display name, password): anyone can create an account and is signed in at once. No email verification, no password reset. The display name may contain spaces and capitals and is shown as typed.
- Document list with two tabs: "Owned by me" and "Shared with me" (role badge, owner name).
- Rich-text editor: bold, italic, underline, headings (H1-H3), bullet and numbered lists.
- Rename document, autosave, manual save.
- Import .txt, .md, .docx as a new document. Supported types are stated in the UI and the README.
- Share by email as **viewer** or **editor**. Owner can change or remove access.
- Change detection (Section 7): if someone else saved a newer version, show a banner and let the user choose.
- Delete (owner only).

**Out (list in README under "what I'd build next"):**
- Real-time co-editing, live cursors, comments, version history, merge of conflicting edits.
- Images, tables, PDF import or export, link-based sharing, password reset, email verification.

## 3. Stack

- **Backend:** FastAPI (Python), session cookie auth, password hashing with `hashlib.scrypt`.
- **Database:** Supabase Postgres, used only as a hosted database. No Supabase Auth, no Supabase client SDK.
  - Connect directly from FastAPI via `DATABASE_URL` (use the Supabase **pooler** connection string; **VERIFY** whether the host can reach the direct connection, which may be IPv6-only).
  - Enable Row Level Security on all three tables with no policies, so Supabase's public API cannot read them. FastAPI does all permission checks.
  - Access layer: SQLAlchemy 2.0 Core. Tests run on in-memory SQLite and production on Postgres, so keep SQL portable. Run the smoke test once against real Supabase before submitting. **VERIFY**
- **Editor:** Quill 2.0.3, vendored in `static/vendor/` (no CDN, no build step). Content is exchanged as HTML.
- **Sanitizer:** `nh3` on the server (Section 9).
- **Import:** `mammoth` (.docx to HTML), `markdown` (.md to HTML), plain `.txt` is escaped into paragraphs.
- **Frontend:** plain HTML + JS + CSS served by FastAPI. No framework.
- **Tests:** pytest with FastAPI `TestClient`. Optional Playwright smoke test.
- **Deploy:** Vercel (Python runtime, the app runs as a serverless function, no Docker needed), imported from the GitHub repository. A `Dockerfile` is included for hosts that run Docker; Render's Python runtime also works. Free tiers wipe local files, which is why data lives in Supabase.

PyMuPDF was considered and rejected: Office-to-Markdown needs the paid PyMuPDF Pro add-on (3-page limit without a license), and the direction is wrong for this task.

## 4. Data model

```sql
create table users (
  id bigint generated always as identity primary key,
  email text unique not null,
  username text not null,            -- the display name, shown as typed
  password_hash text not null,
  created_at timestamptz default now()
);

create table documents (
  id bigint generated always as identity primary key,
  owner_id bigint not null references users(id),
  title text not null,
  content text not null default '',   -- sanitized HTML
  content_hash text not null,         -- sha256 hex of the sanitized HTML
  updated_by bigint references users(id),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table shares (
  document_id bigint references documents(id) on delete cascade,
  user_id bigint references users(id) on delete cascade,
  role text not null check (role in ('viewer','editor')),
  primary key (document_id, user_id)
);

-- names are unique ignoring case ("Bob" and "bob" are the same name)
create unique index users_username_lower_idx on users (lower(username));

alter table users enable row level security;
alter table documents enable row level security;
alter table shares enable row level security;
```

Rules: exactly one owner per document (`owner_id`). `shares` lists only people the document was shared with. Emails are stored and compared in lowercase. Display names are stored as typed and compared ignoring case. The app creates the index itself at start-up (`CREATE UNIQUE INDEX IF NOT EXISTS`), so a database made before the rule gets it too.

## 5. Permissions

| Action | Owner | Editor | Viewer | No access |
|---|---|---|---|---|
| Open / read | yes | yes | yes | 404 |
| Edit content, rename | yes | yes | 403 | 404 |
| Delete | yes | 403 | 403 | 404 |
| View / change shares | yes | 403 | 403 | 404 |

Users without access get **404, not 403**, so the API never reveals that a document exists. Every endpoint checks permission server-side; hiding buttons in the UI is not security.

## 6. API

All JSON under `/api`. Errors always return `{"detail": "human readable message"}`.

| Method + path | Purpose |
|---|---|
| `POST /api/register` `{email, username, password}` | Create an account and start a session (201). 400 for invalid input, 409 if the email or name is taken. |
| `POST /api/login` `{email, password}` | Start session. 401 on bad credentials. |
| `POST /api/logout`, `GET /api/me` | End session, current user. |
| `GET /api/documents` | `{owned: [...], shared: [...]}` with title, preview, updated_at, role, owner name, share count. |
| `POST /api/documents` `{title?}` | Create an empty document owned by the caller. |
| `GET /api/documents/{id}` | Full document: title, content, content_hash, role, can_edit, updated_by, updated_at. |
| `GET /api/documents/{id}/meta` | `{content_hash, updated_at, updated_by}`. Used for polling. |
| `PATCH /api/documents/{id}` `{title?, content?, base_hash?}` | Save. See Section 7. |
| `DELETE /api/documents/{id}` | Owner only. |
| `GET /api/documents/{id}/shares` | Owner only. |
| `PUT /api/documents/{id}/shares` `{email, role}` | Grant or change access. Owner only. 404 for unknown email, 400 for sharing with yourself. |
| `DELETE /api/documents/{id}/shares/{email}` | Remove access. Owner only. |
| `POST /api/import` (multipart file) | Convert, sanitize, create a new document, return its id. |
| `GET /healthz` | Health check. |

## 7. Saving and change detection (core logic)

The browser keeps `base_hash`, the hash of the version it loaded or last saved.

On `PATCH` with `content`:

1. Sanitize the HTML (Section 9), compute `new_hash`.
2. Load the current row.
3. If `new_hash == current.content_hash` then **do nothing**. Return the current hash. Repeated saves with no edits change nothing.
4. Else if `base_hash` is provided and `base_hash != current.content_hash` then **409 conflict**. The response includes `current` (content, content_hash, updated_by name, updated_at) so the browser can show the difference without another request.
5. Else update content, content_hash, updated_by, updated_at in one statement with `WHERE content_hash = :base_hash` (compare-and-swap, so two simultaneous saves cannot both win). Return the new hash. The browser sets `base_hash` to it.

If `base_hash` is omitted, the save is an intentional overwrite ("keep mine"). The browser sends `base_hash = current.content_hash` from the 409 response, so it still goes through step 5.

Browser behaviour:
- Autosave 1 second after the last keystroke, only if the content actually changed (dirty flag). Ctrl+S saves immediately. Show "Saving...", "Saved", or the error.
- Poll `GET /meta` every 10 seconds. If `content_hash` differs from `base_hash`, show a banner: "{name} edited this document at {time}."
- Banner choices: **Load their version** (replace the editor content), **Keep mine and overwrite** (resend as above), **Download my copy** (.html of the local text).
- If the user has unsaved edits when the banner appears, autosave pauses until they choose.
- "What changed": the browser diffs its own old copy against the new text and highlights added and removed passages. Start with a simple text diff; skip if time runs short.
- Renames are a separate small update; last write wins.

README wording: "Change detection with a choice, not real-time collaboration."

## 8. Import

- Accepted: `.txt`, `.md`, `.docx`. Maximum 2 MB. Anything else returns 415 with a clear message. Empty files return 400. Corrupt or fake `.docx` returns 400. A `.docx` that expands past 20 MB uncompressed is rejected (zip-bomb guard).
- Conversion produces HTML, which then goes through the same sanitizer as saves. The result becomes a **new** document titled from the filename.
- Not supported (state in README and UI hint): images, tables, comments, tracked changes, headers and footers. mammoth drops what it cannot map and returns warnings, which are shown to the user.
- Text decoding: UTF-8 (with BOM), then UTF-16, then Latin-1 fallback.

## 9. HTML sanitization (the security boundary)

The server never stores or returns unsanitized HTML. Allowed tags: `p, br, h1, h2, h3, strong, em, u, ul, ol, li, a`. Allowed attribute: `href` on `a`, restricted to `http`, `https`, `mailto`. Everything else is removed, including scripts, event handlers, styles, iframes and images. Size limit 500,000 characters.

The editor reads and writes HTML via `quill.getSemanticHTML()` and `quill.clipboard.dangerouslyPasteHTML()`. **VERIFY** with a test that bold, italic, underline, H1-H3, bullet and numbered lists survive: editor to server to database to editor. If Quill's HTML uses attributes such as `data-list` that the sanitizer strips, adjust the allow-list or the conversion until the round trip is correct.

Also set `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, and session cookie `HttpOnly`, `SameSite=Lax`, plus `Secure` in production.

## 10. Validation and error handling

- Title: trimmed, 1-200 characters.
- Content: sanitized, at most 500,000 characters.
- Share role: `viewer` or `editor` only.
- Sign-up: email trimmed and lowercased, a simple `x@y.z` shape check, at most 254 characters. Display name (sent as `username`): runs of spaces collapsed, 2-30 characters, letters of any language, digits, spaces and `. _ - '`, at least one letter or digit, capitals kept. Password 8-128 characters (not trimmed).
- Login failures say "Wrong email or password" and nothing more.
- The UI shows every API error message in a visible message area. No silent failures. Network errors show "Could not reach the server".
- Viewers see a read-only editor (toolbar hidden or disabled) and a "View only" badge.

## 11. Tests

Minimum (pytest): save then reopen returns the same content. Better, in priority order:
1. Permission matrix: viewer cannot edit, editor can, stranger gets 404, only owner can share or delete.
2. Save semantics: identical content causes no change, stale `base_hash` gives 409, overwrite works.
3. Sanitizer: script tags and `javascript:` links are removed, allowed formatting survives.
4. Import: a txt, an md and a docx work; wrong type gives 415; oversize gives 413.

## 12. Deployment and secrets

Environment variables: `DATABASE_URL`, `SECRET_KEY` (random, stable), `COOKIE_SECURE=1`, `SEED_PASSWORD`. Never commit `.env`. The app creates tables and seeds demo users on first start if empty.

Seeded demo users (password from `SEED_PASSWORD`, document it in the README):
- `alice@example.com`, `bob@example.com`, `carol@example.com`
- Welcome document owned by Alice, shared with Bob (editor) and Carol (viewer). A second document owned by Bob, shared with Alice (editor).

Vercel settings: import the GitHub repository. Vercel finds `app/main.py` (the `app` instance), installs `requirements.txt` and reads the Python version from `.python-version`. Environment variables: `DATABASE_URL`, `SECRET_KEY`, `SEED_PASSWORD`, `COOKIE_SECURE=1`, set in the project settings and never committed. Start-up work (tables, index, seed check) runs on each cold start. Keep the function region close to the Supabase region (see ARCHITECTURE.md, "Performance"). The `Dockerfile` listens on `$PORT` (default 7860) as user 1000 for Docker hosts; a Docker Space on Hugging Face needs a paid plan, and Render asked for a card, so neither was used.

## 13. Deliverables checklist

Google Drive folder (shared "anyone with the link") containing:
- [x] Source code (https://github.com/Copperhorse/ajaia-docs)
- [x] `README.md` (what it does, supported file types, run locally, run tests, demo logins, known limits)
- [x] Architecture note (`ARCHITECTURE.md`)
- [ ] AI workflow note (`AI_WORKFLOW.md`, written by the user in their own words, see that file)
- [ ] `SUBMISSION.md` (what works, what is partial, what I'd build next). Drafted; the live URL, demo password and video link still need filling in.
- [ ] Live URL and test credentials
- [ ] A text file containing the video URL

Also: a 3-5 minute walkthrough video (public Loom or YouTube) and the Markdown submission in the portal (maximum 1000 lines) plus the video link field.

Walkthrough order: log in as Alice, create and format a document, import a file, share with Bob as editor; log in as Bob (second window), see it under "Shared", edit it, see the change banner as Alice; show a viewer (Carol) cannot edit; run the tests; explain what AI did and what I decided.

## 14. Build order and time budget (PKT)

| Slot | Step |
|---|---|
| 12:00 | Supabase project, run the SQL, RLS on, copy pooler URL to `.env` |
| 12:15 | Backend core: DB layer, auth, documents CRUD, sanitizer, hash save, shares |
| 13:15 | Tests for permissions and save semantics |
| 13:45 | Frontend: login, list with tabs, editor, autosave, share dialog |
| 14:30 | Import, change banner |
| 14:50 | Deploy on Vercel, smoke test on the live URL |
| 15:05 | README, ARCHITECTURE, SUBMISSION, AI_WORKFLOW, Drive folder |
| 15:15 | Record and upload video, submit |

If behind schedule, cut in this order: diff highlighting, "Download my copy", Playwright test, polish. Never cut: persistence, sharing, permissions checks, one automated test, the live URL, the video.

## 15. Decisions (all settled)

- Sharing is by **email**.
- Host: **Vercel**. Render needed a card and a Hugging Face Docker Space needs a paid plan, so neither was used. The `Dockerfile` stays for Docker hosts.
- Database: **Supabase Postgres** (SQLite only for tests and local development).
- Account creation: **open sign-up** (added after the first version of this spec).

## 16. Known limitations (copy into README)

Open sign-up has no email verification, CAPTCHA or rate limiting, so anyone with the link can create accounts. Last-save protection and change notification, not real-time editing or merging. No version history. Free-tier hosting can sleep and take about a minute to wake. Imports keep basic formatting only.
