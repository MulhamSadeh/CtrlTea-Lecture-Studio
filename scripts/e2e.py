"""Isolated browser E2E. Starts its own local server and disposable database."""

from pathlib import Path
import argparse, json, os, re, socket, sqlite3, subprocess, sys, tempfile, time, zipfile
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def run(out):
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ctrltea-e2e-") as temp:
        temp = Path(temp)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = dict(
            os.environ,
            CTRLTEA_DATA_DIR=str(temp / "data"),
            PYTHONPATH=str(ROOT / "backend"),
        )
        log = (out / "server.log").open("w")
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "ctrltea.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=base, trust_env=False, timeout=180) as api:
                for _ in range(100):
                    try:
                        if api.get("/api/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.15)
                else:
                    raise RuntimeError("Server did not start")
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(
                        executable_path=os.environ.get("CHROMIUM_EXECUTABLE_PATH")
                        or None,
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--no-zygote",
                        ],
                    )
                    context = browser.new_context(
                        viewport={"width": 1500, "height": 1000}, accept_downloads=True
                    )
                    expect.set_options(timeout=30000)
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))

                    def button(name, exact=True):
                        return page.get_by_role("button", name=name, exact=exact)

                    def tab(name):
                        page.locator("nav").get_by_role(
                            "button", name=re.compile(name)
                        ).click()

                    def download(button_locator, name):
                        with page.expect_download() as event:
                            button_locator.click()
                        path = out / name
                        event.value.save_as(path)
                        return path

                    page.goto(base)
                    button("مقرر جديد").click()
                    page.get_by_label("اسم المقرر", exact=True).fill(
                        "نظم التحكم الآلي 1"
                    )
                    button("حفظ المقرر").click()
                    button("محاضرة جديدة").click()
                    page.get_by_label("عنوان المحاضرة").fill(
                        "المحاضرة الأولى في التحكم الآلي"
                    )
                    page.get_by_role("radio", name="Honey", exact=True).check()
                    page.screenshot(path=str(out / "theme-create.png"), full_page=True)
                    button("إنشاء المحاضرة").click()
                    expect(page.locator(".source-layout")).to_be_visible()
                    cid = api.get("/api/courses").json()[0]["id"]
                    lid = api.get("/api/courses/" + cid + "/lectures").json()[0]["id"]
                    assert api.get("/api/lectures/" + lid).json()["theme"] == "honey"
                    page.locator('input[accept=".pdf,.txt,.md"]').set_input_files(
                        ROOT / "examples/references/control-original.pdf"
                    )
                    expect(
                        page.get_by_role(
                            "heading", name="control-original.pdf", exact=True
                        )
                    ).to_be_visible()
                    sid = api.get("/api/lectures/" + lid + "/sources").json()[0]["id"]
                    page.get_by_label("نوع الملف المرفوع").select_option("transcript")
                    page.get_by_label("ربط التفريغ بالأصل").select_option(sid)
                    txtfile = temp / "corrected.txt"
                    txtfile.write_text(
                        "تابع الخطوة الواحدية يساوي صفرًا قبل اللحظة صفر وواحدًا بعدها."
                    )
                    page.locator('input[accept=".pdf,.txt,.md"]').set_input_files(
                        txtfile
                    )
                    expect(
                        page.get_by_role("heading", name="corrected.txt", exact=True)
                    ).to_be_visible()
                    corrected = "تابع الخطوة الواحدية يساوي صفرًا عندما t < 0 وواحدًا عندما t ≥ 0."
                    page.get_by_label("النص المصحح", exact=True).fill(corrected)
                    button("حفظ التصحيح").click()
                    txt = next(
                        s
                        for s in api.get("/api/lectures/" + lid + "/sources").json()
                        if s["kind"] == "txt"
                    )
                    assert txt["linked_id"] == sid
                    for _ in range(50):
                        if (
                            api.get("/api/sources/" + txt["id"] + "/pages").json()[0][
                                "corrected"
                            ]
                            == corrected
                        ):
                            break
                        time.sleep(0.1)
                    else:
                        raise AssertionError("Corrected transcript did not persist")
                    reference = json.loads(
                        (ROOT / "examples/control.document.json").read_text()
                    )
                    tab("المحرر")
                    for section in reference["sections"]:
                        button("إضافة قسم").last.click()
                        page.get_by_label("عنوان القسم", exact=True).fill(
                            section["title"]
                        )
                    button("حفظ الآن").click()
                    expect(
                        page.get_by_text("كل التعديلات محفوظة", exact=True)
                    ).to_be_visible(timeout=15000)
                    outline = api.get("/api/lectures/" + lid).json()["document"][
                        "sections"
                    ]
                    assert len(outline) == len(reference["sections"])
                    for section, current in zip(reference["sections"], outline):
                        section["id"] = current["id"]
                        for b in section["blocks"]:
                            # This fixture simulates a fresh external author result,
                            # which cannot assert a prior human review decision.
                            b["issue_resolved"] = False
                            for r in b["refs"]:
                                r["source_id"] = sid
                    tab("التأليف")
                    packet = download(button("تنزيل حزمة التأليف"), "authoring.zip")
                    with zipfile.ZipFile(packet) as z:
                        manifest = json.loads(z.read("manifest.json"))
                    assert len(manifest["tasks"]) == len(outline)
                    import copy

                    invalid = {
                        "run_id": manifest["run_id"],
                        "sections": copy.deepcopy(reference["sections"][:1]),
                    }
                    invalid["sections"][0]["blocks"][0].update(
                        kind="example", problem="حقول مسألة على نوع غير صحيح"
                    )
                    invalid_file = temp / "invalid-result.json"
                    invalid_file.write_text(json.dumps(invalid, ensure_ascii=False))
                    unchanged = api.get("/api/lectures/" + lid).json()["document"]
                    page.locator('input[accept=".json"]').set_input_files(invalid_file)
                    expect(
                        page.get_by_role(
                            "heading", name="صحّح نتيجة التأليف قبل الاستيراد"
                        )
                    ).to_be_visible()
                    expect(button("اعتماد الاستيراد في المحرر")).to_have_count(0)
                    assert (
                        api.get("/api/lectures/" + lid).json()["document"] == unchanged
                    )
                    page.screenshot(
                        path=str(out / "author-validation.png"), full_page=True
                    )
                    for index, batch in enumerate(
                        [reference["sections"][:2], reference["sections"][2:]]
                    ):
                        result = temp / "result.json"
                        result.write_text(
                            json.dumps(
                                {"run_id": manifest["run_id"], "sections": batch},
                                ensure_ascii=False,
                            )
                        )
                        page.locator('input[accept=".json"]').set_input_files(result)
                        expect(
                            page.get_by_role("heading", name="مراجعة الاستيراد")
                        ).to_be_visible()
                        button("اعتماد الاستيراد في المحرر").click()
                        expect(page.locator(".editor-layout")).to_be_visible(
                            timeout=15000
                        )
                        if index == 0:
                            tab("التأليف")
                            packet = download(
                                button("تنزيل حزمة التأليف"), "authoring-resumed.zip"
                            )
                            with zipfile.ZipFile(packet) as z:
                                manifest = json.loads(z.read("manifest.json"))
                            assert len(manifest["tasks"]) == len(outline) - 2
                    assert all(
                        s["complete"]
                        for s in api.get("/api/lectures/" + lid).json()["document"][
                            "sections"
                        ]
                    )
                    button(re.compile("النظام الفيزيائي والدخل والخرج"), False).click()
                    page.get_by_label("خلية 1 1", exact=True).fill("خزان الماء")
                    button(re.compile("النمذجة والتحليل والتصميم"), False).click()
                    math = page.get_by_label("المعادلة بصيغة LaTeX", exact=True).first
                    math.fill(math.input_value() + r"\,")
                    button("فحص التوافق مع Word").first.click()
                    button(re.compile("التوابع الأساسية وتحويلاتها"), False).click()
                    page.get_by_label("نهاية المجال", exact=True).first.fill("5")
                    button("توليد الرسم للمراجعة").first.click()
                    expect(page.locator(".figure-preview").first).to_be_visible()
                    page.get_by_label("نوع العنصر الجديد").select_option("list")
                    button("إضافة عنصر").click()
                    page.get_by_label("عنصر القائمة 1", exact=True).fill(
                        r"صفر عندما \(t<0\)."
                    )
                    button("عنصر قائمة").click()
                    page.get_by_label("عنصر القائمة 2", exact=True).fill(
                        r"واحد عندما \(t\geq0\)."
                    )
                    page.get_by_label("قائمة مرقّمة").check()
                    button("حفظ الآن").click()
                    expect(
                        page.get_by_text("كل التعديلات محفوظة", exact=True)
                    ).to_be_visible(timeout=15000)
                    before = api.get("/api/lectures/" + lid).json()["document"]
                    page.reload()
                    expect(page.locator(".editor-layout")).to_be_visible()
                    assert api.get("/api/lectures/" + lid).json()["document"] == before
                    page.screenshot(path=str(out / "editor.png"), full_page=True)
                    tab("المعاينة والتصدير")
                    button("تجهيز Word وPDF").click()
                    expect(page.get_by_alt_text("معاينة الصفحة 1")).to_be_visible(
                        timeout=180000
                    )
                    export = api.get("/api/lectures/" + lid + "/exports").json()[0]
                    assert export["equations"] >= 20 and export["figures"] == 4
                    for kind, label in [("docx", "Word"), ("pdf", "PDF")]:
                        download(
                            page.get_by_role("link", name=label, exact=True),
                            "control." + kind,
                        )
                    page.screenshot(path=str(out / "export.png"), full_page=True)
                    tab("المقررات")
                    archive = download(
                        button("تصدير المشروع كاملًا"), "control-project.zip"
                    )
                    page.locator('input[accept=".zip"]').set_input_files(archive)
                    expect(
                        page.get_by_text(
                            "تمت استعادة المشروع بمصادره وتعديلاته.", exact=True
                        )
                    ).to_be_visible(timeout=30000)
                    assert len(api.get("/api/courses").json()) == 2
                    restored_cid = next(
                        c["id"]
                        for c in api.get("/api/courses").json()
                        if c["id"] != cid
                    )
                    assert (
                        api.get("/api/courses/" + restored_cid + "/lectures").json()[0][
                            "theme"
                        ]
                        == "honey"
                    )
                    page.screenshot(path=str(out / "courses.png"), full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=window.innerWidth"
                    )
                    page.screenshot(path=str(out / "mobile.png"), full_page=True)
                    assert not errors, errors
                    # Use the real API to produce the second source-grounded statistics excerpt too.
                    course = api.post("/api/courses", json={"name": "الإحصاء"}).json()
                    l = api.post(
                        "/api/courses/" + course["id"] + "/lectures",
                        json={"title": "الفئات والتوزيعات التكرارية", "theme": "olive"},
                    ).json()
                    r = api.post(
                        "/api/lectures/" + l["id"] + "/sources",
                        files={
                            "file": (
                                "statistics-original.pdf",
                                (
                                    ROOT / "examples/references/statistics-original.pdf"
                                ).read_bytes(),
                            )
                        },
                    ).json()
                    stats = json.loads(
                        (ROOT / "examples/statistics.document.json").read_text()
                    )
                    for sec in stats["sections"]:
                        for b in sec["blocks"]:
                            b["issue_resolved"] = (
                                False  # simulated fresh author, not a restored project
                            )
                            for ref in b["refs"]:
                                ref["source_id"] = r["source"]["id"]
                    resp = api.post(
                        "/api/lectures/" + l["id"] + "/authoring/import",
                        json={"result": stats, "revision": 0},
                    )
                    resp.raise_for_status()
                    api.post(
                        "/api/lectures/" + l["id"] + "/exports", json={}
                    ).raise_for_status()
                    for _ in range(800):
                        stats_exports = api.get(
                            "/api/lectures/" + l["id"] + "/exports"
                        ).json()
                        if stats_exports:
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError(
                            api.get("/api/lectures/" + l["id"] + "/jobs").text
                        )
                    for kind in ("docx", "pdf"):
                        (out / ("statistics." + kind)).write_bytes(
                            api.get(
                                "/api/exports/"
                                + stats_exports[0]["export_id"]
                                + "/"
                                + kind
                            ).content
                        )
                    (out / "statistics-project.zip").write_bytes(
                        api.get("/api/courses/" + course["id"] + "/bundle").content
                    )
                    academic_course = api.post(
                        "/api/courses", json={"name": "التحكم — المحاضرة الحالية"}
                    ).json()
                    academic_lecture = api.post(
                        "/api/courses/" + academic_course["id"] + "/lectures",
                        json={"title": "ملهم سعدية"},
                    ).json()
                    primary = api.post(
                        "/api/lectures/" + academic_lecture["id"] + "/sources",
                        files={
                            "file": (
                                "control_lecture_1_transcript.txt",
                                (
                                    ROOT
                                    / "examples/references/control_lecture_1_transcript.txt"
                                ).read_bytes(),
                            )
                        },
                    ).json()["source"]
                    original = api.post(
                        "/api/lectures/" + academic_lecture["id"] + "/sources",
                        files={
                            "file": (
                                "control-original.pdf",
                                (
                                    ROOT / "examples/references/control-original.pdf"
                                ).read_bytes(),
                            )
                        },
                    ).json()["source"]
                    academic = json.loads(
                        (ROOT / "examples/study-control.document.json").read_text()
                    )
                    for section in academic["sections"]:
                        for block in section["blocks"]:
                            for ref in block["refs"]:
                                ref["source_id"] = (
                                    primary["id"]
                                    if ref["source_id"]
                                    == "5f62b2cc305847f481f491ff178a4e3c"
                                    else original["id"]
                                )
                    response = api.post(
                        "/api/lectures/" + academic_lecture["id"] + "/authoring/import",
                        json={"result": academic, "revision": 0},
                    )
                    response.raise_for_status()
                    api.post(
                        "/api/lectures/" + academic_lecture["id"] + "/exports", json={}
                    ).raise_for_status()
                    for _ in range(800):
                        academic_exports = api.get(
                            "/api/lectures/" + academic_lecture["id"] + "/exports"
                        ).json()
                        if academic_exports:
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("Real control lecture export failed")
                    assert (
                        academic_exports[0]["equations"] == 82
                        and academic_exports[0]["figures"] == 4
                    )
                    current_math = json.loads((ROOT / "examples/omml-control.document.json").read_text())
                    math_lecture = api.post("/api/courses/"+academic_course["id"]+"/lectures",json={"title":"التحكم — اختبار OMML المختلط"}).json()
                    math_source = api.post("/api/lectures/"+math_lecture["id"]+"/sources",files={"file":("test-transcript.txt",(ROOT/"examples/references/control_lecture_1_transcript.txt").read_bytes())}).json()["source"]
                    for section in current_math["sections"]:
                        for block in section["blocks"]:
                            for ref in block["refs"]:
                                ref["source_id"]=math_source["id"]
                                ref["page"]=1
                    api.post("/api/lectures/"+math_lecture["id"]+"/authoring/import",json={"result":current_math,"revision":0}).raise_for_status()
                    api.post("/api/lectures/"+math_lecture["id"]+"/exports",json={}).raise_for_status()
                    for _ in range(800):
                        current_exports=api.get("/api/lectures/"+math_lecture["id"]+"/exports").json()
                        if current_exports:break
                        time.sleep(.2)
                    else:raise RuntimeError("Current mixed OMML lecture export failed")
                    assert current_exports[0]["pdf_math"]["visible"]==100
                    # Test both existing scientific documents in every theme through React.
                    page.set_viewport_size({"width": 1500, "height": 1000})
                    matrix = {}
                    snapshots = {}

                    def scientific_snapshot():
                        with sqlite3.connect(temp / "data/studio.sqlite3") as db:
                            return {
                                "documents": db.execute(
                                    "SELECT id,doc,revision FROM lectures ORDER BY id"
                                ).fetchall(),
                                "revisions": db.execute(
                                    "SELECT * FROM revisions ORDER BY id"
                                ).fetchall(),
                                "sources": db.execute(
                                    "SELECT * FROM sources ORDER BY id"
                                ).fetchall(),
                                "pages": db.execute(
                                    "SELECT * FROM pages ORDER BY source_id,number"
                                ).fetchall(),
                                "runs": db.execute(
                                    "SELECT * FROM author_runs ORDER BY id"
                                ).fetchall(),
                                "tasks": db.execute(
                                    "SELECT * FROM author_tasks ORDER BY run_id,section_id"
                                ).fetchall(),
                            }

                    immutable = scientific_snapshot()
                    for name, lecture_id, course_id in [
                        ("control", lid, cid),
                        ("statistics", l["id"], course["id"]),
                        (
                            "academic-control",
                            academic_lecture["id"],
                            academic_course["id"],
                        ),
                        ("current-control",math_lecture["id"],academic_course["id"]),
                    ]:
                        snapshots[lecture_id] = api.get(
                            "/api/lectures/" + lecture_id
                        ).json()["document"]
                        page.evaluate(
                            '([c,l])=>{localStorage.setItem("ct-course",c);localStorage.setItem("ct-lecture",l);localStorage.setItem("ct-tab","export")}',
                            [course_id, lecture_id],
                        )
                        page.reload()
                        expect(page.locator(".export-layout")).to_be_visible()
                        for theme in ["cinnamon", "honey", "olive"]:
                            button("إعدادات المحاضرة").click()
                            page.get_by_role(
                                "radio", name=theme.capitalize(), exact=True
                            ).check()
                            expect(
                                page.get_by_role(
                                    "radio", name=theme.capitalize(), exact=True
                                )
                            ).to_be_checked()
                            expect(button("حفظ الإعدادات")).to_be_enabled()
                            page.screenshot(
                                path=str(out / f"theme-{name}-{theme}.png"),
                                full_page=True,
                            )
                            if name == "control" and theme == "olive":
                                page.set_viewport_size({"width": 390, "height": 844})
                                assert page.evaluate(
                                    "document.documentElement.scrollWidth<=window.innerWidth"
                                )
                                page.screenshot(
                                    path=str(out / "theme-mobile.png"), full_page=True
                                )
                                page.set_viewport_size({"width": 1500, "height": 1000})
                            button("حفظ الإعدادات").click()
                            assert (
                                api.get("/api/lectures/" + lecture_id).json()["theme"]
                                == theme
                            )
                            prior = api.get(
                                "/api/lectures/" + lecture_id + "/exports"
                            ).json()[0]["export_id"]
                            # Theme-only changes must show that an old PDF still needs re-export.
                            old = api.get(
                                "/api/lectures/" + lecture_id + "/exports"
                            ).json()[0]
                            if old["theme"] != theme:
                                expect(
                                    page.get_by_text(
                                        re.compile("تغيّر المحتوى أو لون المحاضرة")
                                    )
                                ).to_be_visible()
                            button("تجهيز Word وPDF").click()
                            for _ in range(1000):
                                reports = api.get(
                                    "/api/lectures/" + lecture_id + "/exports"
                                ).json()
                                if reports and reports[0]["export_id"] != prior:
                                    break
                                time.sleep(0.15)
                            else:
                                raise RuntimeError(
                                    api.get(
                                        "/api/lectures/" + lecture_id + "/jobs"
                                    ).text
                                )
                            report = reports[0]
                            assert report["theme"] == theme
                            expect(
                                page.get_by_alt_text("معاينة الصفحة 1")
                            ).to_have_attribute(
                                "src", re.compile(report["export_id"]), timeout=15000
                            )
                            for kind, label in [("docx", "Word"), ("pdf", "PDF")]:
                                download(
                                    page.get_by_role("link", name=label, exact=True),
                                    f"{name}-{theme}.{kind}",
                                )
                            matrix[f"{name}-{theme}"] = {
                                k: report[k]
                                for k in [
                                    "pages",
                                    "equations",
                                    "figures",
                                    "theme",
                                    "revision",
                                ]
                            }
                            assert scientific_snapshot() == immutable
                            assert (
                                api.get("/api/lectures/" + lecture_id).json()[
                                    "document"
                                ]
                                == snapshots[lecture_id]
                            )
                            print(
                                f"Dashboard theme/export passed: {name}-{theme}",
                                flush=True,
                            )
                        tab("المحرر")
                        button("قراءة سريعة", False).click()
                        expect(page.locator(".reading-mode")).to_be_visible()
                        assert (
                            page.locator('select[aria-label="لون القسم"]').count() == 0
                        )
                        page.screenshot(
                            path=str(out / f"reader-{name}.png"), full_page=True
                        )
                    # Stop the application process, then reopen the exact same database.
                    server.terminate()
                    server.wait(timeout=15)
                    server = subprocess.Popen(
                        server.args, cwd=ROOT, env=env, stdout=log, stderr=log
                    )
                    for _ in range(150):
                        try:
                            if api.get("/api/health").status_code == 200:
                                break
                        except httpx.RequestError:
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Server failed to restart")
                    page.reload()
                    expect(page.locator(".editor-layout")).to_be_visible()
                    button("إعدادات المحاضرة").click()
                    expect(
                        page.get_by_role("radio", name="Olive", exact=True)
                    ).to_be_checked()
                    button("حفظ الإعدادات").click()
                    for lecture_id in [lid, l["id"], academic_lecture["id"]]:
                        row = api.get("/api/lectures/" + lecture_id).json()
                        assert (
                            row["theme"] == "olive"
                            and row["document"] == snapshots[lecture_id]
                        )
                    assert scientific_snapshot() == immutable
                    assert not errors, errors
                    summary = {
                        "passed": True,
                        "browser": "Chromium",
                        "flow": "dashboard -> sources -> external partial authoring/resume -> editor -> DOCX/PDF -> backup/restore",
                        "control": {
                            k: export[k] for k in ["pages", "equations", "figures"]
                        },
                        "statistics": {
                            k: stats_exports[0][k]
                            for k in ["pages", "equations", "figures"]
                        },
                        "javascript_errors": errors,
                        "word_application_tested": False,
                        "theme_matrix": matrix,
                        "invalid_author_result_rejected_in_ui": True,
                        "native_list_edited_and_saved_in_ui": True,
                        "actual_current_control": {
                            k: academic_exports[0][k]
                            for k in ["pages", "equations", "figures"]
                        },
                        "theme_survives_process_restart": True,
                        "theme_survives_backup_restore": True,
                        "scientific_json_bytes_revisions_sources_authoring_unchanged": True,
                    }
                    (out / "e2e-report.json").write_text(
                        json.dumps(summary, ensure_ascii=False, indent=2)
                    )
                    print(json.dumps(summary, ensure_ascii=False))
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "output/e2e")
    args = parser.parse_args()
    run(args.output.resolve())
