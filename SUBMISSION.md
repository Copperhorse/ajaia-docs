# Submission: Ajaia Docs

| | |
|---|---|
| **Live app** | `TODO(you): live URL` |
| **Demo logins** | `alice@example.com`, `bob@example.com`, `carol@example.com` |
| **Demo password** | `TODO(you): the SEED_PASSWORD you set on Render. Put it in the portal and the Drive file, not in the public repo.` |
| **Walkthrough video** | `TODO(you): public Loom or YouTube link` |
| **Source code** | https://github.com/Copperhorse/ajaia-docs |
| **Docs** | [README](README.md) (run, test, deploy), [ARCHITECTURE](ARCHITECTURE.md), [AI workflow note](AI_WORKFLOW.md) |

A free Render service sleeps when idle and can take about a minute to wake on the first visit.

## What I built

A lightweight collaborative document editor: sign in, create and edit rich-text documents, import files, share them, and handle two people editing the same document. FastAPI + Postgres (Supabase) on the back end; plain HTML/CSS/JS with the Quill editor on the front.

## What works

Each item below was exercised, and how is noted in brackets. "Tests" means the 72 automated pytest tests; "browser run" means a scripted Firefox session I wrote during development (it is not in the repository).

- **Accounts:** sign-in with the three demo users, and open sign-up with validation. [tests, browser run]
- **Documents:** create, rename, edit, delete (owner only), and reopen with formatting intact. [tests, browser run]
- **Rich text:** headings 1-3, bold, italic, underline, bulleted and numbered lists. The HTML Quill produces survives the server-side sanitizer and loads back identically. [browser run]
- **Autosave:** one second after you stop typing, only when something changed; `Ctrl+S` saves immediately; a visible status shows Saving, Saved, or the error. [browser run]
- **Import:** `.txt`, `.md`, `.docx` into a new editable document; wrong types, empty, oversized, corrupt and zip-bomb files are refused with a clear message. [tests, browser run]
- **Sharing:** the owner shares by email as viewer or editor, changes or removes access. The list shows "Owned by me" and "Shared with me" with role badges. Viewers get a read-only editor and a "View only" badge. [tests, browser run]
- **Permissions on the server:** a stranger gets 404, a viewer cannot edit, only the owner can share or delete. [tests]
- **Change detection:** the page checks for a newer version every 10 seconds. A banner offers Load their version, Keep mine and overwrite, or Download my copy, and autosave pauses until you choose. A save refused by the server (409) opens the same banner. The server never lets two saves both win. [tests for the server rules, browser run with a simulated second user]
- **Safety:** all stored HTML is sanitized (scripts, event handlers and `javascript:` links are removed), user text is always shown as text, and the pages carry a Content Security Policy. [tests, browser run]
- **Persistence:** all data is in Postgres; the API was also run against the real Supabase database. [manual run]

## What is partial or missing

- **No real-time co-editing.** This is change detection with a choice: two people can still conflict, and the second saver decides what to keep. There is no merge and no version history.
- **The banner does not show what changed,** only who saved and when. (The spec marks this as the first thing to cut.)
- **`.docx` import** drops underline (a mammoth default) and ignores images, tables and comments. I only tested `.docx` files I built by hand, not real Word documents.
- **Open sign-up has no email verification, CAPTCHA or rate limiting,** and there is no password reset.
- **Speed depends on where the database is.** From my machine to a Tokyo-hosted Supabase, opening a document took about 2 seconds, because every request needs several database round trips. Running the app near the database fixes most of it. Details are in ARCHITECTURE.md.
- **Tested in Firefox only.** `requirements.txt` is not pinned.
- `TODO(you)`: anything you found while testing the deployed app.

## What I would build next

1. Real-time collaboration and a version history.
2. A "what changed" view in the change banner.
3. Fewer database round trips per request, and pinned dependency versions.
4. Email verification, password reset and rate limiting.
5. Tables, images and comments; PDF import and export; share links.
6. A browser test suite (for example Playwright) kept in the repository.

## How I used AI

See [AI_WORKFLOW.md](AI_WORKFLOW.md), written by the author.
