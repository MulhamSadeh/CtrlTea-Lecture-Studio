import io
import zipfile
import fitz
import pytest
from lxml import etree
from PIL import Image, ImageDraw, ImageFont
from ctrltea import store, sources
from ctrltea.models import LectureDocument, Section, Block, Reference, Figure
from ctrltea.exporter import build_docx, to_pdf, export_lecture
from ctrltea.mathml import NS


def test_docx_pdf_native_math_table_direction_two_sections_one_page(
    client, lecture, tmp_path
):
    c, l = lecture
    doc = LectureDocument(
        title="تجربة تنسيق",
        sections=[
            Section(
                id="first",
                title="قسم القرفة",
                blocks=[
                    Block(
                        kind="definition",
                        text="نص عربي مع وحدات R = 10 Ω ورموز لاتينية للمقارنة.",
                    ),
                    Block(
                        kind="equation", latex=r"\frac{d^2 y}{dt^2}+3\frac{dy}{dt}=u(t)"
                    ),
                ],
            ),
            Section(
                id="second",
                title="قسم الزيتون",
                palette="olive",
                blocks=[
                    Block(
                        kind="table",
                        headers=["RIGHT_HEADER", "LEFT_HEADER"],
                        rows=[["25", "6"], ["30", "8"]],
                    ),
                    Block(
                        kind="explanation",
                        text=r"المعادلة داخل النص \(x_i^2=4\) لا تنعكس.",
                    ),
                ],
            ),
        ],
    )
    output = tmp_path / "sample.docx"
    report = build_docx(doc, output)
    assert report["equations"] == 2 and not report["word_application_tested"]
    with zipfile.ZipFile(output) as z:
        xml = etree.fromstring(z.read("word/document.xml"))
        assert xml.find(".//w:bidiVisual", NS) is not None
        assert xml.find(".//m:f", NS) is not None
        styles = etree.fromstring(z.read("word/styles.xml"))
        assert styles.find(".//w:pBdr", NS) is None
        assert (
            "8B3F25" in z.read("word/document.xml").decode()
            and "556B2F" not in z.read("word/document.xml").decode()
        )
    pdf = to_pdf(output)
    with fitz.open(pdf) as d:
        assert (
            len(d) == 2
        )  # original cover includes the linked index; both sections share body page
        assert len(d[0].get_links()) == 2
        words = d[1].get_text("words")
        right = next(w for w in words if w[4] == "RIGHT_HEADER")
        left = next(w for w in words if w[4] == "LEFT_HEADER")
        assert right[0] > left[0]
        assert any("Cairo" in f[3] for f in d[1].get_fonts())


def test_long_table_repeats_header_and_keeps_last_row(client, tmp_path):
    doc = LectureDocument(
        title="جدول طويل",
        sections=[
            Section(
                title="البيانات",
                blocks=[
                    Block(
                        kind="table",
                        title="نتائج البيانات",
                        headers=["VALUE", "FREQUENCY"],
                        rows=[[f"ITEM{i}", str(i)] for i in range(1, 81)],
                    )
                ],
            )
        ],
    )
    p = tmp_path / "long.docx"
    build_docx(doc, p)
    pdf = to_pdf(p)
    with fitz.open(pdf) as d:
        pages = [p.get_text() for p in d][1:]
        assert len(pages) > 2
        assert "ITEM80" in "".join(pages)
        assert sum("FREQUENCY" in p for p in pages) >= 3


def test_svg_is_embedded_and_pdf_contains_figure(client, lecture, tmp_path):
    c, l = lecture
    s = sources.register(
        l["id"], "source.txt", "رسم الخطوة الواحدية من المصدر".encode()
    )
    sources.extract(s["id"])
    doc = LectureDocument(
        title="الخطوة الواحدية",
        sections=[
            Section(
                title="الإشارة",
                blocks=[
                    Block(
                        kind="figure",
                        figure=Figure(kind="step", caption="تابع الخطوة الواحدية"),
                        refs=[Reference(source_id=s["id"])],
                    )
                ],
            )
        ],
    )
    p = tmp_path / "figure.docx"
    r = build_docx(doc, p)
    assert r["figures"] == 1
    with zipfile.ZipFile(p) as z:
        assert any(n.endswith(".svg") for n in z.namelist())
        assert b"svgBlip" in z.read("word/document.xml")
    with fitz.open(to_pdf(p)) as pdf:
        assert len(pdf[1].get_images()) >= 1 or len(pdf[1].get_drawings()) > 3


def test_actual_local_ocr_and_corrected_cache(client, lecture, tmp_path):
    c, l = lecture
    image = Image.new("RGB", (1200, 300), "white")
    font = ImageFont.truetype(str(store.ROOT / "assets/fonts/Cairo-Regular.ttf"), 60)
    ImageDraw.Draw(image).text((80, 100), "CTRL TEA 123", font=font, fill="black")
    data = io.BytesIO()
    image.save(data, format="PNG")
    pdf = fitz.open()
    page = pdf.new_page(width=600, height=150)
    page.insert_image(page.rect, stream=data.getvalue())
    raw = pdf.tobytes()
    source = sources.register(l["id"], "scan.pdf", raw)
    sources.extract(source["id"])
    row = store.one("SELECT * FROM pages WHERE source_id=?", (source["id"],))
    assert row["method"] == "tesseract" and "123" in row["raw"]
    sources.update_page(source["id"], 1, "نص مصحح محفوظ", False)
    sources.extract(source["id"])
    assert (
        store.one("SELECT corrected FROM pages WHERE source_id=?", (source["id"],))[
            "corrected"
        ]
        == "نص مصحح محفوظ"
    )


def test_export_revision_report_and_verbatim_draft_policy(client, lecture):
    c, l = lecture
    s = sources.register(l["id"], "question.txt", "النص الأصلي".encode())
    sources.extract(s["id"])
    doc = LectureDocument.model_validate(l["document"])
    doc.sections = [
        Section(
            title="سؤال",
            blocks=[
                Block(
                    kind="exercise",
                    problem="نص مختلف",
                    verbatim=True,
                    refs=[Reference(source_id=s["id"], quote="النص الأصلي")],
                )
            ],
        )
    ]
    store.save_document(l["id"], doc.model_dump(), 0)
    with pytest.raises(ValueError, match="نص سؤال حرفي"):
        export_lecture(l["id"])
    report = export_lecture(l["id"], draft=True)
    assert report["draft"] and report["revision"] == 1
    assert report["checks"]["issues"][0]["severity"] == "error"


def test_rtl_alignment_intervals_and_readable_math_size(client, tmp_path):
    from ctrltea.exporter import paragraph
    from docx import Document

    p = tmp_path / "direction.docx"
    doc = Document()
    paragraph(doc, "اختبار عربي [25,30[ ووحدة R = 10 Ω.")
    equation = doc.add_paragraph()
    from ctrltea.mathml import omml

    equation._p.append(omml(r"F(s)=\frac{1}{s^2}"))
    doc.save(p)
    with zipfile.ZipFile(p) as z:
        xml = etree.fromstring(z.read("word/document.xml"))
        assert xml.find(".//w:jc", NS).get("{" + NS["w"] + "}val") == "start"
        assert "\u2066[25,30[" in "".join(xml.itertext()) or any(
            "[25,30[" in t for t in xml.itertext()
        )
    with fitz.open(to_pdf(p)) as pdf:
        spans = [
            s
            for b in pdf[0].get_text("dict")["blocks"]
            for line in b.get("lines", [])
            for s in line["spans"]
        ]
        assert any(s["text"] == "F" and 13.5 <= s["size"] <= 14.5 for s in spans)
        words = pdf[0].get_text("words")
        assert (
            max(w[2] for w in words if any("\u0600" <= c <= "\u06ff" for c in w[4]))
            > 500
        )
        assert next(w for w in words if w[4] == "R")[0] < 400


def test_irrelevant_payload_fields_cannot_disappear_silently():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Block(kind="explanation", text="نص", latex="x=1")


def test_matrix_and_cases_preserve_delimiters_in_actual_pdf(client, tmp_path):
    from ctrltea.mathml import omml
    from docx import Document

    d = Document()
    d.add_paragraph()._p.append(omml(r"\begin{cases}0&t<0\\1&t\geq0\end{cases}"))
    d.add_paragraph()._p.append(omml(r"\begin{bmatrix}1&2\\3&4\end{bmatrix}"))
    p = tmp_path / "delimiters.docx"
    d.save(p)
    with fitz.open(to_pdf(p)) as pdf:
        value = pdf[0].get_text()
        assert "{" in value and "[" in value and "]" in value
        assert ")" not in value


def test_original_art_font_slots_and_unclipped_drawing_layout(client, tmp_path):
    from ctrltea.theme import AR_BODY, AR_HEADING, EN_BODY, EN_HEADING

    doc = LectureDocument(
        title="هوية المحاضرة",
        sections=[
            Section(
                title="قسم",
                blocks=[
                    Block(
                        kind="definition",
                        text=r"تعريف عربي مع English text والمعادلة \(\frac{a}{b}\).",
                    ),
                    Block(kind="equation", latex=r"\frac{1}{s^2}"),
                ],
            )
        ],
    )
    output = tmp_path / "identity.docx"
    build_docx(doc, output)
    with zipfile.ZipFile(output) as z:
        xml = etree.fromstring(z.read("word/document.xml"))
        assert (
            len(xml.findall(".//w:sectPr", NS)) == 2
        )  # only cover/body, never per scientific section
        for r in xml.findall(".//w:r", NS):
            if (
                r.find("w:t", NS) is None
                or not r.find("w:t", NS).text.strip()
                or r.getparent().tag == "{" + NS["m"] + "}r"
            ):
                continue
            f = r.find("w:rPr/w:rFonts", NS)
            assert f is not None
            assert f.get("{" + NS["w"] + "}ascii") in (EN_BODY, EN_HEADING, "Cairo")
            assert f.get("{" + NS["w"] + "}hAnsi") == f.get("{" + NS["w"] + "}ascii")
            assert f.get("{" + NS["w"] + "}cs") in (AR_BODY, AR_HEADING, "Cairo")
        for name in [
            n for n in z.namelist() if n.endswith(".xml") and n.startswith("word/")
        ]:
            assert b"IBM Plex" not in z.read(name)
        anchors = []
        for name in [
            n
            for n in z.namelist()
            if n.startswith(("word/header", "word/footer")) and n.endswith(".xml")
        ]:
            root = etree.fromstring(z.read(name))
            anchors.extend(
                root.findall(
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}anchor"
                )
            )
        assert len(anchors) == 4
        expected = [
            (51, 56.95, 99.2, 47.85),
            (555.59, 0, 39.69, 841.89),
            (294.8, 646.04, 209.75, 195.85),
            (0, 799.3, 595.28, 42.59),
        ]
        wp = {
            "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        }
        actual = []
        for a in anchors:
            ext = a.find("wp:extent", wp)
            actual.append(
                (
                    int(a.find("wp:positionH/wp:posOffset", wp).text) / 12700,
                    int(a.find("wp:positionV/wp:posOffset", wp).text) / 12700,
                    int(ext.get("cx")) / 12700,
                    int(ext.get("cy")) / 12700,
                )
            )
        for measurement in expected:
            assert any(
                all(abs(a - b) < 0.02 for a, b in zip(measurement, value))
                for value in actual
            )
        # Displayed fractions get automatic height instead of the body exact line box.
        equation = xml.find(".//m:oMath", NS).getparent()
        while equation.tag != "{" + NS["w"] + "}p":
            equation = equation.getparent()
        assert (
            equation.find("w:pPr/w:spacing", NS).get("{" + NS["w"] + "}lineRule")
            == "atLeast"
        )
    with fitz.open(to_pdf(output)) as pdf:
        footer = [
            s
            for b in pdf[-1].get_text("dict")["blocks"]
            for l in b.get("lines", [])
            for s in l["spans"]
            if s["bbox"][1] > 799
        ]
        assert any(
            s["text"] == "2" and s["size"] >= 27 and s["color"] == 0xFFFFFF
            for s in footer
        )


def test_long_cover_index_reserves_character_zone_and_preserves_all_links(
    client, tmp_path
):
    doc = LectureDocument(
        title="فهرس طويل لاختبار توزيع الصفحات",
        sections=[
            Section(
                id=f"s{i}",
                title=f"عنوان القسم {i} — قراءة النص وتنظيم الأمثلة",
                blocks=[Block(kind="explanation", text=f"نص الاختبار {i}.")],
            )
            for i in range(1, 41)
        ],
    )
    output = tmp_path / "outline.docx"
    build_docx(doc, output)
    with fitz.open(to_pdf(output)) as pdf:
        assert sum(len(p.get_links()) for p in pdf) == 40
        first = pdf[0]
        # All index links on cover stop before the measured character at y646.
        assert all(link["from"].y1 < 640 for link in first.get_links())
        assert "40" in "".join(p.get_text() for p in pdf)
        assert all(p.get_text().strip() for p in pdf)


def test_current_exports_keep_native_footers_on_every_body_page(client, tmp_path):
    # A long mixed-direction exercise followed by an end marker must survive reflow.
    doc = LectureDocument(
        title="مراجعة التدفق",
        sections=[
            Section(
                title="أمثلة",
                blocks=[
                    Block(
                        kind="explanation",
                        text="نص عربي لتجربة توزيع الفقرات ومسافات السطور. " * 22,
                    ),
                    Block(
                        kind="exercise",
                        title="تمرين",
                        problem=r"احسب \(x^2\).",
                        givens=r"\(x=2\).",
                        steps=[r"\(x^2=2^2\).", r"\(2^2=4\)."],
                        result=r"\(x^2=4\).",
                    ),
                ],
            )
        ],
    )
    output = tmp_path / "flow.docx"
    build_docx(doc, output)
    with fitz.open(to_pdf(output)) as pdf:
        for page in list(pdf)[1:]:
            assert any(
                abs(rect.y0 - 799.3) < 0.15
                for im in page.get_images()
                for rect in page.get_image_rects(im[0])
            )
            spans = [
                s
                for b in page.get_text("dict")["blocks"]
                for l in b.get("lines", [])
                for s in l["spans"]
            ]
            number = [
                s
                for s in spans
                if s["text"] == str(page.number + 1) and s["size"] >= 27
            ]
            assert number and number[0]["bbox"][3] < 842


def test_academic_semantic_flow_frames_and_book_font_slots(client, tmp_path):
    from ctrltea.theme import AR_BODY, EN_BODY

    blocks = [
        Block(kind="definition", title="تعريف أكاديمي", text="DEF_TOKEN نص التعريف."),
        Block(kind="rule", title="قانون", text=r"RULE_TOKEN قاعدة مع \(x_i\)."),
        Block(kind="explanation", text="PROSE_TOKEN فقرة عادية."),
        Block(kind="example", title="مثال", text="EXAMPLE_TOKEN نص المثال."),
        Block(kind="note", text="NOTE_TOKEN ملاحظة عادية."),
        Block(kind="warning", text="WARNING_TOKEN تنبيه للمراجعة."),
        Block(
            kind="exercise",
            title="مسألة",
            problem="QUESTION_TOKEN نص المسألة كما هو.",
            givens="GIVENS_TOKEN المعطيات كما هي.",
            steps=["STEP_TOKEN خطوة الحل."],
            result=r"RESULT_TOKEN \(\frac{a}{b}\).",
        ),
    ]
    doc = LectureDocument(
        title="تجربة أسلوب الكتب",
        sections=[Section(title="قسم أكاديمي", blocks=blocks)],
    )
    output = tmp_path / "book.docx"
    build_docx(doc, output)
    with zipfile.ZipFile(output) as z:
        xml = etree.fromstring(z.read("word/document.xml"))
        paragraphs = xml.findall(".//w:p", NS)

        def contains(token):
            return next(p for p in paragraphs if token in "".join(p.itertext()))

        assert contains("PROSE_TOKEN").getparent().tag != "{"+NS["w"]+"}tc"
        for token in ["DEF_TOKEN", "RULE_TOKEN", "EXAMPLE_TOKEN", "NOTE_TOKEN", "WARNING_TOKEN", "QUESTION_TOKEN"]:
            cell=contains(token).getparent()
            assert cell.tag=="{"+NS["w"]+"}tc"
            table=cell.getparent().getparent()
            border=table.find("w:tblPr/w:tblBorders",NS)
            assert border is not None
            assert {etree.QName(side).localname for side in border}=={"top","left","bottom","right"}
            assert all(side.get("{"+NS["w"]+"}val")=="single"for side in border)
            assert cell.find("w:tcPr/w:shd",NS)is not None
        assert contains("QUESTION_TOKEN") is not contains("GIVENS_TOKEN")
        assert contains("STEP_TOKEN").find("w:pPr/w:pBdr", NS) is None
        assert (
            contains("PROSE_TOKEN").find("w:pPr/w:jc", NS).get("{" + NS["w"] + "}val")
            == "start"
        )
        assert contains("STEP_TOKEN").find("w:pPr/w:numPr", NS) is not None
        heading = next(
            p
            for p in paragraphs
            if p.find("w:pPr/w:pStyle", NS) is not None
            and p.find("w:pPr/w:pStyle", NS).get("{" + NS["w"] + "}val") == "Heading1"
        )
        assert heading.find("w:pPr/w:tabs", NS) is None
        for p in [contains("DEF_TOKEN"), contains("QUESTION_TOKEN"), heading]:
            for r in p.findall(".//w:r", NS):
                if r.find("w:t", NS) is None:
                    continue
                fonts = r.find("w:rPr/w:rFonts", NS)
                assert fonts.get("{" + NS["w"] + "}ascii") == "Cairo"
                assert fonts.get("{" + NS["w"] + "}cs") == "Cairo"
        assert len(xml.findall(".//m:oMath", NS)) == 2
    with fitz.open(to_pdf(output)) as pdf:
        rendered = "".join(p.get_text() for p in pdf)
        for token in [
            "DEF_TOKEN",
            "RULE_TOKEN",
            "PROSE_TOKEN",
            "EXAMPLE_TOKEN",
            "NOTE_TOKEN",
            "WARNING_TOKEN",
            "QUESTION_TOKEN",
            "GIVENS_TOKEN",
            "STEP_TOKEN",
            "RESULT_TOKEN",
        ]:
            assert token in rendered


def test_long_book_frame_can_split_without_losing_last_text(client, tmp_path):
    doc = LectureDocument(
        title="تجربة صندوق ممتد",
        sections=[
            Section(
                title="التدفق",
                blocks=[
                    Block(
                        kind="rule",
                        title="قاعدة بشرح طويل",
                        text=("نص للمراجعة البصرية وتوزيع السطور. " * 180)
                        + " LASTTOKEN",
                    ),
                    Block(kind="explanation", text="FOLLOWING_TOKEN فقرة تالية."),
                ],
            )
        ],
    )
    output = tmp_path / "long-frame.docx"
    build_docx(doc, output)
    with fitz.open(to_pdf(output)) as pdf:
        assert len(pdf) > 3
        value = "".join(p.get_text() for p in pdf)
        assert "LASTTOKEN" in value and "FOLLOWING_TOKEN" in value
        assert all(p.get_text().strip() for p in pdf)
