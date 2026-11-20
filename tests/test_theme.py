"""Theme metadata, safe migration, backups and actual rendered color coverage."""

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import fitz
import pytest
from lxml import etree

from ctrltea import bundles, store, sources
from ctrltea.exporter import build_docx, to_pdf
from ctrltea.figures import render
from ctrltea.mathml import NS, omml
from ctrltea.models import LectureDocument, Section, Block, Figure, Reference
from ctrltea.theme import DEFAULT_THEME, PALETTES


def test_legacy_migration_preserves_raw_document_and_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    raw = json.dumps(
        LectureDocument(title="محاضرة قديمة").model_dump(), ensure_ascii=False, indent=3
    )
    with sqlite3.connect(tmp_path / "studio.sqlite3") as db:
        db.executescript(
            """CREATE TABLE courses(id TEXT PRIMARY KEY,name TEXT NOT NULL,doctor TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE lectures(id TEXT PRIMARY KEY,course_id TEXT NOT NULL REFERENCES courses(id),title TEXT NOT NULL,doc TEXT NOT NULL,revision INTEGER NOT NULL,updated TEXT NOT NULL);"""
        )
        db.execute("INSERT INTO courses VALUES(?,?,?,?)", ("c", "مقرر", "دكتور", "original"))
        db.execute(
            "INSERT INTO lectures VALUES(?,?,?,?,?,?)",
            ("l", "c", "محاضرة قديمة", raw, 7, "original"),
        )
    store.init()
    store.init()
    row = store.one("SELECT * FROM lectures WHERE id=?", ("l",))
    assert row["doc"] == raw and row["revision"] == 7 and row["updated"] == "original"
    assert row["theme"] == DEFAULT_THEME
    with store.connect() as db:
        assert [r["name"] for r in db.execute("PRAGMA table_info(lectures)")].count("theme") == 1


def test_theme_api_is_independent_of_document_history_and_authoring(client, lecture):
    c, l = lecture
    other = client.post(
        f'/api/courses/{c["id"]}/lectures', json={"title": "مستقلة", "theme": "honey"}
    ).json()
    original = store.one("SELECT * FROM lectures WHERE id=?", (l["id"],))
    design = client.get("/api/design").json()
    assert {
        t["id"]: tuple(t[k] for k in ["dark", "medium", "light"]) for t in design["themes"]
    } == PALETTES
    schema = client.get("/api/schema").content
    for theme in PALETTES:
        result = client.put(f'/api/lectures/{l["id"]}/theme', json={"theme": theme})
        assert result.status_code == 200 and result.json()["theme"] == theme
        current = store.one("SELECT * FROM lectures WHERE id=?", (l["id"],))
        assert current["doc"] == original["doc"] and current["revision"] == original["revision"]
    assert client.get(f'/api/lectures/{other["id"]}').json()["theme"] == "honey"
    assert not store.all_rows("SELECT * FROM revisions")
    assert not store.all_rows("SELECT * FROM jobs")
    assert not store.all_rows("SELECT * FROM author_runs")
    assert client.get("/api/schema").content == schema
    assert client.put(f'/api/lectures/{l["id"]}/theme', json={"theme": "blue"}).status_code == 422
    assert (
        client.post(
            f'/api/courses/{c["id"]}/lectures', json={"title": "invalid", "theme": "blue"}
        ).status_code
        == 422
    )
    assert client.put("/api/lectures/missing/theme", json={"theme": "olive"}).status_code == 404
    # A stale content editor cannot overwrite a theme change when its autosave completes.
    assert (
        client.put(
            f'/api/lectures/{l["id"]}', json={"document": l["document"], "revision": l["revision"]}
        ).json()["theme"]
        == "olive"
    )


def test_bundle_preserves_theme_and_old_archives_default_safely(client, lecture):
    c, l = lecture
    store.set_theme(l["id"], "olive")
    archive = bundles.export_course(c["id"])
    restored = bundles.import_course(archive)
    row = store.one("SELECT * FROM lectures WHERE course_id=?", (restored["course_id"],))
    assert row["theme"] == "olive"
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(files["project.json"])
    manifest["lectures"][0].pop("theme")
    files["project.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    old = bundles.import_course(output.getvalue())
    assert (
        store.one("SELECT theme FROM lectures WHERE course_id=?", (old["course_id"],))["theme"]
        == DEFAULT_THEME
    )
    manifest["lectures"][0]["theme"] = "invalid"
    invalid = io.BytesIO()
    with zipfile.ZipFile(invalid, "w") as z:
        z.writestr("project.json", json.dumps(manifest))
    before = store.all_rows("SELECT * FROM courses")
    with pytest.raises(ValueError, match="لون المحاضرة"):
        bundles.import_course(invalid.getvalue())
    assert store.all_rows("SELECT * FROM courses") == before


@pytest.mark.parametrize("theme", PALETTES)
def test_lecture_theme_covers_shared_page_boxes_table_footer_svg_and_omml(
    client, lecture, tmp_path, theme
):
    _, l = lecture
    source = sources.register(l["id"], "reference.txt", "المحتوى المرجعي".encode())
    block = Block(
        kind="figure",
        figure=Figure(kind="step", caption="تابع الخطوة"),
        refs=[Reference(source_id=source["id"])],
    )
    doc = LectureDocument(
        title="فحص تصميم المحاضرة",
        sections=[
            Section(
                title="القسم الأول",
                palette="cinnamon",
                blocks=[
                    Block(kind="rule", text="قانون موثق من المصدر."),
                    Block(kind="equation", latex=r"\frac{x_i}{2}=4"),
                ],
            ),
            Section(
                title="القسم الثاني",
                palette="olive",
                blocks=[Block(kind="table", headers=["RIGHT", "LEFT"], rows=[["25", "6"]]), block],
            ),
        ],
    )
    before = doc.model_dump_json()
    output = tmp_path / (theme + ".docx")
    build_docx(doc, output, theme=theme)
    assert doc.model_dump_json() == before
    dark, medium, light = PALETTES[theme]
    with zipfile.ZipFile(output) as z:
        xml = etree.fromstring(z.read("word/document.xml"))
        heading_colors = xml.xpath(
            './/w:p[w:pPr/w:pStyle[@w:val="Heading1"]]//w:color/@w:val', namespaces=NS
        )
        assert heading_colors and set(heading_colors) == {dark[1:]}
        box=xml.xpath('.//w:tbl[count(w:tr)=1 and count(w:tr/w:tc)=1 and w:tblPr/w:tblBorders]',namespaces=NS)[0]
        assert all(box.find("w:tblPr/w:tblBorders/w:"+side,NS)is not None for side in ["top","left","bottom","right"])
        from ctrltea.theme import academic_box_style
        assert box.find("w:tr/w:tc/w:tcPr/w:shd",NS).get("{"+NS["w"]+"}fill")==academic_box_style("rule",dark,light)["fill"][1:]
        table = xml.xpath(".//w:tbl[w:tblPr/w:bidiVisual and w:tr[1]//w:t[text()='RIGHT']]", namespaces=NS)[0]
        assert set(table.xpath("./w:tr[1]/w:tc/w:tcPr/w:shd/@w:fill", namespaces=NS)) == {dark[1:]}
        assert set(table.xpath("./w:tr[1]//w:color/@w:val", namespaces=NS)) == {"FFFFFF"}
        assert (
            table.find(".//w:tblHeader", NS) is not None
            and table.find(".//w:cantSplit", NS) is not None
        )

        def expanded(node):
            return (node.tag, sorted(node.attrib.items()), node.text, [expanded(c) for c in node])

        assert expanded(xml.find(".//m:oMath", NS)) == expanded(omml(r"\frac{x_i}{2}=4"))
        vectors = [z.read(n).decode() for n in z.namelist() if n.endswith(".svg")]
        assert len(vectors) == 1 and dark.lower() in vectors[0].lower()
    with fitz.open(to_pdf(output)) as pdf:
        assert len(pdf) == 2  # Two differently labeled legacy sections share a themed page.
        pix = pdf[1].get_pixmap(dpi=72)
        assert max(abs(a - b) for a, b in zip(pix.pixel(20, 820)[:3], bytes.fromhex(dark[1:]))) <= 2
        assert (
            max(abs(a - b) for a, b in zip(pix.pixel(560, 820)[:3], bytes.fromhex(medium[1:]))) <= 2
        )  # PDF image encoding may round by one channel level
        assert any("Cairo" in f[3] for f in pdf[1].get_fonts())


def test_source_crop_is_not_recolored_or_duplicated_by_theme(client, lecture, tmp_path):
    _, l = lecture
    pdf = fitz.open()
    page = pdf.new_page()
    page.draw_rect(fitz.Rect(20, 20, 200, 200), color=(0, 0, 1), fill=(1, 0, 0))
    page.insert_text((40, 80), "Original")
    source = sources.register(l["id"], "source.pdf", pdf.tobytes())
    pdf.close()
    block = Block(
        kind="figure", figure=Figure(kind="source_crop"), refs=[Reference(source_id=source["id"])]
    )
    results = [render(block, t) for t in PALETTES]
    assert len({str(p[0]) for p in results}) == 1
    assert len({p[1].read_bytes() for p in results}) == 1


def test_native_math_in_dark_header_uses_readable_light_inset(client, tmp_path):
    doc = LectureDocument(
        title="اختبار جدول رياضي",
        sections=[
            Section(
                title="جدول",
                blocks=[
                    Block(
                        kind="table",
                        headers=[r"القيمة \(x_i^2\)", r"\(\frac{1}{2}\)"],
                        rows=[["10", "20"]],
                    )
                ],
            )
        ],
    )
    path = tmp_path / "math-header.docx"
    before = doc.model_dump_json()
    build_docx(doc, path, theme="olive")
    assert doc.model_dump_json() == before
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        table = root.xpath(".//w:tbl[w:tblPr/w:bidiVisual and w:tr[1]//m:oMath]", namespaces=NS)[0]
        assert len(table.findall(".//m:oMath", NS)) == 2
        assert set(table.xpath("./w:tr[1]/w:tc/w:tcPr/w:shd/@w:fill", namespaces=NS)) == {"556B2F"}
        assert set(table.xpath("./w:tr[1]/w:tc/w:p/w:pPr/w:shd/@w:fill", namespaces=NS)) == {
            "E9F0D7"
        }
        assert root.find(".//m:f", NS) is not None and root.find(".//m:sSubSup", NS) is not None
    with fitz.open(to_pdf(path)) as pdf:
        spans = [
            s
            for b in pdf[1].get_text("dict")["blocks"]
            for l in b.get("lines", [])
            for s in l["spans"]
            if s["bbox"][1] < 799
        ]
        assert any(s["text"] == "x" and s["color"] == 0 for s in spans)
        assert any(s["text"] == "1" and s["color"] == 0 for s in spans)


def test_multiple_curves_remain_distinguishable_in_monochrome(client, lecture):
    from ctrltea.models import Series

    _, l = lecture
    source = sources.register(l["id"], "curves.txt", "مواصفات رسم الاختبار".encode())
    block = Block(
        kind="figure",
        figure=Figure(
            kind="plot",
            series=[
                Series(label="Curve A", x=[0, 1, 2], y=[0, 1, 2]),
                Series(label="Curve B", x=[0, 1, 2], y=[2, 1, 0]),
            ],
        ),
        refs=[Reference(source_id=source["id"])],
    )
    before = block.model_dump_json()
    svg, _ = render(block, "honey")
    assert block.model_dump_json() == before
    root = etree.fromstring(svg.read_bytes())
    ns = {"svg": "http://www.w3.org/2000/svg"}
    curves = root.xpath(
        './/svg:g[starts-with(@id,"line2d_")][svg:path[contains(@style,"stroke-width: 1.8")]]',
        namespaces=ns,
    )
    assert len(curves) >= 2
    assert not curves[0].findall(".//{" + ns["svg"] + "}use")
    assert curves[1].findall(".//{" + ns["svg"] + "}use")  # sparse markers survive gray printing


def test_all_eight_supported_scatter_series_have_distinct_shapes(client, lecture):
    from ctrltea.models import Series

    _, l = lecture
    source = sources.register(l["id"], "scatter.txt", "مواصفات اختبار الطباعة الرمادية".encode())
    block = Block(
        kind="figure",
        figure=Figure(
            kind="scatter",
            series=[Series(label=f"Series {i}", x=[0, 1], y=[i, i + 1]) for i in range(8)],
        ),
        refs=[Reference(source_id=source["id"])],
    )
    before = block.model_dump_json()
    svg, _ = render(block, "olive")
    root = etree.fromstring(svg.read_bytes())
    ns = {"svg": "http://www.w3.org/2000/svg"}
    shapes = root.xpath(
        './/svg:g[starts-with(@id,"PathCollection_")]/svg:defs/svg:path/@d', namespaces=ns
    )
    assert len(shapes) == 8 and len(set(shapes)) == 8
    assert block.model_dump_json() == before
