from __future__ import annotations
from .runtime import find_binary, tool_environment

import hashlib
import subprocess
import tempfile
from pathlib import Path
import fitz
from . import store
from .models import uid

MAX_UPLOAD = 120 * 1024 * 1024


def register(lid, name, content, role="support", priority=1, linked_id=None):
    store.lecture(lid)
    suffix = Path(name).suffix.lower()
    if suffix not in (".txt", ".md", ".pdf", ".docx"):
        raise ValueError("الصيغ المدعومة هي TXT وMarkdown وPDF وDOCX")
    if not content or len(content) > MAX_UPLOAD:
        raise ValueError("الملف فارغ أو أكبر من 120 ميغابايت")
    if linked_id:
        parent = store.one("SELECT * FROM sources WHERE id=? AND lecture_id=?", (linked_id, lid))
        if parent["kind"] != "pdf":
            raise ValueError("اربط التفريغ بملف PDF أصلي")
    digest = hashlib.sha256(content).hexdigest()
    duplicate = store.all_rows(
        "SELECT * FROM sources WHERE lecture_id=? AND digest=?", (lid, digest)
    )
    if duplicate:
        return duplicate[0]
    sid = uid()
    relative = f"sources/{sid}{suffix}"
    path = store.DATA / relative
    path.write_bytes(content)
    if suffix == ".pdf":
        try:
            with fitz.open(path) as pdf:
                if pdf.is_encrypted:
                    raise ValueError("افتح حماية PDF قبل رفعه")
                count = len(pdf)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    elif suffix == ".docx":
        import io, zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as package:
                if "word/document.xml" not in package.namelist():
                    raise ValueError("الملف ليس مستند DOCX")
        except zipfile.BadZipFile as error:
            path.unlink(missing_ok=True)
            raise ValueError("ملف DOCX غير صالح") from error
        count = 1
    else:
        content.decode("utf-8-sig")
        count = len(content.decode("utf-8-sig").split("\f"))
    with store.connect() as db:
        db.execute(
            "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                sid,
                lid,
                Path(name.replace("\\", "/")).name,
                relative,
                suffix[1:],
                priority,
                role,
                linked_id,
                digest,
                store.now(),
            ),
        )
        for n in range(1, count + 1):
            db.execute("INSERT INTO pages(source_id,number) VALUES(?,?)", (sid, n))
    return store.one("SELECT * FROM sources WHERE id=?", (sid,))


def text_usable(text):
    chars = [c for c in text if not c.isspace()]
    if len(chars) < 30:
        return False
    bad = sum(c == "\ufffd" or ord(c) < 32 for c in chars)
    return bad / len(chars) < 0.02 and sum(c.isalnum() for c in chars) / len(chars) > 0.45


def extract(sid, progress=lambda n: None):
    source = store.one("SELECT * FROM sources WHERE id=?", (sid,))
    path = store.DATA / source["path"]
    if source["kind"] == "docx":
        from .word_import import parse
        parsed = parse(path.read_bytes(), source["name"])
        with store.connect() as db:
            db.execute("UPDATE pages SET raw=?,method=? WHERE source_id=? AND number=1",
                       (parsed["source_text"], "docx", sid))
        progress(100)
        return {"source_id": sid, "pages": 1, "warnings": parsed["warnings"]}
    pages = store.all_rows("SELECT * FROM pages WHERE source_id=? ORDER BY number", (sid,))
    linked = store.all_rows("SELECT id FROM sources WHERE linked_id=?", (sid,))
    pdf = fitz.open(path) if source["kind"] == "pdf" else None
    try:
        for index, row in enumerate(pages):
            if row["corrected"] is not None or row["raw"] or row["excluded"]:
                progress(round((index + 1) / len(pages) * 100))
                continue
            if pdf:
                page = pdf[row["number"] - 1]
                text = page.get_text(sort=True)
                method = "pdf_text"
                if not text_usable(text):
                    if linked:
                        method, text = "external_transcript", ""
                    else:
                        langs = subprocess.run(
                            [find_binary("tesseract"), "--list-langs"],
                            env=tool_environment(),
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            check=True,
                        ).stdout
                        if "ara" not in langs.split():
                            raise ValueError(
                                "حزمة OCR العربية غير مثبتة. ثبّت ara أو ارفع تفريغًا خارجيًا."
                            )
                        with tempfile.TemporaryDirectory() as tmp:
                            image = Path(tmp) / "page.png"
                            page.get_pixmap(dpi=220).save(image)
                            result = subprocess.run(
                                [find_binary("tesseract"), str(image), "stdout", "-l", "ara+eng", "--psm", "3"],
                                env=tool_environment(),
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                                timeout=180,
                            )
                            if result.returncode:
                                raise ValueError(
                                    "تعذر استخراج النص من الصفحة؛ ارفع تفريغًا خارجيًا أو صححها يدويًا"
                                )
                            text, method = result.stdout, "tesseract"
            else:
                text = (
                    path.read_text(encoding="utf-8-sig").split("\f")[row["number"] - 1]
                    if row["number"] <= len(path.read_text(encoding="utf-8-sig").split("\f"))
                    else ""
                )
                method = "external_transcript" if source["linked_id"] else "text"
            with store.connect() as db:
                db.execute(
                    "UPDATE pages SET raw=?,method=? WHERE source_id=? AND number=?",
                    (text, method, sid, row["number"]),
                )
            progress(round((index + 1) / len(pages) * 100))
    finally:
        if pdf:
            pdf.close()
    return {"source_id": sid, "pages": len(pages)}


def update_page(sid, number, corrected, excluded):
    with store.connect() as db:
        row = db.execute(
            "SELECT number FROM pages WHERE source_id=? AND number=?", (sid, number)
        ).fetchone()
        if not row:
            raise LookupError("صفحة المصدر غير موجودة")
        db.execute(
            "UPDATE pages SET corrected=?,excluded=? WHERE source_id=? AND number=?",
            (corrected, int(excluded), sid, number),
        )


def page_image(sid, number):
    path = store.source_path(sid)
    with fitz.open(path) as pdf:
        if not 1 <= number <= len(pdf):
            raise ValueError("رقم الصفحة خارج الملف")
        return pdf[number - 1].get_pixmap(dpi=120).tobytes("png")


def source_warnings(document, lid):
    rows = store.effective_pages(lid)
    pages = {(r["source_id"], r["number"]): r for r in rows}
    issues = []
    covered = set()
    for section in document.sections:
        for block in section.blocks:
            for ref in block.refs:
                key = (ref.source_id, ref.page)
                if key not in pages:
                    raise ValueError(f"مرجع غير موجود في العنصر {block.title or block.kind}")
                row = pages[key]
                text = row["corrected"] if row["corrected"] is not None else row["raw"]
                if ref.quote and ref.quote not in text:
                    issues.append(
                        {
                            "block_id": block.id,
                            "message": "المقتطف لا يطابق النص المعتمد للمصدر",
                            "severity": "warning",
                        }
                    )
                covered.add(key)
            if block.verbatim and block.problem not in [r.quote for r in block.refs]:
                issues.append(
                    {
                        "block_id": block.id,
                        "message": "نص السؤال تغيّر عن المقتطف الحرفي",
                        "severity": "error",
                    }
                )
            if block.issue and not block.issue_resolved:
                issues.append({"block_id": block.id, "message": block.issue, "severity": "warning"})
            if not block.refs:
                issues.append(
                    {
                        "block_id": block.id,
                        "message": "إضافة بلا مرجع؛ تحتاج مراجعة علمية",
                        "severity": "warning",
                    }
                )
    usable = {
        (r["source_id"], r["number"])
        for r in rows
        if not r["excluded"]
        and (r["corrected"] if r["corrected"] is not None else r["raw"]).strip()
    }
    return {
        "issues": issues,
        "covered_pages": len(covered & usable),
        "source_pages": len(usable),
        "unreferenced_pages": [{"source_id": x[0], "page": x[1]} for x in sorted(usable - covered)],
        "notice": "التغطية هنا تتبع مراجع الصفحات؛ لا تثبت وحدها اكتمال المعلومات العلمية.",
    }
