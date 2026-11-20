# Ctrl+Tea Lecture Studio

**Status: Work in progress · Local development preview · AQ-06 source snapshot**

Ctrl+Tea Lecture Studio is an **Arabic-first lecture authoring and management dashboard** developed for the **Ctrl+Tea volunteer student team**. It helps organize courses, prepare university lecture materials, review structured content, and produce editable documents.

The team is **currently focused on third-year Computer Engineering students**. This describes the team's present educational scope, not a restriction enforced by the software.

> **Under active improvement.** The application is not a hosted public service or a production-ready multi-user deployment. Some workflows, deployment instructions, and quality checks are still being refined. No accuracy or performance benchmark is claimed here.

## Project overview

![Lecture Studio workflow](docs/workflow.svg)

The source includes:

- **Arabic RTL dashboard** built with React, TypeScript, and Vite.
- **Lecture and course management:** create, edit, organize and restore work.
- **Source handling:** PDFs, transcripts, correction workflows and OCR support.
- **Structured authoring:** definitions, explanations, equations, exercises, tables, and diagrams.
- **Document exports:** editable DOCX and PDF, with native equations in Word using the OMML pathway.
- **Workspace and admin interfaces:** role-aware profiles and a Super Admin dashboard, backed by FastAPI endpoints. These are not claims of production deployment.
- **Backend:** Python, FastAPI, SQLite for local work; PostgreSQL-related development and migrations included for the account-enabled track.

## Demo example (synthetic, not a real lecture)

The repository includes an **original teaching example** about binary numbers. It shows the structure of a lecture document without publishing students' files, teachers' notes, or copyrighted lecture sources.

- [`examples/demo-lecture.json`](examples/demo-lecture.json): a schema-valid illustrative lecture document.
- [`examples/seed_demo.py`](examples/seed_demo.py): loads the example into the **local, authentication-disabled** development instance using the existing API.

For a local instance running on port 8766:

```bash
python examples/seed_demo.py --url http://127.0.0.1:8766
```

For Windows's default port, use `--url http://127.0.0.1:8765`. This script is intended only for an offline/local development environment. Do **not** disable authentication on an internet-accessible host. Do not use the demo on a server holding real student data.

## Local setup (source distribution)

1. Install Python 3.11+, Node.js, Pandoc, LibreOffice with Math, and Tesseract OCR with the Arabic/English trained data; see the existing [`README_AR.md`](README_AR.md) for details.
2. Install Python dependencies in an isolated environment. The current local server imports the PostgreSQL client module even when running with SQLite, so include the `postgres` optional dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[postgres]" httpx
   ```

   On Windows, activate `.venv\Scripts\activate` instead.
3. Build the frontend:

   ```bash
   cd frontend
   npm ci
   npm run build
   cd ..
   ```

4. Use the **local-only profile** on your computer (example on Linux):

   ```bash
   export CTRLTEA_AUTH_MODE=local
   export CTRLTEA_DB_BACKEND=sqlite
   export CTRLTEA_DATA_DIR="$PWD/data"
   python scripts/start.py --port 8765
   ```

5. Open `http://127.0.0.1:8765`.

**Font notice:** This source snapshot intentionally omits binary font files and generated frontend builds. For faithful document layout/embedded fonts, install licensed font dependencies separately and follow the project's font setup instructions. Some font-dependent exports will not match the team's internal release without those resources. The example and code are presented for review and development, not as a drop-in full production distribution.

The account-enabled / PostgreSQL deployment requires additional configuration and security review. Never expose local-mode sessions directly to the internet. See [`docs/task04/`](docs/task04/) for technical details and implementation notes. Do not put credentials in the repository.

## Current work

- Improving the UX of the lecture editor and dashboard.
- Expanding end-to-end tests and cross-platform compatibility.
- Refining the review workflow, scientific content QA, and export consistency.
- Preparing secure, documented multi-user usage; the online version is **not announced as released**.

## Ctrl+Tea team and college bot

Ctrl+Tea is a **student-run volunteer initiative**, currently focused on **third-year students**. Its materials and communication channels are separate from this local application.

**College Telegram bot:** [@CAE20_25_bot](https://t.me/CAE20_25_bot)

The bot is linked for students' convenience; **this README does not claim the bot is integrated into Lecture Studio**.

## بالعربي

**Ctrl+Tea Lecture Studio** لوحة عمل لتجهيز المحاضرات وتنظيمها ومراجعتها وتصديرها، وهي **قيد التطوير والتحسين** وليست نسخة منشورة للجمهور. الفريق تطوعي ويركّز حالياً على **طلاب السنة الثالثة في هندسة الحواسيب**. بوت الكلية: [@CAE20_25_bot](https://t.me/CAE20_25_bot).

## About this repository

This is a **curated source snapshot** prepared from the AQ-06 NixOS-corrected archive. Generated builds, font binaries, original reference artworks, private data, and source-PDF fixtures have been omitted. Existing implementation documents are included for context and may describe internal validation from an earlier environment; these results have **not** been re-certified for this curated export. No public live demo or hosted deployment is claimed.

The project is evolving. Contributions and usage rights should be agreed with the Ctrl+Tea team before reusing or redistributing the code; no open-source license has been added automatically.
