from __future__ import annotations

import json
import logging
import shutil
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, UploadFile, File, Form, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from . import store, sources, authoring, bundles
from . import accounts,access,account_api,trash
from .models import LectureDocument, Block, uid
from .author_validation import AuthoringValidationError, result_schema
from .jobs import Worker, enqueue
from .figures import render
from .mathml import omml
from .theme import DEFAULT_THEME, ThemeName, design_settings, validate_theme


class CourseInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    doctor: str = ""


class LectureInput(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    number: str = "01"
    theme: ThemeName = DEFAULT_THEME


class ThemeInput(BaseModel):
    theme: ThemeName


class SaveInput(BaseModel):
    document: LectureDocument
    revision: int


class PageInput(BaseModel):
    corrected: str | None
    excluded: bool = False


class SourceInput(BaseModel):
    priority: int = Field(default=1, ge=0, le=999)
    role: str = "support"
    linked_id: str | None = None


class ResultInput(BaseModel):
    result: Any
    revision: int = 0
    allow_conflicts: bool = False


class ExportInput(BaseModel):
    draft: bool = False


@asynccontextmanager
async def lifespan(app):
    if accounts.enabled():
        accounts.check_config()
    else:
        store.init()
    worker = Worker()
    worker.start()
    app.state.worker = worker
    yield
    worker.stop()


app = FastAPI(title="Ctrl+Tea Lecture Studio", version="1.0.0", lifespan=lifespan, dependencies=[Depends(access.authorize)])
app.add_middleware(access.SecurityHeaders)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"],
)


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
        from urllib.parse import urlparse

        parsed = urlparse(origin)
        if (accounts.enabled() and origin.rstrip('/')!=accounts.origin()) or (not accounts.enabled() and parsed.hostname not in ("localhost", "127.0.0.1", "[::1]", "::1")):
            return JSONResponse(
                {"message": "هذا التطبيق يقبل التعديلات من واجهته المحلية فقط."},
                status_code=403,
            )
    return await call_next(request)


@app.exception_handler(store.Conflict)
async def conflict(request, error):
    return JSONResponse({"message": str(error)}, status_code=409)


@app.exception_handler(LookupError)
async def missing(request, error):
    return JSONResponse({"message": str(error)}, status_code=404)


@app.exception_handler(AuthoringValidationError)
async def bad_author_result(request, error):
    return JSONResponse(
        {
            "message": "نتيجة التأليف تحتاج تصحيح الحقول التالية قبل الاستيراد.",
            "errors": error.errors,
        },
        status_code=422,
    )


@app.exception_handler(ValueError)
async def bad_value(request, error):
    detail = str(error)
    return JSONResponse({"message": detail[:1200]}, status_code=422)


@app.exception_handler(Exception)
async def unexpected(request, error):
    if accounts.enabled():
        logging.error("Request failed: %s", type(error).__name__)
        return JSONResponse({"message":"تعذر إتمام العملية","code":"internal_error"},status_code=500)
    logging.exception("Request failed")
    return JSONResponse(
        {
            "message": "تعذر إتمام العملية. افتح التشخيص لمعرفة السبب.",
            "diagnostic": str(error),
        },
        status_code=500,
    )


@app.get("/api/health")
def health():
    if accounts.enabled():
        return {"status":"ok"}
    return {
        "status": "ok",
        "version": "1.0.0",
        "tools": {k: bool(shutil.which(k)) for k in ["pandoc", "soffice", "tesseract"]},
        "word_application_tested": False,
    }


@app.get("/api/schema")
def schema():
    return LectureDocument.model_json_schema()


@app.get("/api/authoring/schema")
def author_schema():
    return result_schema()


@app.get("/api/design")
def design():
    return design_settings()


@app.get("/api/courses")
def courses():
    return store.all_rows(
        "SELECT c.*,(SELECT count(*) FROM lectures l WHERE l.course_id=c.id) AS lecture_count FROM courses c ORDER BY c.created DESC"
    )


@app.post("/api/courses", status_code=201)
def create_course(data: CourseInput):
    cid = uid()
    with store.connect() as db:
        db.execute(
            "INSERT INTO courses VALUES(?,?,?,?)",
            (cid, data.name.strip(), data.doctor, store.now()),
        )
    return store.one("SELECT * FROM courses WHERE id=?", (cid,))


@app.put("/api/courses/{cid}")
def edit_course(cid: str, data: CourseInput):
    store.one("SELECT * FROM courses WHERE id=?", (cid,))
    with store.connect() as db:
        db.execute(
            "UPDATE courses SET name=?,doctor=? WHERE id=?",
            (data.name, data.doctor, cid),
        )
    return {"ok": True}


@app.delete("/api/courses/{cid}")
def delete_course(cid: str):
    store.one("SELECT * FROM courses WHERE id=?", (cid,))
    with store.connect() as db:
        trash.capture("course",cid)
        db.execute("DELETE FROM courses WHERE id=?", (cid,))
    return {"ok": True}


@app.get("/api/courses/{cid}/lectures")
def lectures(cid: str):
    return store.all_rows(
        "SELECT id,course_id,title,revision,updated,theme FROM lectures WHERE course_id=? ORDER BY updated DESC",
        (cid,),
    )


@app.post("/api/courses/{cid}/lectures", status_code=201)
def create_lecture(cid: str, data: LectureInput):
    course = store.one("SELECT * FROM courses WHERE id=?", (cid,))
    doc = LectureDocument(
        title=data.title,
        number=data.number,
        course=course["name"],
        doctor=course["doctor"],
    )
    lid = uid()
    with store.connect() as db:
        db.execute(
            "INSERT INTO lectures(id,course_id,title,doc,revision,updated,theme) VALUES(?,?,?,?,?,?,?)",
            (lid, cid, data.title, doc.model_dump_json(), 0, store.now(), data.theme),
        )
    return store.lecture(lid)


@app.get("/api/lectures/{lid}")
def get_lecture(lid: str):
    return store.lecture(lid)


@app.put("/api/lectures/{lid}/theme")
def set_lecture_theme(lid: str, data: ThemeInput):
    return store.set_theme(lid, data.theme)


@app.put("/api/lectures/{lid}")
def save_lecture(lid: str, data: SaveInput):
    sources.source_warnings(data.document, lid)
    return store.save_document(lid, data.document.model_dump(), data.revision)


@app.delete("/api/lectures/{lid}")
def delete_lecture(lid: str):
    store.lecture(lid)
    with store.connect() as db:
        trash.capture("lecture",lid)
        db.execute("DELETE FROM lectures WHERE id=?", (lid,))
    return {"ok": True}


@app.get("/api/lectures/{lid}/revisions")
def revisions(lid: str):
    return store.all_rows(
        "SELECT id,revision,created,reason FROM revisions WHERE lecture_id=? ORDER BY revision DESC LIMIT 100",
        (lid,),
    )


@app.post("/api/lectures/{lid}/revisions/{rid}/restore")
def restore(lid: str, rid: str, data: dict):
    version = store.one(
        "SELECT * FROM revisions WHERE lecture_id=? AND id=?", (lid, rid)
    )
    doc = LectureDocument.model_validate_json(version["doc"])
    return store.save_document(
        lid, doc.model_dump(), int(data["revision"]), "استعادة نسخة سابقة"
    )


@app.get("/api/lectures/{lid}/sources")
def list_sources(lid: str):
    return store.all_rows(
        "SELECT s.*,(SELECT count(*) FROM pages p WHERE p.source_id=s.id) AS page_count FROM sources s WHERE s.lecture_id=? ORDER BY s.priority,s.created",
        (lid,),
    )


@app.post("/api/lectures/{lid}/sources")
async def upload_source(
    lid: str,
    file: UploadFile = File(...),
    role: str = Form("support"),
    priority: int = Form(1),
    linked_id: str = Form(""),
):
    if role not in ("primary", "support", "previous", "transcript"):
        raise ValueError("نوع المصدر غير صالح")
    data = await file.read(sources.MAX_UPLOAD + 1)
    source = sources.register(
        lid, file.filename or "source.txt", data, role, priority, linked_id or None
    )
    job = enqueue(lid, "extract", {"source_id": source["id"]})
    return {"source": source, "job": job}


@app.post("/api/lectures/{lid}/word/preview")
async def word_preview(lid: str, file: UploadFile = File(...)):
    from .word_import import parse
    name = file.filename or "document.docx"
    if not name.lower().endswith(".docx"):
        raise ValueError("اختر ملف DOCX؛ ملفات DOC القديمة غير مدعومة")
    data = await file.read(40 * 1024 * 1024 + 1)
    parsed = parse(data, name)
    source = sources.register(lid, name, data, role="previous")
    with store.connect() as db:
        db.execute("UPDATE pages SET raw=?,method=? WHERE source_id=? AND number=1",
                   (parsed["source_text"], "docx", source["id"]))
    for section in parsed["sections"]:
        for block in section["blocks"]:
            block["refs"] = [{"source_id":source["id"], "page":1, "quote": ""}]
    return {"sections":parsed["sections"], "warnings":parsed["warnings"], "source":source}


@app.put("/api/sources/{sid}")
def edit_source(sid: str, data: SourceInput):
    source = store.one("SELECT * FROM sources WHERE id=?", (sid,))
    if data.role not in ("primary", "support", "previous", "transcript"):
        raise ValueError("نوع المصدر غير صالح")
    if data.linked_id:
        parent = store.one(
            "SELECT * FROM sources WHERE id=? AND lecture_id=?",
            (data.linked_id, source["lecture_id"]),
        )
        if parent["kind"] != "pdf" or parent["id"] == sid:
            raise ValueError("يجب الربط بملف PDF أصلي آخر")
    with store.connect() as db:
        db.execute(
            "UPDATE sources SET priority=?,role=?,linked_id=? WHERE id=?",
            (data.priority, data.role, data.linked_id, sid),
        )
    return {"ok": True}


@app.delete("/api/sources/{sid}")
def delete_source(sid: str):
    with store.transaction() as db:
        if accounts.enabled():
            db.execute('SELECT id FROM lectures WHERE id=(SELECT lecture_id FROM sources WHERE id=?) FOR UPDATE',(sid,)).fetchall()
        return delete_source_record(sid)


def delete_source_record(sid):
    source = store.one("SELECT * FROM sources WHERE id=?", (sid,))
    doc = LectureDocument.model_validate(
        store.lecture(source["lecture_id"])["document"]
    )
    if any(r.source_id == sid for s in doc.sections for b in s.blocks for r in b.refs):
        raise ValueError("المصدر مرتبط بمحتوى المحاضرة؛ عدّل المراجع قبل حذفه")
    historical = store.all_rows(
        "SELECT doc FROM revisions WHERE lecture_id=?", (source["lecture_id"],)
    )
    if any(
        any(
            r.get("source_id") == sid
            for s in json.loads(row["doc"])["sections"]
            for b in s["blocks"]
            for r in b.get("refs", [])
        )
        for row in historical
    ):
        raise ValueError(
            "المصدر مستخدم في سجل النسخ؛ استبعد صفحاته بدل حذفه للحفاظ على إمكانية الاستعادة"
        )
    if store.all_rows("SELECT id FROM sources WHERE linked_id=?", (sid,)):
        raise ValueError("هناك تفريغ مرتبط بهذا الأصل؛ أزل الربط أولًا")
    with store.connect() as db:
        trash.capture("source",sid)
        db.execute("DELETE FROM sources WHERE id=?", (sid,))
    return {"ok": True}


@app.get("/api/sources/{sid}/pages")
def get_pages(sid: str):
    return store.all_rows(
        "SELECT * FROM pages WHERE source_id=? ORDER BY number", (sid,)
    )


@app.post("/api/sources/{sid}/pages")
def add_transcript_page(sid: str, data: dict):
    source = store.one("SELECT * FROM sources WHERE id=?", (sid,))
    if source["kind"] == "pdf":
        raise ValueError("صفحات PDF ثابتة؛ أضف النص المصحح لصفحة موجودة")
    number = int(data["number"])
    if number < 1 or number > 10000:
        raise ValueError("رقم الصفحة غير صالح")
    with store.connect() as db:
        if db.execute(
            "SELECT 1 FROM pages WHERE source_id=? AND number=?", (sid, number)
        ).fetchone():
            raise ValueError("هذه الصفحة موجودة مسبقًا")
        db.execute(
            "INSERT INTO pages VALUES(?,?,?,?,?,?)",
            (sid, number, "", data.get("corrected", ""), 0, "external_transcript"),
        )
    return {"ok": True}


@app.put("/api/sources/{sid}/pages/{number}")
def correct_page(sid: str, number: int, data: PageInput):
    sources.update_page(sid, number, data.corrected, data.excluded)
    return {"ok": True}


@app.get("/api/sources/{sid}/pages/{number}/image")
def image(sid: str, number: int):
    return Response(sources.page_image(sid, number), media_type="image/png")


@app.get("/api/sources/{sid}/file")
def source_file(sid: str):
    source = store.one("SELECT * FROM sources WHERE id=?", (sid,))
    return FileResponse(
        store.DATA / source["path"],
        filename=source["name"],
        content_disposition_type="inline",
    )


@app.post("/api/sources/{sid}/extract")
def extract_source(sid: str):
    s = store.one("SELECT * FROM sources WHERE id=?", (sid,))
    return enqueue(s["lecture_id"], "extract", {"source_id": sid})


@app.post("/api/lectures/{lid}/authoring/packet")
def author_packet(lid: str, data: dict):
    run, content = authoring.packet(lid, data.get("section_ids"))
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="authoring-{run[:8]}.zip"'
        },
    )


@app.get("/api/lectures/{lid}/authoring/runs")
def runs(lid: str):
    rows = store.all_rows(
        "SELECT id,status,created FROM author_runs WHERE lecture_id=? ORDER BY created DESC",
        (lid,),
    )
    for row in rows:
        row["tasks"] = store.all_rows(
            "SELECT section_id,status FROM author_tasks WHERE run_id=?", (row["id"],)
        )
    return rows


@app.post("/api/lectures/{lid}/authoring/preview")
def author_preview(lid: str, data: ResultInput):
    return authoring.proposal(lid, data.result)


@app.post("/api/lectures/{lid}/authoring/import")
def author_import(lid: str, data: ResultInput):
    return authoring.import_result(
        lid, data.result, data.revision, data.allow_conflicts
    )


@app.get("/api/lectures/{lid}/checks")
def checks(lid: str):
    return sources.source_warnings(
        LectureDocument.model_validate(store.lecture(lid)["document"]), lid
    )


@app.post("/api/math/check")
def check_math(data: dict):
    value = omml(data.get("latex", ""))
    from lxml import etree

    return {"native": True, "omml": etree.tostring(value).decode()}


@app.post("/api/figures/preview")
def figure_preview(data: dict):
    block = Block.model_validate(data["block"])
    svg, png = render(
        block, validate_theme(data.get("theme", data.get("palette", DEFAULT_THEME)))
    )
    store.record_asset(svg)
    store.record_asset(png)
    return Response(svg.read_bytes(), media_type="image/svg+xml")


@app.get("/api/lectures/{lid}/figures/{bid}")
def figure(lid: str, bid: str):
    lecture = store.lecture(lid)
    doc = LectureDocument.model_validate(lecture["document"])
    for s in doc.sections:
        for b in s.blocks:
            if b.id == bid and b.kind == "figure":
                svg, png = render(b, lecture["theme"])
                store.record_asset(svg, lid)
                store.record_asset(png, lid)
                return FileResponse(svg, media_type="image/svg+xml")
    raise LookupError("الرسم غير موجود")


@app.get("/api/lectures/{lid}/jobs")
def jobs(lid: str):
    return store.all_rows(
        "SELECT * FROM jobs WHERE lecture_id=? ORDER BY created DESC LIMIT 50", (lid,)
    )


@app.post("/api/jobs/{jid}/retry")
def retry(jid: str):
    row = store.one("SELECT * FROM jobs WHERE id=?", (jid,))
    if row["status"] != "failed":
        raise ValueError("يمكن إعادة المهام المتعثرة فقط")
    with store.transaction() as db:
        db.execute(
            "UPDATE jobs SET status='queued',error=NULL,progress=0 WHERE id=?", (jid,)
        )
        if accounts.enabled():
            db.execute("UPDATE jobs SET requested_by=? WHERE id=?",(accounts.actor.get()['id'],jid))
    return {"ok": True}


@app.post("/api/lectures/{lid}/exports")
def create_export(lid: str, data: ExportInput):
    store.lecture(lid)
    return enqueue(lid, "export", data.model_dump())


@app.get("/api/lectures/{lid}/exports")
def list_exports(lid: str):
    store.lecture(lid)
    reports = []
    for path in (store.DATA / "exports").glob("*/report.json"):
        if accounts.enabled() and not store.all_rows('SELECT id FROM private_assets WHERE relative_path=?',(str(path.relative_to(store.DATA)),)):
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["lecture_id"] == lid:
            reports.append(report)
    return sorted(reports, key=lambda x: x["created"], reverse=True)


def export_path(eid):
    if not eid.isalnum():
        raise ValueError("معرّف تصدير غير صالح")
    folder = store.DATA / "exports" / eid
    if not (folder / "report.json").exists():
        raise LookupError("التصدير غير موجود")
    if accounts.enabled() and not store.all_rows('SELECT id FROM private_assets WHERE relative_path=?',(f'exports/{eid}/report.json',)):
        raise LookupError("التصدير غير متاح")
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    store.lecture(report["lecture_id"])
    return folder


@app.get("/api/exports/{eid}/{kind}")
def export_file(eid: str, kind: str):
    folder = export_path(eid)
    if kind not in ("pdf", "docx", "report"):
        raise ValueError("نوع ملف غير صالح")
    path = folder / ("report.json" if kind == "report" else "lecture." + kind)
    return FileResponse(
        path,
        filename="CtrlTea_Lecture." + ("json" if kind == "report" else kind),
        media_type="application/pdf" if kind == "pdf" else None,
        content_disposition_type="inline" if kind == "pdf" else "attachment",
    )


@app.get("/api/exports/{eid}/pages/{number}")
def export_page(eid: str, number: int):
    import fitz

    folder = export_path(eid)
    with fitz.open(folder / "lecture.pdf") as pdf:
        if not 1 <= number <= len(pdf):
            raise ValueError("الصفحة غير موجودة")
        data = pdf[number - 1].get_pixmap(dpi=110).tobytes("png")
    return Response(data, media_type="image/png")


@app.post("/api/exports/{eid}/review")
def reviewed(eid: str):
    path = export_path(eid) / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["visual_review"] = "user_reviewed"
    report["reviewed_at"] = store.now()
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    store.record_asset(path, report["lecture_id"])
    return report


class BundleExportInput(BaseModel):
    lecture_ids: list[str] = Field(min_length=1, max_length=1000)


class BundleImportInput(BaseModel):
    bundle_id: str
    lecture_ids: list[str] = Field(min_length=1, max_length=1000)
    target_course_id: str | None = None
    target_lecture_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=0)


@app.post("/api/courses/{cid}/bundle")
def selected_lecture_bundle(cid: str, data: BundleExportInput):
    return Response(bundles.export_course(cid, data.lecture_ids), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="CtrlTea_Lectures.zip"'})


@app.get("/api/lectures/{lid}/bundle")
def single_lecture_bundle(lid: str):
    lecture = store.lecture(lid)
    return Response(bundles.export_course(lecture["course_id"], [lid]), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="CtrlTea_Lecture_Data.zip"'})


@app.post("/api/transfers/preview")
async def preview_transfer(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".zip"):
        raise ValueError("اختر حزمة ZIP مصدّرة من Ctrl+Tea")
    content = await file.read(bundles.MAX_BUNDLE + 1)
    result = bundles.preview_bundle(content)
    # Staging is separate from the database and never imports a lecture yet.
    folder = store.DATA / "bundles" / "incoming"
    folder.mkdir(exist_ok=True)
    import time
    for previous in folder.iterdir():
        if previous.suffix in (".zip", ".processing") and time.time() - previous.stat().st_mtime > 24 * 60 * 60:
            previous.unlink(missing_ok=True)
    token = uid()
    (folder / (token + ".zip")).write_bytes(content)
    return dict(result, bundle_id=token, file_name=file.filename)


@app.post("/api/transfers/import")
def import_transfer(data: BundleImportInput):
    import re
    if not re.fullmatch(r"[a-f0-9]{32}", data.bundle_id):
        raise ValueError("معرّف حزمة غير صالح")
    path = store.DATA / "bundles" / "incoming" / (data.bundle_id + ".zip")
    if not path.is_file():
        raise ValueError("انتهت معاينة الحزمة؛ أسقط الملف مجددًا")
    if data.target_course_id and data.target_lecture_id:
        raise ValueError("اختر مادة أو محاضرة وجهة واحدة")
    claimed = path.with_suffix(".processing")
    try:
        path.rename(claimed)
    except FileNotFoundError as error:
        raise ValueError("الحزمة قيد الاستيراد أو أضيفت بالفعل؛ انتظر اكتمال العملية") from error
    try:
        result = bundles.import_course(claimed.read_bytes(), data.lecture_ids, data.target_course_id,
                                       data.target_lecture_id, data.expected_revision)
    except BaseException:
        claimed.rename(path)
        raise
    claimed.unlink(missing_ok=True)
    return result


@app.get("/api/courses/{cid}/bundle")
def course_bundle(cid: str):
    return Response(
        bundles.export_course(cid),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="CtrlTea_Project.zip"'},
    )


@app.post("/api/projects/import")
async def project_import(file: UploadFile = File(...)):
    data = await file.read(220 * 1024 * 1024 + 1)
    if len(data) > 220 * 1024 * 1024:
        raise ValueError("حجم الأرشيف أكبر من 220 ميغابايت")
    return bundles.import_course(data)


@app.exception_handler(RequestValidationError)
async def request_validation(request,error):
    # Pydantic's default input echo can contain passwords/tokens.
    return JSONResponse({"detail":[{"loc":e["loc"],"msg":e["msg"],"type":e["type"]} for e in error.errors()]},status_code=422)

app.include_router(account_api.router)
app.include_router(trash.router)

# Built React application is served by the same local process.
static = store.ROOT / "frontend/dist"
app.mount(
    "/document-fonts",
    StaticFiles(directory=store.ROOT / "assets/fonts"),
    name="document-fonts",
)
if static.exists():
    app.mount("/", StaticFiles(directory=static, html=True), name="studio")
