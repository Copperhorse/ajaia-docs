# AI workflow note (DRAFT SKELETON)

> This note is meant to be in **your** words. Rows marked `TODO(you)` are things only you know. Delete this box before submitting. Do not claim verification you have not done.

## Tools used

- Claude (Anthropic) in an agentic coding session: planning, library research, drafting code, drafting documents.
- Zed editor
- Supabase
- Excalidraw


## How I used AI

1. Planning and scope before any code (the first hour).
2. Comparing libraries and storage choices.
3. Drafting code, which I then reviewed. TODO(you): say which parts you wrote yourself, which parts AI drafted, and how much you changed.
4. TODO(you): tests, docs, deployment help.

## Decision log (who decided what)

| Decision | Who proposed | What happened |
|---|---|---|
| Overall scope and the sharing model | Me | Set before building. |
| Use FastAPI + Supabase (as a hosted Postgres) | Me | AI agreed with caveats: needs a database-layer change, RLS must be on. |
| Use PyMuPDF for file conversion | Me | AI pushed back (Office-to-Markdown needs the paid Pro add-on, 3-page limit without a license). I accepted and chose mammoth + python-markdown. |
| Markdown as the stored format | Me | AI corrected that Quill stores Delta, not Markdown, and Markdown has no underline. I chose HTML storage instead. |
| Quill with HTML storage, sanitized with nh3 | AI | I accepted. TODO(you): why it suited you. |
| Tables: users, documents, shares; owner as a column on documents | Me | AI agreed and suggested the exact columns (title, updated_by, timestamps). |
| Sharing by hash or link | Me | AI advised against (a hash of an ID is guessable; the assignment asks for user-based sharing). I agreed. |
| Version counter for change detection | AI | I pointed out it changes even when nothing changed. |
| Content hash for change detection | Me | Adopted in place of the counter. |
| Change banner: load theirs / keep mine / download | Me | AI drafted the details. |

## Where AI was wrong or I overrode it

- AI wrote a first backend draft using SQLite and Quill Delta before the design was settled. I changed the direction (Supabase, HTML), so that draft was replaced. TODO(you): what you kept.
- The version-counter suggestion was replaced by your content-hash idea.
- TODO(you): any bugs or bad suggestions you caught during the build.

## How I verified

TODO(you): list only what you actually did. Examples to choose from, if true:
- Ran the automated tests (which ones, results).
- Tested sharing manually as Alice, Bob and Carol in separate windows.
- Tested a bad file, an oversized file, a stale save.
- Read the code for auth and permissions.
- Tested on the deployed URL, not just locally.

## What I did not verify / limits

TODO(you): be honest. Likely items: behaviour under many simultaneous editors, large documents, browsers other than the one you tested, `.docx` files with complex layouts.

## What I would do differently

TODO(you).
