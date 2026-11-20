"""Regression checks tied to the diagnosed real-lecture defects, not test counts."""

import copy
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import fitz
from jsonschema import Draft202012Validator
from lxml import etree
import pytest

from ctrltea import authoring, sources, store
from ctrltea.author_validation import (
    AuthoringValidationError,
    result_schema,
    validate_result,
)
from ctrltea.exporter import build_docx, to_pdf
from ctrltea.figures import diagram
from ctrltea.mathml import NS, formulas, omml
from ctrltea.models import Block, Figure, LectureDocument, Section
from ctrltea.text_layout import direction_runs


def author_payload():
    return {
        "run_id": "run",
        "sections": [
            {
                "id": "s",
                "title": "قسم",
                "blocks": [
                    {
                        "id": "b",
                        "kind": "exercise",
                        "problem": "نص المسألة",
                        "steps": [r"\(x=1\)."],
                        "result": r"\(x^2=1\).",
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "field,value", [("latex", "x=1"), ("problem", "نص السؤال"), ("steps", ["خطوة"])]
)
def test_actual_packet_schema_rejects_fields_on_wrong_kind(field, value):
    payload = author_payload()
    payload["sections"][0]["blocks"][0] = {
        "id": "b",
        "kind": "example",
        "text": "نص مثال",
        field: value,
    }
    assert not Draft202012Validator(result_schema("run")).is_valid(payload)
    with pytest.raises(AuthoringValidationError) as exc:
        validate_result(payload, check_math=False)
    assert any(field in e["message"] for e in exc.value.errors)


def test_complete_validation_checks_cross_fields_ids_math_and_human_review(client):
    p = author_payload()
    validate_result(p)
    bad = copy.deepcopy(p)
    bad["sections"][0]["blocks"].append(copy.deepcopy(bad["sections"][0]["blocks"][0]))
    with pytest.raises(AuthoringValidationError, match="فريدة"):
        validate_result(bad)
    for block in [
        {"id": "b", "kind": "table", "headers": ["أ", "ب"], "rows": [["1"]]},
        {"id": "b", "kind": "equation", "latex": r"\unsupportedcommand{x}"},
        {"id": "b", "kind": "note", "text": "نص", "issue_resolved": True},
        {"id": "b", "kind": "explanation", "text": r"رمز \(x=1 غير مغلق"},
        {"id": "b", "kind": "list", "items": [" "]},
    ]:
        bad = copy.deepcopy(p)
        bad["sections"][0]["blocks"] = [block]
        with pytest.raises(AuthoringValidationError):
            validate_result(bad)


def test_friendly_preflight_does_not_mutate_or_import_bad_results(client, lecture):
    _, l = lecture
    s = sources.register(l["id"], "text.txt", "نص مصدر حقيقي للتأليف".encode())
    sources.extract(s["id"])
    run, packet = authoring.packet(l["id"])
    before = store.one("SELECT doc,revision FROM lectures WHERE id=?", (l["id"],))
    for result in [
        [],
        {"run_id": []},
        {"run_id": run, "sections": None},
        {
            "run_id": run,
            "sections": [
                {
                    "id": "s",
                    "title": "قسم",
                    "blocks": [{"id": "b", "kind": "example", "problem": "سؤال"}],
                }
            ],
        },
    ]:
        response = client.post(
            f'/api/lectures/{l["id"]}/authoring/preview', json={"result": result}
        )
        assert response.status_code == 422, response.text
        assert response.json()["errors"][0]["location"]
    assert before == store.one(
        "SELECT doc,revision FROM lectures WHERE id=?", (l["id"],)
    )


def test_packet_has_real_contract_offline_validator_no_design_and_no_ghost_run(
    client, lecture, tmp_path
):
    _, l = lecture
    with pytest.raises(ValueError):
        authoring.packet(l["id"])
    assert not store.all_rows("SELECT * FROM author_runs")
    s = sources.register(l["id"], "source.txt", "نص المصدر المعتمد للدراسة".encode())
    sources.extract(s["id"])
    run, data = authoring.packet(l["id"])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(tmp_path / "packet")
        instructions = z.read("instructions.txt").decode()
        assert (
            "validate_result.py" in instructions
            and "issue_resolved=false" in instructions
        )
        current = json.loads(z.read("current.json"))
        assert "settings" not in current and "theme" not in current
        example = json.loads(z.read("schema-examples.json"))
        assert Draft202012Validator(json.loads(z.read("schema.json"))).is_valid(example)
    (tmp_path / "result.json").write_text(json.dumps(example))
    result = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "packet/validate_result.py"),
            str(tmp_path / "result.json"),
            "--schema",
            str(tmp_path / "packet/schema.json"),
            "--manifest",
            str(tmp_path / "packet/manifest.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["native_word_math_checked"]


@pytest.mark.parametrize(
    "value",
    [
        "تعريف النظام الفيزيائي (Physical System) وشروطه.",
        "المتحول s (متحول لابلاس) والجهد R = 10 Ω.",
        "النظام (Input → System → Output) يعمل.",
        "الفئة [25,30[ والفئة ]2,5] ثم (Analysis).",
        "1) التحليل ثم 2) التصميم.",
    ],
)
def test_direction_segmentation_preserves_every_source_character(value):
    runs = list(direction_runs(value))
    assert "".join(text for _, text in runs) == value
    if "[25,30[" in value:
        assert any(ltr and text == "[25,30[" for ltr, text in runs)
    if "s (متحول" in value:
        assert any(ltr and text == "s" for ltr, text in runs)


def test_real_lecture_native_lists_alignment_all_math_and_science_unchanged(
    client, tmp_path
):
    # The user's valid imported control lecture, not the older demo lecture.
    path = store.ROOT / "examples/academic-control.document.json"
    raw = path.read_bytes()
    doc = LectureDocument.model_validate_json(raw)
    before = doc.model_dump_json()
    out = tmp_path / "real.docx"
    report = build_docx(doc, out)
    assert doc.model_dump_json() == before and path.read_bytes() == raw
    assert report["equations"] == len(list(formulas(doc))) == 82
    with zipfile.ZipFile(out) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        assert len(root.findall(".//m:oMath", NS)) == 82
        assert (
            len(root.findall(".//w:numPr", NS)) >= 13
        )  # 11 bullet items + two solution steps
        assert not root.xpath(
            './/w:jc[@w:val="both" or @w:val="distribute"]', namespaces=NS
        )
        assert not root.xpath(".//w:rPr/w:spacing | .//w:fitText", namespaces=NS)
        text = "".join(root.itertext())
        assert "مثال: مثال" not in text and "مسألة محلولة: مثال:" not in text
        numbering = etree.fromstring(z.read("word/numbering.xml"))
        assert numbering.xpath('.//w:lvl/w:numFmt[@w:val="decimal"]', namespaces=NS)
    from scripts.render_examples import verify_content

    verify_content(doc, out)
    with fitz.open(to_pdf(out)) as pdf:
        # Every native step stays on the same body page for this short exercise.
        matches = [p for p in pdf if "3!" in p.get_text().replace("\n", "")]
        assert matches
        spans = [
            s
            for p in pdf[1:]
            for b in p.get_text("dict")["blocks"]
            for l in b.get("lines", [])
            for s in l["spans"]
        ]
        assert any("Cairo" in s["font"] for s in spans)
        assert any(
            "LatinModernMath" in font[3] for page in pdf for font in page.get_fonts()
        )
        assert all(s["bbox"][3] < 799 or s["bbox"][1] > 799 for s in spans)


def test_vector_diagram_crops_empty_coordinate_space_and_shapes_labels(client):
    spec = Figure(
        kind="block_diagram",
        nodes=[
            {"id": "a", "label": "الدخل u(t)", "x": 150, "y": 400},
            {"id": "b", "label": "النظام الفيزيائي", "x": 500, "y": 400},
            {"id": "c", "label": "الخرج y(t)", "x": 850, "y": 400},
        ],
        edges=[{"start": "a", "end": "b"}, {"start": "b", "end": "c"}],
    )
    before = spec.model_dump_json()
    root = etree.fromstring(diagram(spec, "#8B3F25", "#F6E1D3").encode())
    x, y, width, height = map(float, root.get("viewBox").split())
    assert y > 300 and width / height > 5
    assert root.findall(".//{http://www.w3.org/2000/svg}use")
    assert not root.findall(
        ".//{http://www.w3.org/2000/svg}text"
    )  # joined outlined glyphs
    assert len(root.findall(".//{http://www.w3.org/2000/svg}rect")) == 3
    assert before == spec.model_dump_json()


def test_statistics_does_not_end_with_a_page_containing_only_end_marker(
    client, tmp_path
):
    from ctrltea import bundles
    from ctrltea.exporter import export_lecture

    restored = bundles.import_course(
        (store.ROOT / "examples/projects/statistics-project.zip").read_bytes()
    )
    lid = store.one(
        "SELECT id FROM lectures WHERE course_id=?", (restored["course_id"],)
    )["id"]
    before = store.one("SELECT doc,revision FROM lectures WHERE id=?", (lid,))
    report = export_lecture(lid)
    with fitz.open(store.DATA / "exports" / report["export_id"] / "lecture.pdf") as pdf:
        for page in pdf:
            body = page.get_text(clip=fitz.Rect(0, 0, 595, 799)).strip()
            assert body and body != "انتهت المحاضرة"
        assert len(pdf) == 5
    assert store.one("SELECT doc,revision FROM lectures WHERE id=?", (lid,)) == before


def test_legacy_full_author_result_cannot_manufacture_human_approval(client, lecture):
    _, l = lecture
    doc = LectureDocument(
        sections=[
            Section(
                title="مراجعة",
                blocks=[
                    Block(
                        kind="warning",
                        text="توضيح",
                        issue="خطأ في المصدر",
                        correction="تصحيح مقترح",
                        issue_resolved=True,
                    )
                ],
            )
        ]
    )
    result = client.post(
        f'/api/lectures/{l["id"]}/authoring/preview', json={"result": doc.model_dump()}
    )
    assert (
        result.status_code == 422
        and result.json()["errors"][0]["path"][-1] == "issue_resolved"
    )
    assert store.lecture(l["id"])["revision"] == 0
    # Explicit editor review is supported; importing the same reviewed block preserves it.
    saved = client.put(
        f'/api/lectures/{l["id"]}', json={"document": doc.model_dump(), "revision": 0}
    )
    assert saved.status_code == 200
    result = client.post(
        f'/api/lectures/{l["id"]}/authoring/preview', json={"result": doc.model_dump()}
    )
    assert (
        result.status_code == 200
        and result.json()["document"]["sections"][0]["blocks"][0]["issue_resolved"]
    )


def test_long_exercise_flows_at_step_boundaries_without_losing_steps(client, tmp_path):
    steps = [
        f"STEP{i:02}_BEGIN "
        + ("شرح خطوة مترابطة في الحل لاختبار توزيع السطور. " * 4)
        + f" STEP{i:02}_END"
        for i in range(1, 15)
    ]
    doc = LectureDocument(
        title="توزيع تمرين طويل",
        sections=[
            Section(
                title="اختبار الحدود المنطقية للخطوات",
                blocks=[
                    Block(
                        kind="exercise",
                        title="تمرين طويل",
                        problem="نص المسألة يبقى مع بداية الحل.",
                        steps=steps,
                        result="FINAL_RESULT",
                    )
                ],
            )
        ],
    )
    path = tmp_path / "long-exercise.docx"
    build_docx(doc, path)
    with fitz.open(to_pdf(path)) as pdf:
        pages = [p.get_text() for p in pdf][1:]
        assert len(pages) >= 2
        for i in range(1, 15):
            start = next(
                n for n, text in enumerate(pages) if f"STEP{i:02}_BEGIN" in text
            )
            end = next(n for n, text in enumerate(pages) if f"STEP{i:02}_END" in text)
            assert start == end  # each short logical step stays intact
        assert "FINAL_RESULT" in pages[-1]
        assert all(text.strip() != "انتهت المحاضرة" for text in pages)
