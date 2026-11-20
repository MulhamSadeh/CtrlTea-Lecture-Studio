# Public demo

This is an **interactive browser-only preview**, not a deployment of the complete FastAPI application. The lecture data is synthetic. Visitors can browse courses, view structured blocks, edit text temporarily, add notes, preview the document, download their modified JSON, and print the browser preview.

No server-side storage, student data, accounts, OCR, or backend DOCX/PDF export is available in this public demo.

## Render settings

- Repository: https://github.com/MulhamSadeh/CtrlTea-Lecture-Studio
- Branch: main
- Build command: cp frontend/public/ct-logo.png demo/logo.png && cp examples/demo-lecture.json demo/example.json
- Publish directory: demo
- No environment variables or database.

Run those copy commands locally, then use python -m http.server 8769 --directory demo for a local preview.