# AI workflow note


## Tools I used

- **Claude (chat session):** helped me plan, compare options, write `SPEC.md` and `CLAUDE.md`, draw the first versions of the diagrams, and review the code.
- **Claude Code (Claude Sonnet 5.5):** wrote the backend, the frontend, the tests and the documents in the repo, following `SPEC.md` and `CLAUDE.md`. It also ran the checks described below, created the GitHub repository and pushed the commits when I asked it to.
- **Zed editor:** where I read the code, ran the tests and ran my own commands.
- **Excalidraw:** the diagrams I show in the video. Claude generated the first versions; I added the Scope and Tech Stack boxes and arranged the canvas myself.
- **Supabase** (hosted Postgres), **GitHub**, and **Render** for hosting. 

## How I used AI

1. **Planning.** I wrote down the scope and the first idea of the stack myself (FastAPI, Supabase, the tables). I used Claude for references and for checking my ideas. For example, I didn't know which rich-text editors exist, so I asked, and Claude compared Quill, Tiptap and others.
2. **Spec before code.** Before any code, I had Claude write `SPEC.md` (scope, data model, API, save logic) and `CLAUDE.md` (rules for the coding agent). Giving the coding agent a fixed spec meant it had less room to guess or go off track. `CLAUDE.md` told it to build one milestone at a time, say what it would build before each one, say how to check it afterwards, and say which of its choices were not obvious.
3. **Code.** Claude Code wrote the code in small steps, one milestone at a time: database layer, password hashing and sanitizer, sign-in and demo users, documents and saving, sharing, import, then the frontend (list, editor, share dialog, import, change banner), open sign-up and delete. I did not write the application code by hand. By hand I edited `CLAUDE.md` and this note, and I set up `.env` and the Supabase project. `TODO(me): add anything else you changed yourself, however small.`
4. **Tests and documents.** Claude Code wrote the 76 automated tests, and drafted `README.md`, `ARCHITECTURE.md` and `SUBMISSION.md`. When I asked, it also measured how long each request takes against the real database.
5. **Review.** I read the code in Zed, ran the tests, and used the app myself.

## Who decided what

| Decision | Who proposed | What happened |
|---|---|---|
| Scope, sharing model, tables (users, documents, shares), owner as a column on documents | Me | Claude agreed and suggested extra columns (title, updated_by, timestamps). |
| FastAPI + Supabase | Me | Claude agreed, with a warning about region and Row Level Security. |
| Content hash to detect changes | Me | I noticed a version counter would change even with no edits. We switched to the hash. |
| Version counter | Claude | Replaced by my hash idea. |
| Version history, PDF and Markdown export | Me | Left out because the assignment asks for one small enhancement. I chose the change banner. |
| Pandoc instead of Mammoth | Me | I still like Pandoc. Claude advised keeping Mammoth because the sanitizer strips most of what Pandoc adds, and Pandoc is heavy on a free host. I kept Mammoth for now. |
| Open sign-up (anyone can create an account) | Me | The spec had only demo users. Claude Code asked me to choose between a protected admin route, open sign-up, or a SQL script, and noted that a plain SQL insert can't make a working login because passwords are stored as scrypt hashes. I chose open sign-up. It warned there is no email check or rate limit, and that is recorded in `SPEC.md`. |
| Display names with spaces and capitals | Me | After the sign-up form rejected "Bob Odenkirk", I asked for spaces and capitals. Claude Code made names unique ignoring case with a database index. |
| Squarer corners everywhere, tidier share dialog | Me | Claude Code picked the sizes (8, 6 and 4 px) in one place in the stylesheet. This departs from the design system, which uses pills. |
| No Docker, Render builds from the GitHub repo | Me | Claude Code removed Docker from the spec and wrote the Render build and start commands into the README. |
| Move the database near the host | Me | Claude Code measured the delay and explained it. I made the change (see below). |

## Where AI's first answer was changed or thrown away

**During planning (this is where almost all the corrections happened):**
- Claude's first backend draft used SQLite and Quill's Delta format. We changed direction to Supabase and HTML before the real build.
- The version counter was replaced by the content hash (my idea).
- Markdown as the stored format, sharing by hash, an in-memory cache and PyMuPDF were all proposed by me and changed after discussion (see the table above).

**During coding, problems found and fixed:**
- Claude Code found that Quill writes every space as `&nbsp;`, which stops text from wrapping. It added a fix before saving and tested that formatting survives a round trip. A worry in the spec (that Quill's list HTML would be stripped by the sanitizer) turned out not to apply.
- Its first README said `.docx` import keeps underline. Testing showed Mammoth drops it, so the README now says so.
- The sign-up rule it first wrote was too strict (lowercase only, no spaces). I hit this myself and asked for the change.
- Its first way to add the case-insensitive name index made every test fail. It switched to a different statement and added a test for databases that already exist.
- After building delete, it noticed that a pending autosave would still send a request to the deleted document. It fixed that and added a check.
- Its first poll could show a false "newer version" banner after my own save. It added a guard.
- Smaller slips of its own: several bugs in its test scripts, a command that killed its own shell more than once, and one early test run that went through my already-running server instead of its own (nothing was written, because its test password was wrong for my database).


**One problem that came up while building, not in planning:** Supabase's "Auto" region put the database in Tokyo, and opening a document took about 2 seconds. Claude Code measured it (opening a document about 2.0 s, the list about 1.7 s, sign-in about 0.7 s, against 1 to 5 ms on a local database) and traced most of it to the distance between the app and the database. I then moved the project to Ohio, next to the host. 

## How I verified

- **Automated tests:** 76 pytest tests; all passed the last time they were run (in-memory database, never the real one).
- **Real Supabase:** sign-in, list, create, save, stale save (409), sharing and delete were run against my real database with temporary documents that were removed afterwards. This was done before the later changes listed below.


## What I did not verify

- The database changes made late (the case-insensitive name index, the combined sign-up query, the lighter document read, the single start-up transaction) against real Supabase. They were tested on SQLite only.
- Browsers other than Firefox, and the editor on a phone-sized screen.
- Real Word documents. The `.docx` tests used small files built by hand, so lists and links from real Word files are untested, and underline is dropped.
- Two real people editing at once. The banner was tested with a simulated second user.
- Abuse of open sign-up: there is no email check, no CAPTCHA and no rate limit.
- Large documents, and many people editing at the same time.
- `requirements.txt` is not pinned, so a fresh install gets the newest versions.
