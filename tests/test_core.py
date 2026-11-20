import io
import json
import zipfile
from unittest.mock import patch

import numpy as np
import pytest
from lxml import etree
from pydantic import ValidationError
from ctrltea import store, sources, authoring, bundles
from ctrltea.models import LectureDocument, Section, Block, Figure, Reference
from ctrltea.figures import evaluate, render
from ctrltea.mathml import omml, NS


def add_source(client, lid, text="نص علمي معتمد من المصدر لاختبار حفظ وتصحيح المحاضرة."):
    r = client.post(
        f"/api/lectures/{lid}/sources",
        files={"file": ("transcript.txt", text.encode())},
        data={"role": "primary", "priority": "0"},
    )
    assert r.status_code == 200, r.text
    source = r.json()["source"]
    sources.extract(source["id"])
    return source


def test_save_conflict_and_revision_restore(client, lecture):
    course, l = lecture
    doc = l["document"]
    doc["title"] = "عنوان معدل"
    r = client.put("/api/lectures/" + l["id"], json={"document": doc, "revision": 0})
    assert r.status_code == 200
    assert (
        client.put("/api/lectures/" + l["id"], json={"document": doc, "revision": 0}).status_code
        == 409
    )
    rev = client.get(f'/api/lectures/{l["id"]}/revisions').json()[0]
    old = client.post(
        f'/api/lectures/{l["id"]}/revisions/{rev["id"]}/restore', json={"revision": 1}
    ).json()
    assert old["title"] == l["title"] and old["revision"] == 2


def test_corrected_text_never_replaced(client, lecture):
    c, l = lecture
    s = add_source(client, l["id"])
    raw = store.one("SELECT raw FROM pages WHERE source_id=?", (s["id"],))["raw"]
    sources.update_page(s["id"], 1, "التفريغ المصحح النهائي", False)
    with patch("ctrltea.sources.subprocess.run", side_effect=AssertionError("OCR must not run")):
        sources.extract(s["id"])
    p = client.get(f'/api/sources/{s["id"]}/pages').json()[0]
    assert p["raw"] == raw and p["corrected"] == "التفريغ المصحح النهائي"


def test_duplicate_source_and_transcript_page_mapping(client, lecture):
    c, l = lecture
    s = add_source(client, l["id"], "أول صفحة\fثاني صفحة")
    same = add_source(client, l["id"], "أول صفحة\fثاني صفحة")
    assert same["id"] == s["id"]
    rows = client.get(f'/api/sources/{s["id"]}/pages').json()
    assert [p["raw"] for p in rows] == ["أول صفحة", "ثاني صفحة"]
    assert (
        client.post(
            f'/api/sources/{s["id"]}/pages', json={"number": 5, "corrected": "نص الصفحة الخامسة"}
        ).status_code
        == 200
    )
    assert client.get(f'/api/sources/{s["id"]}/pages').json()[-1]["number"] == 5


def test_authoring_packet_exclusions_and_resume(client, lecture):
    c, l = lecture
    s = add_source(client, l["id"], "الأصل النصي للتأليف")
    sources.update_page(s["id"], 1, "النص المصحح الأساسي", False)
    doc = LectureDocument.model_validate(l["document"])
    doc.sections = [
        Section(id="done", title="مكتمل", complete=True),
        Section(id="todo", title="المطلوب"),
    ]
    store.save_document(l["id"], doc.model_dump(), 0)
    run, data = authoring.packet(l["id"])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert [t["section_id"] for t in manifest["tasks"]] == ["todo"]
        assert z.read(f'sources/{s["id"]}/page-0001.txt').decode() == "النص المصحح الأساسي"
    section = Section(
        id="todo",
        title="المطلوب",
        blocks=[
            Block(
                kind="explanation",
                text="النص المصحح الأساسي",
                refs=[Reference(source_id=s["id"], quote="النص المصحح الأساسي")],
            )
        ],
        complete=True,
    )
    payload = {"run_id": run, "sections": [section.model_dump()]}
    result = authoring.import_result(l["id"], payload, 1)
    assert len(result["document"]["sections"]) == 2
    assert store.one("SELECT status FROM author_runs WHERE id=?", (run,))["status"] == "complete"
    sources.update_page(s["id"], 1, "النص المصحح الأساسي", True)
    with pytest.raises(ValueError, match="لا يوجد نص"):
        authoring.packet(l["id"], ["todo"])


def test_import_detects_manual_changes(client, lecture):
    c, l = lecture
    s = add_source(client, l["id"])
    section = Section(
        id="target", title="قسم", blocks=[Block(kind="explanation", text="النص الأول")]
    )
    doc = LectureDocument.model_validate(l["document"])
    doc.sections = [section]
    store.save_document(l["id"], doc.model_dump(), 0)
    run, data = authoring.packet(l["id"])
    doc.sections[0].blocks[0].text = "تعديل يدوي مهم"
    store.save_document(l["id"], doc.model_dump(), 1)
    payload = {"run_id": run, "sections": [section.model_dump()]}
    assert authoring.proposal(l["id"], payload)["conflicts"] == ["target"]
    with pytest.raises(store.Conflict):
        authoring.import_result(l["id"], payload, 2)
    assert (
        store.lecture(l["id"])["document"]["sections"][0]["blocks"][0]["text"] == "تعديل يدوي مهم"
    )


def test_verbatim_question_change_reported(client, lecture):
    c, l = lecture
    s = add_source(client, l["id"], "أوجد تحويل لابلاس للتابع المعطى.")
    doc = LectureDocument(
        sections=[
            Section(
                title="مسألة",
                blocks=[
                    Block(
                        kind="exercise",
                        problem="أوجد التحويل.",
                        verbatim=True,
                        refs=[
                            Reference(source_id=s["id"], quote="أوجد تحويل لابلاس للتابع المعطى.")
                        ],
                    )
                ],
            )
        ]
    )
    check = sources.source_warnings(doc, l["id"])
    assert any(x["severity"] == "error" for x in check["issues"])
    assert check["covered_pages"] == 1


def test_project_round_trip_preserves_assets_history_and_references(client, lecture):
    c, l = lecture
    s = add_source(client, l["id"], "النص الأصلي")
    sources.update_page(s["id"], 1, "نص مصحح", False)
    doc = LectureDocument.model_validate(l["document"])
    doc.sections = [
        Section(
            title="قسم",
            blocks=[Block(kind="explanation", text="نص مصحح", refs=[Reference(source_id=s["id"])])],
        )
    ]
    store.save_document(l["id"], doc.model_dump(), 0)
    result = bundles.import_course(bundles.export_course(c["id"]))
    new_l = store.one("SELECT * FROM lectures WHERE course_id=?", (result["course_id"],))
    new_source = store.one("SELECT * FROM sources WHERE lecture_id=?", (new_l["id"],))
    assert new_source["id"] != s["id"]
    assert (
        store.source_path(new_source["id"]).read_bytes() == store.source_path(s["id"]).read_bytes()
    )
    assert (
        json.loads(new_l["doc"])["sections"][0]["blocks"][0]["refs"][0]["source_id"]
        == new_source["id"]
    )
    assert (
        store.one("SELECT corrected FROM pages WHERE source_id=?", (new_source["id"],))["corrected"]
        == "نص مصحح"
    )
    assert len(store.all_rows("SELECT * FROM revisions WHERE lecture_id=?", (new_l["id"],))) == 1


def test_zip_traversal_rejected(client):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("../escape", "bad")
    with pytest.raises(ValueError, match="مسار"):
        bundles.import_course(data.getvalue())


@pytest.mark.parametrize(
    "expression",
    [
        '__import__("os").getcwd()',
        "x.__class__",
        "[x for x in range(10)]",
        "2**100000",
        'open("x")',
        "sin(x, y)",
        "x[0]",
    ],
)
def test_numeric_expression_language_rejects_code(expression):
    with pytest.raises((ValueError, SyntaxError)):
        evaluate(expression, np.array([0.0, 1.0]))


def test_numeric_plot_is_mathematically_correct():
    x = np.array([-1.0, 0.0, 1.0, 2.0])
    assert np.allclose(evaluate("t*step(t)", x), [0, 0, 1, 2])
    assert np.allclose(evaluate("exp(-x)", x), np.exp(-x))


@pytest.mark.parametrize(
    "latex,tag",
    [
        (r"\frac{1}{s^2}", "f"),
        (r"\frac{\frac{a}{b}}{c}", "f"),
        (r"\int_0^\infty e^{-st}\,dt", "nary"),
        (r"\frac{d^2 y}{dt^2}", "f"),
        (r"x_i^2", "sSubSup"),
        (r"\begin{bmatrix}1&2\\3&4\end{bmatrix}", "m"),
        (r"\sqrt{x+1}", "rad"),
        (r"\dot{\theta}(t)", "acc"),
    ],
)
def test_native_math_semantic_structure(client, latex, tag):
    result = omml(latex)
    assert etree.QName(result).localname == "oMath"
    assert result.find(".//m:" + tag, NS) is not None
    assert result.findall(".//m:t", NS)


@pytest.mark.parametrize("latex", [r"\unsupportedThing{a}", r"\input{/etc/passwd}", ""])
def test_unsupported_math_is_not_silently_dropped(client, latex):
    with pytest.raises(ValueError):
        omml(latex)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "table", "headers": ["a"], "rows": [["1", "2"]]},
        {"kind": "equation", "latex": ""},
        {"kind": "figure", "figure": Figure(kind="step")},
        {"kind": "exercise", "problem": ""},
    ],
)
def test_invalid_blocks_rejected(kwargs):
    with pytest.raises(ValidationError):
        Block(**kwargs)


@pytest.mark.parametrize(
    "kind",
    ["step", "ramp", "impulse", "plot", "scatter", "bar", "histogram", "block_diagram", "circuit"],
)
def test_scientific_svg_and_fallback_are_created(client, lecture, kind):
    c, l = lecture
    s = add_source(client, l["id"])
    spec = {"kind": kind}
    if kind in ("plot", "scatter"):
        spec["series"] = (
            [{"expression": "x^2"}] if kind == "plot" else [{"x": [1, 2, 3], "y": [1, 4, 9]}]
        )
    if kind == "bar":
        spec.update(labels=["A", "B"], values=[6, 8])
    if kind == "histogram":
        spec["values"] = [1, 1, 2, 3, 3, 4]
    if kind in ("block_diagram", "circuit"):
        spec.update(
            nodes=[
                {"id": "a", "label": "u(t)", "x": 70, "y": 70},
                {"id": "b", "label": "y(t)", "x": 270, "y": 70},
            ],
            edges=[
                {
                    "start": "a",
                    "end": "b",
                    "kind": "resistor" if kind == "circuit" else "arrow",
                    "label": "R" if kind == "circuit" else "",
                }
            ],
        )
    b = Block(kind="figure", figure=Figure(**spec), refs=[Reference(source_id=s["id"])])
    svg, png = render(b, "cinnamon")
    assert etree.parse(str(svg)).getroot().tag.endswith("svg")
    assert png.read_bytes().startswith(b"\x89PNG")
    assert svg.stat().st_size > 300


def test_pending_job_recovered_after_restart(client, lecture):
    c, l = lecture
    with store.connect() as db:
        db.execute(
            "INSERT INTO jobs(id,lecture_id,kind,status,payload,created,updated) VALUES(?,?,?,?,?,?,?)",
            ("interrupted", l["id"], "extract", "running", "{}", store.now(), store.now()),
        )
    store.init()
    assert store.one("SELECT status FROM jobs WHERE id=?", ("interrupted",))["status"] == "queued"


def test_cross_origin_mutation_rejected(client):
    r = client.post(
        "/api/courses", json={"name": "bad"}, headers={"Origin": "https://unrelated.example"}
    )
    assert r.status_code == 403


def test_invalid_source_type_rejected(client, lecture):
    c, l = lecture
    r = client.post(f'/api/lectures/{l["id"]}/sources', files={"file": ("program.exe", b"content")})
    assert r.status_code == 422


def test_unfinished_external_packet_can_resume_after_project_transfer(client, lecture):
    course, l = lecture
    s = add_source(client, l["id"], "نص المصدر المعتمد")
    doc = LectureDocument.model_validate(l["document"])
    section = Section(id="unfinished", title="قسم ينتظر المؤلف")
    doc.sections = [section]
    store.save_document(l["id"], doc.model_dump(), 0)
    run, data = authoring.packet(l["id"])
    restored = bundles.import_course(bundles.export_course(course["id"]))
    new_l = store.one("SELECT * FROM lectures WHERE course_id=?", (restored["course_id"],))
    section.blocks = [
        Block(
            kind="explanation",
            text="نص المصدر المعتمد",
            refs=[Reference(source_id=s["id"], quote="نص المصدر المعتمد")],
        )
    ]
    section.complete = True
    imported = authoring.import_result(
        new_l["id"], {"run_id": run, "sections": [section.model_dump()]}, new_l["revision"]
    )
    actual = imported["document"]["sections"][0]
    assert actual["complete"]
    assert actual["blocks"][0]["refs"][0]["source_id"] != s["id"]
    current_run = store.one("SELECT * FROM author_runs WHERE lecture_id=?", (new_l["id"],))
    assert current_run["status"] == "complete"
