"""Inspect a six-export theme matrix, including actual PDF colors and glyph bounds.

python scripts/verify_theme_exports.py --input examples/exports/themes
Complements, never substitutes for, visual review of the rendered pages.
"""

from pathlib import Path
import argparse
import hashlib
import json
import zipfile
import numpy as np

import fitz
from lxml import etree
from ctrltea import store
from ctrltea.mathml import NS
from ctrltea.models import LectureDocument
from ctrltea.theme import AR_BODY, AR_HEADING, EN_BODY, EN_HEADING, PALETTES
from render_examples import verify_content


def expanded(node):
    return (
        node.tag,
        tuple(sorted(node.attrib.items())),
        node.text or "",
        tuple(expanded(c) for c in node),
    )


def svg_geometry(data):
    root = etree.fromstring(data)
    return [
        (
            node.tag,
            tuple(
                (key, value)
                for key, value in sorted(node.attrib.items())
                if key
                in {
                    "d",
                    "points",
                    "x",
                    "y",
                    "x1",
                    "x2",
                    "y1",
                    "y2",
                    "width",
                    "height",
                    "viewBox",
                    "transform",
                    "r",
                    "cx",
                    "cy",
                }
            ),
            node.text if node.tag.endswith("}text") else None,
        )
        for node in root.iter()
        if isinstance(node.tag, str)
        and node.tag.endswith(
            ("}path", "}rect", "}line", "}circle", "}polyline", "}text", "}image")
        )
    ]


def verify(folder):
    summary = {}
    for name in ["control", "statistics"]:
        # Saved projects include the team's existing edits. The import examples
        # are earlier authoring fixtures and must not overwrite those edits.
        with zipfile.ZipFile(store.ROOT / f"examples/projects/{name}-project.zip") as archive:
            saved = json.loads(archive.read("project.json"))
        model = LectureDocument.model_validate_json(saved["lectures"][0]["doc"])
        reference = None
        reference_positions = None
        reference_cover = None
        for theme, (dark, medium, light) in PALETTES.items():
            file = folder / f"{name}-{theme}"
            checks = verify_content(model, file.with_suffix(".docx"))
            with zipfile.ZipFile(file.with_suffix(".docx")) as z:
                root = etree.fromstring(z.read("word/document.xml"))
                images = [z.read(n) for n in z.namelist() if n.startswith("word/media/")]
                for asset in ["cover-wordmark.png", "cover-strip.png", "cover-character.png"]:
                    assert (store.ROOT / "assets/original" / asset).read_bytes() in images
                texts = tuple(root.xpath(".//w:t/text()", namespaces=NS))
                math = tuple(expanded(n) for n in root.findall(".//m:oMath", NS))
                fonts_count = 0
                for run in root.findall(".//w:r", NS):
                    if not "".join(run.xpath("./w:t/text()", namespaces=NS)).strip():
                        continue
                    fonts = run.find("w:rPr/w:rFonts", NS)
                    assert fonts is not None, "Missing direct run fonts"
                    assert fonts.get("{" + NS["w"] + "}ascii") in [EN_BODY, EN_HEADING]
                    assert fonts.get("{" + NS["w"] + "}hAnsi") == fonts.get(
                        "{" + NS["w"] + "}ascii"
                    )
                    assert fonts.get("{" + NS["w"] + "}cs") in [AR_BODY, AR_HEADING]
                    fonts_count += 1
                colors = root.xpath(
                    './/w:p[w:pPr/w:pStyle[@w:val="Heading1"]]//w:color/@w:val', namespaces=NS
                )
                assert set(colors) == {dark[1:]}
                for pr in root.xpath(".//w:pPr[w:pBdr]", namespaces=NS):
                    assert all(
                        pr.find("w:pBdr/w:" + s, NS) is not None
                        for s in ["top", "left", "bottom", "right"]
                    )
                    assert pr.find("w:shd", NS).get("{" + NS["w"] + "}fill") == light[1:]
                for table in root.xpath(".//w:tbl[w:tblPr/w:bidiVisual]", namespaces=NS):
                    assert set(
                        table.xpath("./w:tr[1]/w:tc/w:tcPr/w:shd/@w:fill", namespaces=NS)
                    ) == {dark[1:]}
                    assert table.find(".//w:tblHeader", NS) is not None
                geometries = []
                source_images = []
                for n in sorted(n for n in z.namelist() if n.endswith(".svg")):
                    data = z.read(n)
                    geometries.append(svg_geometry(data))
                    if b"data:image/png" in data:
                        source_images.append(hashlib.sha256(data).hexdigest())
                    else:
                        assert dark.lower().encode() in data.lower()
            with fitz.open(file.with_suffix(".pdf")) as pdf:
                cover = np.frombuffer(pdf[0].get_pixmap(dpi=90).samples, dtype=np.uint8)
                positions = []
                embedded = set()
                for i, page in enumerate(pdf):
                    for font in page.get_fonts():
                        assert pdf.extract_font(font[0])[3], "Unembedded PDF font"
                        embedded.add(font[3])
                    for b in page.get_text("dict")["blocks"]:
                        for line in b.get("lines", []):
                            for span in line["spans"]:
                                if not span["text"].strip():
                                    continue
                                x0, y0, x1, y1 = span["bbox"]
                                assert (
                                    x0 >= -1
                                    and x1 <= page.rect.width + 1
                                    and y0 >= -1
                                    and y1 <= page.rect.height + 1
                                ), (file, i, span)
                                positions.append((i, span["text"], tuple(span["bbox"])))
                    if i:
                        pix = page.get_pixmap(dpi=72)
                        for x, color in [(20, dark), (560, medium)]:
                            assert (
                                max(
                                    abs(a - b)
                                    for a, b in zip(pix.pixel(x, 820)[:3], bytes.fromhex(color[1:]))
                                )
                                <= 2
                            )
                        footer = [
                            s
                            for b in page.get_text("dict")["blocks"]
                            for l in b.get("lines", [])
                            for s in l["spans"]
                            if s["bbox"][1] > 799
                        ]
                        assert any(
                            s["text"] == str(i + 1) and s["color"] == 0xFFFFFF and s["size"] >= 27
                            for s in footer
                        )
                assert any("NotoNaskhArabic" in f for f in embedded)
                assert any("SourceSerif4" in f for f in embedded)
                state = (texts, math, geometries, source_images, len(pdf))
                max_shift = 0
                changed_cover_fraction = 0
                if reference is None:
                    reference = state
                    reference_positions = positions
                    reference_cover = cover
                else:
                    for label, actual, expected in zip(
                        ["text", "math", "svg_geometry", "source_images", "pages"], state, reference
                    ):
                        assert actual == expected, f"Theme altered {label}: {file}"
                    assert len(positions) == len(reference_positions)
                    for actual, expected in zip(positions, reference_positions):
                        assert actual[:2] == expected[:2], f"Theme altered PDF text or page: {file}"
                        max_shift = max(
                            max_shift, max(abs(a - b) for a, b in zip(actual[2], expected[2]))
                        )
                    # LO font subsetting can round glyph advances by a few hundredths
                    # of a point. Check physical placement rather than byte identity.
                    assert max_shift <= 0.15, f"Theme moved text by {max_shift} pt: {file}"
                    changed_cover_fraction = float(
                        np.mean(
                            np.any(cover.reshape(-1, 3) != reference_cover.reshape(-1, 3), axis=1)
                        )
                    )
                    assert changed_cover_fraction < 0.002
                checks.update(
                    pages=len(pdf),
                    native_omml=len(math),
                    embedded_svg=len(geometries),
                    direct_font_runs=fonts_count,
                    original_cover_assets_identical=True,
                    cover_changed_pixel_fraction=changed_cover_fraction,
                    maximum_pdf_glyph_shift_pt=round(max_shift, 5),
                    text_and_math_identical_in_order=True,
                    svg_geometry_identical=True,
                    source_images_unchanged=True,
                    footer_theme_verified_on_every_body_page=True,
                    pdf_text_bounds_checked=True,
                    pdf_embedded_fonts=sorted(embedded),
                )
            summary[f"{name}-{theme}"] = checks
    (folder / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                key: {k: v for k, v in value.items() if k != "pdf_embedded_fonts"}
                for key, value in summary.items()
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=store.ROOT / "examples/exports/themes")
    verify(parser.parse_args().input.resolve())
