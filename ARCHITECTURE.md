# Architecture

Ajaia Docs is one FastAPI service that serves a small single-page frontend and a JSON API, backed by Postgres. There is no build step and no frontend framework.

```
 Browser (static/app.js, Quill 2.0.3)
    |   JSON over HTTPS, signed session cookie
    v
 FastAPI  --  middleware: signed session, security headers
    |         routers: documents, sharing, import   (+ auth routes in main.py)
    |         every route: who is this user, and may they do this?
    v
 SQLAlchemy 2.0 Core  -->  Postgres (Supabase)  /  SQLite (tests, local dev)
```

## Backend modules

| Module | Responsibility |
|---|---|
| `app/main.py` | App setup, session and security-header middleware, `login`, `logout`, `register`, `me`, `healthz`, serves the frontend |
| `app/auth.py` | `current_user`: reads the user id from the session cookie, loads the user, or answers 401 |
| `app/documents.py` | Create, list, open, save (with change detection), rename, delete, and the `meta` endpoint used for polling. Holds `load_document`, the one permission check |
| `app/sharing.py` | List, add or change, and remove shares. Owner only |
| `app/importers.py` | Upload handling and the `.txt`, `.md`, `.docx` converters |
| `app/sanitize.py` | The HTML allow-list and the content hash |
| `app/security.py` | scrypt password hashing and verification |
| `app/seed.py` | Demo users and documents, created only when the database is empty |
| `app/db.py` | Table definitions, engine setup, and `init_db()` |

## Data model

Three tables (`app/db.py`, mirrored in SPEC section 4):

- **users**: `id` (the primary key), `email` (unique, lowercase), `username` (the display name, shown as typed), `password_hash`. Names are unique ignoring case through a unique index on `lower(username)`. People sign in and are found for sharing by email; the name is only what other people see.
- **documents**: `id`, `owner_id`, `title`, `content` (sanitized HTML), `content_hash` (sha256 of that HTML), `updated_by`, `created_at`, `updated_at`. One owner per document.
- **shares**: `(document_id, user_id)` primary key and `role` (`viewer` or `editor`, enforced by a check constraint). Rows are deleted with their document or user (`ON DELETE CASCADE`).

On Postgres the app also enables Row Level Security on all three tables with no policies. Supabase exposes its own public API over the database; with RLS on and no policies, that API can read nothing. Only this service, which connects directly, can use the tables, and it does all the permission checks itself.

`init_db()` creates that index with `CREATE UNIQUE INDEX IF NOT EXISTS`, because `create_all` skips tables that already exist and a database made earlier (such as an existing Supabase project) would otherwise never get it. The case comparison uses the database's `lower()`, so for non-English letters it is only as good as the database's locale: Postgres on UTF-8 handles them, SQLite (tests and local use) only lowercases A-Z.

Identifiers are `bigint` on Postgres and `integer` on SQLite (SQLite only auto-numbers `INTEGER` keys). Everything else is portable SQL, so the same code runs on both.

## Accounts and sessions

- **Passwords** are hashed with scrypt from the Python standard library (N=2^14, r=8, p=1, 16-byte random salt) and stored as `scrypt$N$r$p$salt$hash`. Hashes are never returned or logged.
- **Sign-in** answers "Wrong email or password" for both an unknown email and a wrong password. For an unknown email it still hashes against a dummy value, so the two cases take about the same time.
- **Sessions** are Starlette's signed cookie (`session`): `HttpOnly`, `SameSite=Lax`, `Secure` when `COOKIE_SECURE=1`, valid 7 days. It holds only the user id (not the email or any role), and the user is looked up again on every request, so nothing in the cookie can go stale.
- **Sign-up** (`POST /api/register`) validates input, stores the hashed password and signs the user in. It is open to anyone. See the limits below.

## Permissions

`load_document(conn, doc_id, user)` is the single gate used by every document endpoint. It returns the document and the user's role, or a 404.

| Action | Owner | Editor | Viewer | No access |
|---|---|---|---|---|
| Open / read | yes | yes | yes | 404 |
| Edit content, rename | yes | yes | 403 | 404 |
| Delete | yes | 403 | 403 | 404 |
| View or change shares | yes | 403 | 403 | 404 |

A document the user cannot see and a document that does not exist give the identical 404 message, so the API never reveals that a document exists. The frontend hides buttons the user cannot use, but that is only tidiness: the server decides.

## Content: sanitized HTML

Documents are stored as HTML, not Markdown or Quill's Delta format. Markdown has no underline, and Delta would tie the database to one editor.

- **The editor** (Quill) reads and writes HTML through `getSemanticHTML()` and `clipboard.convert()`. Quill writes every space as `&nbsp;`, which never wraps, so the frontend turns lone `&nbsp;` back into normal spaces before saving and keeps runs of two or more.
- **The server never stores or returns unsanitized HTML.** `nh3` keeps only `p br h1 h2 h3 strong em u ul ol li a`, and only `href` on `a`, limited to `http`, `https` and `mailto`. Scripts, event handlers, styles, iframes and images are removed. The limit is 500,000 characters.
- **The frontend inserts text as text.** A small `el()` helper builds all DOM, and no code path uses `innerHTML`. A test fails if `app.js` ever does.
- **Response headers** set a Content Security Policy (`default-src 'self'`, no inline scripts) and `X-Content-Type-Options: nosniff`.

## Saving and change detection

This is the core logic (`save_document` in `app/documents.py`; the browser half is `startAutosave` in `static/app.js`).

Every document row carries `content_hash`, the sha256 of its sanitized HTML. The browser remembers `base_hash`: the hash of the version it loaded or last saved.

**On a save with content:**

1. Sanitize the HTML and compute its hash.
2. Load the current row.
3. If the new hash equals the stored hash, **do nothing** and return the current hash. Saving without edits changes nothing, not even `updated_at`.
4. Else, if `base_hash` was sent and differs from the stored hash, someone else saved in between: answer **409** with their version (content, hash, who, when).
5. Else write the row with `WHERE content_hash = <the hash we read>`. This compare-and-swap means two simultaneous saves cannot both succeed: the loser updates zero rows and also gets a 409.

A save without `base_hash` is an intentional overwrite. Renames are separate and last-write-wins.

**In the browser:**

- A dirty flag marks real edits. Autosave runs one second after the last keystroke, only if something changed. `Ctrl+S` saves immediately.
- Every 10 seconds the page asks `GET /documents/{id}/meta` for the current hash. If it differs from `base_hash`, a banner shows who saved and when, and **autosave pauses**.
- A refused save (409) opens the same banner immediately, using the version the 409 carried.
- The poll skips background tabs. If it gets a 401 or 404 (the session ended, or the document was deleted or unshared) it stops for good and shows the error where the text is being edited, so nothing typed is lost. The `meta` endpoint reads only the hash and timestamps, not the document text.
- The banner's choices: **Load their version** (replace the editor with the server's text, adopt its hash), **Keep mine and overwrite** (adopt their hash as the base, mark my text dirty, save), **Download my copy** (an `.html` file of my text).
- A poll answer is ignored if one of the browser's own saves finished while it was in flight, since that answer describes the version from before the save. Without this rule, your own save could raise a false banner.
- Leaving the page flushes pending edits. If a save then fails, the error is shown on the next page instead of disappearing.

I chose a content hash over a version counter because a counter changes even when nothing did, which would make "Save" with no edits look like a change to other people.

## Import

`POST /api/import` accepts one file. The order of checks is: type by extension (415), size up to 2 MB (413), empty (400), convert, sanitize, size of the result (413), and "no text found" (400).

- `.txt`: decoded as UTF-8 (with or without a BOM), UTF-16 only if it starts with a BOM, otherwise Latin-1. Text is escaped and split into paragraphs.
- `.md`: converted with `markdown`, then sanitized like everything else.
- `.docx`: the zip is inspected first and refused if its declared uncompressed size exceeds 20 MB (a zip-bomb guard); then converted with mammoth. Images are dropped on purpose, because base64 images would blow the size limit before sanitizing. Mammoth's warnings are returned and shown to the user.

The result becomes a new document owned by the importer, titled from the file name.

## Frontend

`static/app.js` (plain JavaScript, no framework) is a single page with hash routes: `#/` is the list and `#/doc/<id>` is the editor. Main pieces: `api()` (JSON and file uploads, turns server errors into messages), `el()` (safe DOM builder), the sign-in/sign-up card, the list with its two tabs, the editor page, `startAutosave()`, the share dialog (the native `<dialog>` element) and the owner's delete control.

Quill 2.0.3 is vendored in `static/vendor/` (no CDN) with its licence; its sha512 was checked against the npm registry. The look follows the "Clara" design system (near-black ground, one peach accent, glass surfaces) with one deliberate change: corners are squarer than Clara's pills. Three sizes in `style.css` (`--radius` 8px, `--radius-control` 6px, `--radius-small` 4px) control every corner, so the look can be tuned in one place.

Errors always come back as `{"detail": "message"}` and the UI always shows them. A 401 sends the user back to sign-in.

## Decisions and trade-offs

| Decision | Why | Cost |
|---|---|---|
| HTML as the stored format, sanitized on the server | Keeps underline, works with imports, no lock-in to Quill's Delta | The sanitizer is a security boundary that must stay strict; Quill's `&nbsp;` needs a workaround |
| Content hash + compare-and-swap, not a version counter | Detects real changes only; no lost updates | No merge: the user chooses between versions |
| Polling every 10 s, not websockets | Simple, works on a free host, nothing to keep open | A change is noticed up to 10 s late |
| Change detection with a choice, not real-time co-editing | Honest scope for a timed build | Two people can still conflict |
| SQLAlchemy Core, not the ORM | Small, readable SQL; portable between SQLite and Postgres | More explicit queries |
| Supabase used only as hosted Postgres (no Supabase Auth or SDK) | One auth system I control and can explain | I own password handling |
| 404 for "no access", 403 for "known but not allowed" | Never reveals that a document exists | Slightly less obvious errors |
| Plain HTML/CSS/JS, vendored Quill | No build step; fast to review | Hand-rolled DOM code |
| Open sign-up | Reviewers can create their own accounts | No verification or rate limiting (see limits) |

## Testing

- **72 pytest tests** on in-memory SQLite (`pytest -q`). `tests/conftest.py` forces the in-memory database and resets it before every test, so tests are isolated and can never reach a real database.
- **Browser behavior** was checked with a scripted Firefox run: sign-in and sign-up, creating, renaming and saving, autosave debouncing, `Ctrl+S`, the change banner with a simulated second user, sharing, import, delete and the viewer mode. That harness lives outside the repository.
- The API was also exercised against the real Supabase database (create, save, conflict, share, delete), using temporary documents that were removed afterwards.

## Performance

Measured once, from a development machine to a Supabase database in Tokyo through its pooler (median of 8-15 runs per endpoint). The same code on local SQLite takes 1-5 ms per request (28 ms for sign-in, which is the password hash).

| Request | SQL queries | Against Supabase |
|---|---|---|
| Sign-in | 1 | 0.67 s |
| Document list | 3 | 1.7 s |
| Open a document | 4 | 2.0 s |
| Autosave (changed content) | 4 | 1.7 s |
| Poll (`/meta`, every 10 s) | 3 | 1.75 s |

A bare `SELECT 1` took about 0.2 s, so the database round trip dominates. One request costs more than its query count because of connection checks: with `pool_pre_ping` on, a request paid roughly one extra round trip, and turning it off saved about 0.3 s in a test. The numbers are noisy (the same round trip read 0.2 s in one run and 0.36 s in another).

What helps most is **running the app in a region close to the database**. Fewer queries per request (for example joining the owner and author names into one query) would help too. Neither optimization is implemented yet.

## Known limits

- No real-time editing, no merge, no version history.
- No "what changed" view in the change banner.
- Open sign-up without email verification, CAPTCHA or rate limiting; no password reset.
- Import keeps basic formatting only; `.docx` underline is dropped by mammoth's default.
- `requirements.txt` is not pinned.
- Tested in Firefox only.
