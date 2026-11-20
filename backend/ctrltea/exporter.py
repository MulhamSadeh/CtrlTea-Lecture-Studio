from __future__ import annotations

import copy
from contextvars import ContextVar
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from lxml import etree
from docx import Document
from docx.enum.text import (
    WD_LINE_SPACING,
    WD_ALIGN_PARAGRAPH,
    WD_TAB_ALIGNMENT,
    WD_TAB_LEADER,
)
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.shared import Mm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.part import Part
from docx.opc.packuri import PackURI
from .runtime import find_binary, tool_environment
from . import store
from .models import LectureDocument
from .text_layout import ARABIC, direction_runs, prose_parts
from .mathml import omml, segments, formulas, NS
from .figures import render
from .theme import (
    AR_BODY,
    AR_HEADING,
    EN_BODY,
    EN_HEADING,
    MATH,
    MATH_SIZE,
    INK,
    PALETTES,
    FOOTER_POLICY,
    DEFAULT_THEME,
    validate_theme,
    footer_art,
    ACADEMIC_TYPOGRAPHY,
    CONTENT_HEADING,
    academic_box_style,
)
from .sources import source_warnings

_MATH_MODE = ContextVar("ctrltea_math_mode", default="native")
_MATH_WIDTH = ContextVar("ctrltea_math_width", default=480)


def append_math(p, latex):
    if _MATH_MODE.get() == "portable":
        from .portable_math import insert
        insert(p, latex, _MATH_WIDTH.get())
    else:
        p._p.append(copy.deepcopy(omml(latex)))


LABELS = {
    "definition": "تعريف",
    "rule": "قاعدة",
    "explanation": "",
    "list": "",
    "example": "مثال",
    "exercise": "مسألة محلولة",
    "equation": "",
    "figure": "",
    "table": "",
    "note": "ملاحظة",
    "warning": "تنبيه",
}


def element(tag, **attrs):
    el = OxmlElement(tag)
    for key, value in attrs.items():
        el.set(qn("w:" + key), str(value))
    return el


def rtl_paragraph(p, enabled=True):
    pr = p._p.get_or_add_pPr()
    bidi = pr.find(qn("w:bidi"))
    if bidi is None:
        bidi = element("w:bidi")
        pr.append(bidi)
    bidi.set(qn("w:val"), "1" if enabled else "0")
    return p


# Keep Arabic words, spaces and punctuation in a single shaping context. Only
# actual Latin phrases are isolated; splitting on every space breaks contextual
# shaping and makes bidi punctuation depend on unrelated neighbouring runs.


def text(p, value, bold=False, color=None, size=None, *, book=False, font=None):
    styles = p.part.package.main_document_part.document.styles
    body = styles["Normal"]._element.get_or_add_rPr()
    body_fonts = body.rFonts
    en = (
        body_fonts.get(qn("w:ascii"), EN_BODY)
        if book
        else (EN_HEADING if bold else EN_BODY)
    )
    ar = (
        body_fonts.get(qn("w:cs"), AR_BODY)
        if book
        else (AR_HEADING if bold else AR_BODY)
    )
    if font is not None:
        en = ar = font
    for is_math, part in segments(value):
        if is_math:
            # Isolate the native equation from the surrounding Arabic bidi run.
            # Do not put LRI/PDI characters inside the mathematical expression.
            if _MATH_MODE.get() == "portable":
                append_math(p, part)
            else:
                direction = element("w:dir", val="ltr")
                direction.append(copy.deepcopy(omml(part)))
                p._p.append(direction)
            continue
        for ltr, chunk in direction_runs(re.sub(r"[\u2066-\u2069]", "", part)):
            if not chunk:
                continue
            run = p.add_run(chunk)
            run.bold = bold
            pr = run._r.get_or_add_rPr()
            pr.insert(0, element("w:rFonts", ascii=en, hAnsi=en, cs=ar))
            if bold:
                pr.append(element("w:bCs", val="1"))
            if ltr or ARABIC.search(chunk):
                pr.append(element("w:rtl", val="0" if ltr else "1"))
            pr.append(element("w:lang", val="en-US", bidi="ar-SA"))
            if color:
                run.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
            if size:
                run.font.size = Pt(size)
                pr.append(element("w:szCs", val=round(size * 2)))
            if ltr:
                p._p.remove(run._r)
                direction = element("w:dir", val="ltr")
                direction.append(run._r)
                p._p.append(direction)
    if any(is_math for is_math, _ in segments(value)):
        p.paragraph_format.line_spacing = Pt(28)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
    return p


def paragraph(
    parent, value="", *, bold=False, color=None, size=None, keep=False, book=False
):
    p = rtl_paragraph(parent.add_paragraph())
    p._p.get_or_add_pPr().append(element("w:jc", val="start"))
    p.paragraph_format.keep_with_next = keep
    text(p, value, bold, color, size, book=book)
    return p


def border_box(p, dark, light, *, kind="rule"):
    pr = p._p.get_or_add_pPr()
    borders = element("w:pBdr")
    for side in ("top", "left", "bottom", "right"):
        borders.append(
            element("w:" + side, val="single", sz=4, space=7, color=dark[1:])
        )
    pr.append(borders)
    pr.append(element("w:shd", fill=light[1:], val="clear"))
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(9)
    p.paragraph_format.left_indent = p.paragraph_format.right_indent = Mm(3)
    p.paragraph_format.widow_control = True


def academic_paragraph(parent, value="", *, keep=False, indent=False):
    p = paragraph(parent, value, keep=keep, book=True)
    # Physical right alignment avoids Writer's Arabic justification / kashida.
    # Latin-only paragraphs use their natural direction; equations have their own.
    plain = "".join(fragment for math, fragment in segments(value) if not math)
    arabic = bool(ARABIC.search(plain)) or not re.search(r"[A-Za-z]", plain)
    rtl_paragraph(p, arabic)
    p._p.get_or_add_pPr().find(qn("w:jc")).set(qn("w:val"), "start")
    p.paragraph_format.widow_control = True
    return p


def heading_title(value):
    """Generated punctuation belongs to the view, never the saved science."""
    return value.rstrip().rstrip(":：").rstrip() + ":"


def paragraph_rule(p, color, weight=4, space=3, *, between=False):
    pr = p._p.get_or_add_pPr()
    old = pr.find(qn("w:pBdr"))
    if old is not None:
        pr.remove(old)
    borders = element("w:pBdr")
    for side in (("bottom", "between") if between else ("bottom",)):
        borders.append(element("w:" + side, val="single", sz=weight,
                               space=space, color=color.lstrip("#")))
    pr.append(borders)


def academic_title(p, value, dark, size=13):
    text(p, heading_title(value), bold=True, color=dark, size=size)
    # Formula titles may themselves contain OMML: never restyle math runs.
    for run in p._p.xpath(".//w:r[not(ancestor::m:oMath)]"):
        fonts = run.find("w:rPr/w:rFonts", NS)
        if fonts is not None:
            for slot in ("ascii", "hAnsi", "cs"):
                fonts.set(qn("w:" + slot), CONTENT_HEADING)
    paragraph_rule(p, dark, weight=3)
    return p


def separate_body_paragraphs(doc):
    """Black rules between adjacent prose; preserve cover and native objects."""
    def prose(node):
        if node is None or node.tag != qn("w:p"):
            return False
        pr = node.find(qn("w:pPr"))
        if pr is not None:
            if any(pr.find(qn("w:" + tag)) is not None
                   for tag in ("pBdr", "numPr", "sectPr")):
                return False
            jc = pr.find(qn("w:jc"))
            if jc is not None and jc.get(qn("w:val")) == "center":
                return False
        if node.findall(".//" + qn("w:drawing")):
            return False
        return any((t.text or "").strip() for t in node.findall(".//w:t", NS))

    active = False
    from docx.text.paragraph import Paragraph
    for child in doc.element.body:
        if child.tag == qn("w:p") and child.find("w:pPr/w:sectPr", NS) is not None:
            active = True
            continue
        if not active:
            continue
        candidates = [child] if child.tag == qn("w:p") else []
        # Narrative frames, not data grids (which already have row borders).
        if child.tag == qn("w:tbl"):
            rows = child.findall("w:tr", NS)
            if len(rows) == 1 and len(rows[0].findall("w:tc", NS)) == 1:
                candidates = rows[0].findall("w:tc/w:p", NS)
        pairs = [p for p in candidates if prose(p) and prose(p.getnext())]
        for node in pairs:
            paragraph_rule(Paragraph(node, doc), "000000", weight=3, space=4, between=True)


def academic_label(block, label, number=None):
    # Type words are generated by the renderer. Remove repeated *presentation*
    # prefixes, including a legacy "example:" on an exercise, without touching
    # any word in the saved title or body.
    if block.kind in {"definition", "rule"}:
        core = label.strip()
        # Suppress type prefixes only in the view; keep meaningful titles such
        # as «قانون أوم» and never rewrite scientific source text.
        prefix = re.compile(r"^(?:التعريف|تعريف|القاعدة|قاعدة|قانون|نظرية)\s*[:：—–-]\s*")
        while prefix.match(core):
            core = prefix.sub("", core, count=1)
        return "" if core in {"التعريف", "تعريف", "القاعدة", "قاعدة", "قانون", "نظرية"} else core
    kind = LABELS[block.kind]
    if block.kind == "exercise" and block.origin == "instructor_example":
        kind = "مثال محلول"
    if block.origin in ("book_question", "additional_exercise") or not kind:
        return label
    core = label.strip()
    types = sorted(
        {x for x in LABELS.values() if x}
        | {"تمرين محلول", "مثال محلول", "قانون", "نظرية"},
        key=len,
        reverse=True,
    )
    prefix = re.compile(r"^(?:" + "|".join(map(re.escape, types)) + r")\s*[:：—–-]\s*")
    while prefix.match(core):
        core = prefix.sub("", core, count=1)
    if not core or core in types:
        return f"{kind} {number}" if number is not None else kind
    if number is not None:
        # Numbering is a view concern; saved titles and scientific text stay intact.
        core = re.sub(r"^(?:مثال(?: محلول)?|مسألة محلولة|تمرين محلول)\s*(?:[0-9٠-٩]+)?\s*[:：—–-]?\s*", "", core)
        return f"{kind} {number}" + (f": {core}" if core else "")
    if re.match(r"^" + re.escape(kind) + r"(?:\s|[:：])", core):
        return core
    return f"{kind}: {core}"


def box_spacer(doc, keep=False):
    # Distinct adjacent frames must not merge into one paragraph border in Word.
    p = doc.add_paragraph()
    p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = Pt(2)
    p.paragraph_format.keep_with_next = keep


def academic_heading(doc, title, dark, width):
    p = paragraph(doc, keep=True)
    academic_title(p, title, dark, size=17)
    p.style = doc.styles["Heading 1"]
    p.paragraph_format.line_spacing = Pt(30)
    p.paragraph_format.space_before = Pt(15)
    p.paragraph_format.space_after = Pt(9)
    return p


def numbering(doc, ordered=False, start=1):
    """A real editable Word list, with a new numbering instance per group."""
    root = doc.part.numbering_part.element
    abstract_id = (
        max(
            [
                int(n.get(qn("w:abstractNumId")))
                for n in root.findall(qn("w:abstractNum"))
            ]
            + [0]
        )
        + 1
    )
    num_id = (
        max([int(n.get(qn("w:numId"))) for n in root.findall(qn("w:num"))] + [0]) + 1
    )
    abstract = element("w:abstractNum", abstractNumId=abstract_id)
    abstract.append(element("w:multiLevelType", val="singleLevel"))
    level = element("w:lvl", ilvl=0)
    level.append(element("w:start", val=start))
    level.append(element("w:numFmt", val="decimal" if ordered else "bullet"))
    level.append(element("w:suff", val="tab"))
    level.append(element("w:lvlText", val="%1." if ordered else "•"))
    level.append(element("w:lvlJc", val="right"))
    pp = element("w:pPr")
    pp.append(element("w:bidi", val="1"))
    pp.append(element("w:ind", right=400, hanging=260))
    level.append(pp)
    rp = element("w:rPr")
    body_fonts = doc.styles["Normal"]._element.get_or_add_rPr().rFonts
    rp.append(copy.deepcopy(body_fonts))
    rp.append(element("w:rtl", val="0"))
    level.append(rp)
    abstract.append(level)
    root.append(abstract)
    num = element("w:num", numId=num_id)
    num.append(element("w:abstractNumId", val=abstract_id))
    root.append(num)
    return num_id


def list_paragraph(doc, value, num_id, *, keep=False):
    p = academic_paragraph(doc, value, keep=keep)
    rtl_paragraph(p, True)
    p._p.get_or_add_pPr().find(qn("w:jc")).set(qn("w:val"), "start")
    num = element("w:numPr")
    num.append(element("w:ilvl", val=0))
    num.append(element("w:numId", val=num_id))
    p._p.get_or_add_pPr().append(num)
    p.paragraph_format.right_indent = Mm(7)
    p.paragraph_format.first_line_indent = Mm(-4.6)
    p.paragraph_format.space_after = Pt(4)
    return p


def flow_text(doc, value, *, keep=False):
    result = []
    for kind, content in prose_parts(value):
        if kind == "prose":
            p = academic_paragraph(doc, content)
            if not "".join(
                fragment for math, fragment in segments(content) if not math
            ).strip(" .،;:") and any(math for math, _ in segments(content)):
                rtl_paragraph(p, False)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if result:
                    result[-1].paragraph_format.keep_with_next = True
            result.append(p)
        else:
            if result:
                result[-1].paragraph_format.keep_with_next = True
            start, items = content
            num_id = numbering(doc, kind == "ordered", start)
            for item in items:
                result.append(list_paragraph(doc, item, num_id))
    if result:
        result[-1].paragraph_format.keep_with_next = keep
    return result


def block_heading(doc, value, dark, *, size=13):
    p = academic_paragraph(doc)
    academic_title(p, value, dark, size=size)
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.keep_together = True
    return p


def display_equation(parent, block, dark):
    if block.title:
        p = academic_paragraph(parent)
        academic_title(p, block.title, dark, size=12.5)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(4)
    p = rtl_paragraph(parent.add_paragraph(), False)
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_together = True
    p.paragraph_format.keep_with_next = bool(block.text)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    append_math(p, block.latex)
    if block.text:
        flow_text(parent, block.text)


def visible_body(block):
    """Suppress only an exact duplicated heading prefix in the view, never in JSON."""
    value = block.text
    if block.verbatim or not block.title:
        return value
    for title in (block.title, academic_label(block, block.title)):
        matched = re.match(r"^\s*" + re.escape(title) + r"\s*[:：]\s+", value)
        if matched and value[matched.end():].strip():
            return value[matched.end():]
    return value


def framed_content(doc, lead, value, dark, light, keep=False, *, kind="definition", equation=None, givens=""):
    # A native single-cell table gives stable full borders + real inner padding.
    # Its row is deliberately splittable: long content can flow across pages.
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    section = doc.sections[-1]
    table.columns[0].width = section.page_width-section.left_margin-section.right_margin
    borders = element("w:tblBorders")
    box = academic_box_style(kind, dark, light)
    for side in ("top", "left", "bottom", "right"):
        borders.append(element("w:"+side, val="single", sz=box["weight"], color=box["border"][1:]))
    table._tbl.tblPr.append(borders)
    margins = element("w:tblCellMar")
    for side in ("top", "bottom", "left", "right"):
        margins.append(element("w:"+side, w=box["vertical_padding"] if side in {"top", "bottom"} else box["horizontal_padding"], type="dxa"))
    table._tbl.tblPr.append(margins)
    cell = table.cell(0,0)
    cell._tc.get_or_add_tcPr().append(element("w:shd", fill=box["fill"][1:], val="clear"))
    initial = cell.paragraphs[0]
    compact = kind in {"note", "result"} and "\n" not in value
    if len(value) + len(givens) <= 650 and value.count("\n") < 8:
        # Writer can split a table row despite paragraph keepLines. Constrain
        # just these short rows; all long narrative frames remain splittable.
        table.rows[0]._tr.get_or_add_trPr().append(element("w:cantSplit"))
    if compact:
        p = academic_paragraph(cell)
        # Short notes/results are a single reading unit. Long material remains
        # splittable instead of forcing an oversized box onto a blank page.
        p.paragraph_format.keep_together = len(value) <= 450
        if lead:
            text(p, heading_title(lead) + " ", bold=True, color=dark, book=True)
        text(p, value, book=True)
        paragraphs = [p]
    elif lead:
        p = academic_paragraph(cell)
        academic_title(p, lead, dark, size=12.5 if kind=="note" else 13)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.line_spacing = Pt(24)
    if not compact:
        paragraphs = flow_text(cell, value, keep=bool(givens or equation))
    if givens:
        p = academic_paragraph(cell)
        text(p, "المعطيات: ", bold=True, color=dark, book=True)
        text(p, givens, book=True)
        p.paragraph_format.keep_with_next = bool(equation)
    if equation:
        display_equation(cell, equation, dark)
    initial._p.getparent().remove(initial._p)
    if cell.paragraphs:
        cell.paragraphs[-1].paragraph_format.space_after = Pt(1)
        cell.paragraphs[-1].paragraph_format.keep_with_next = keep
    # A modest gap is outside the frame, not an oversized empty area inside it.
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = Pt(2)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(7)
    p.paragraph_format.keep_with_next = keep
    return cell


def section_anchor(identifier):
    import hashlib
    return "sec_" + hashlib.sha1(identifier.encode()).hexdigest()[:28]


def bookmark(p, name, index):
    a = element("w:bookmarkStart", id=index, name=name)
    b = element("w:bookmarkEnd", id=index)
    p._p.insert(1 if p._p.find(qn("w:pPr")) is not None else 0, a)
    p._p.append(b)


def hyperlink(p, label, anchor, color, size=12):
    link = element("w:hyperlink", anchor=anchor, history="1")
    holder = p._parent.add_paragraph()
    text(holder, label, color=color, size=size, font="Cairo")
    for run in list(holder._p):
        if run.tag != qn("w:pPr"):
            link.append(run)
    holder._p.getparent().remove(holder._p)
    p._p.append(link)


def image_with_svg(p, svg, png, width_mm):
    shape = p.add_run().add_picture(str(png), width=Mm(width_mm))
    # SVG retained as the vector original, with a PNG fallback for older readers.
    part = p.part
    index = 1
    existing = {str(x.partname) for x in part.package.parts}
    while f"/word/media/vector{index}.svg" in existing:
        index += 1
    svgpart = Part(
        PackURI(f"/word/media/vector{index}.svg"),
        "image/svg+xml",
        svg.read_bytes(),
        part.package,
    )
    rid = part.relate_to(svgpart, RT.IMAGE)
    blip = shape._inline.xpath(".//a:blip")[0]
    extlist = OxmlElement("a:extLst")
    ext = OxmlElement("a:ext")
    ext.set("uri", "{96DAC541-7B7A-43D3-8B79-37D633B846F1}")
    vector = etree.Element(
        "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip",
        nsmap={"asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main"},
    )
    vector.set(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed",
        rid,
    )
    ext.append(vector)
    extlist.append(ext)
    blip.append(extlist)
    return shape


def floating_art(p, path, x, y, width, height):
    """Page-relative DrawingML; explicit dimensions in points, never page-count based."""
    shape = p.add_run().add_picture(str(path), width=Pt(width), height=Pt(height))
    inline = shape._inline
    ns = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"

    def wp(tag, **attrs):
        el = etree.Element("{" + ns + "}" + tag)
        for key, value in attrs.items():
            el.set(key, str(value))
        return el

    anchor = wp(
        "anchor",
        distT=0,
        distB=0,
        distL=0,
        distR=0,
        simplePos=0,
        relativeHeight=0,
        behindDoc=1,
        locked=0,
        layoutInCell=1,
        allowOverlap=1,
    )
    anchor.append(wp("simplePos", x=0, y=0))
    for axis, offset in [("H", x), ("V", y)]:
        pos = wp("position" + axis, relativeFrom="page")
        off = wp("posOffset")
        off.text = str(round(offset * 12700))
        pos.append(off)
        anchor.append(pos)
    for tag in ["extent", "effectExtent"]:
        child = inline.find("{" + ns + "}" + tag)
        if child is not None:
            anchor.append(copy.deepcopy(child))
    anchor.append(wp("wrapNone"))
    for tag in ["docPr", "cNvGraphicFramePr"]:
        child = inline.find("{" + ns + "}" + tag)
        if child is not None:
            anchor.append(copy.deepcopy(child))
    anchor.append(copy.deepcopy(inline[-1]))
    inline.getparent().replace(inline, anchor)


def page_number(p, color, size=28):
    # Complex field retains its editable cached-result formatting in Writer and Word.
    for kind in ("begin", "instruction", "separate", "result", "end"):
        run = p.add_run()
        run.font.name = EN_HEADING
        pr = run._r.get_or_add_rPr()
        pr.rFonts.set(qn("w:cs"), AR_HEADING)
        run.font.size = Pt(size)
        pr.append(element("w:szCs", val=size * 2))
        run.bold = True
        pr.append(element("w:bCs", val="1"))
        run.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
        if kind == "instruction":
            instruction = element("w:instrText")
            instruction.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            instruction.text = " PAGE "
            run._r.append(instruction)
        elif kind == "result":
            run.text = "1"
        else:
            run._r.append(element("w:fldChar", fldCharType=kind))


def setup(doc, content, theme, typography=ACADEMIC_TYPOGRAPHY):
    for border in doc.styles.element.xpath(".//w:pBdr"):
        border.getparent().remove(border)
    # Reset all legacy theme/direct style font slots, not only Normal.
    for style in doc.styles:
        rp = style._element.get_or_add_rPr()
        for old in list(rp):
            if old.tag == qn("w:rFonts"):
                rp.remove(old)
        heading = style.name.startswith("Heading") or style.name == "Title"
        content_heading = heading and style.name != "Title"
        latin_font = CONTENT_HEADING if content_heading else EN_HEADING if heading else EN_BODY
        arabic_font = CONTENT_HEADING if content_heading else AR_HEADING if heading else AR_BODY
        rp.insert(
            0,
            element(
                "w:rFonts",
                ascii=latin_font,
                hAnsi=latin_font,
                cs=arabic_font,
            ),
        )
    defaults = doc.styles.element.find(qn("w:docDefaults"))
    for old in defaults.findall(".//" + qn("w:rFonts")):
        old.attrib.clear()
        for slot, font in [("ascii", EN_BODY), ("hAnsi", EN_BODY), ("cs", AR_BODY)]:
            old.set(qn("w:" + slot), font)
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = Mm(content.settings.margin_mm)
    section.bottom_margin = Mm(
        73
    )  # cover artwork exclusion zone; body gets its own section
    section.left_margin = section.right_margin = Mm(content.settings.margin_mm)
    section.header_distance = Mm(0)
    section.footer_distance = Mm(1)
    section.different_first_page_header_footer = True
    normal = doc.styles["Normal"]
    scale = content.settings.font_size / 14.5
    normal.font.size = Pt(typography.latin_size * scale)
    normal.font.color.rgb = RGBColor.from_string(INK[1:])
    fonts = normal._element.get_or_add_rPr().rFonts
    for slot, font in [
        ("ascii", typography.latin),
        ("hAnsi", typography.latin),
        ("cs", typography.arabic),
    ]:
        fonts.set(qn("w:" + slot), font)
    normal._element.get_or_add_rPr().append(
        element("w:szCs", val=round(typography.arabic_size * scale * 2))
    )
    normal.paragraph_format.line_spacing = Pt(
        typography.leading * scale * content.settings.line_spacing / 1.45
    )
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.widow_control = True
    for name, size in [("Title", 22), ("Heading 1", 17), ("Heading 2", 14)]:
        style = doc.styles[name]
        style.font.size = Pt(size)
        if name != "Title":
            fonts = style._element.get_or_add_rPr().rFonts
            for slot, font in (("ascii", CONTENT_HEADING), ("hAnsi", CONTENT_HEADING), ("cs", CONTENT_HEADING)):
                fonts.set(qn("w:" + slot), font)
        style._element.get_or_add_rPr().append(element("w:szCs", val=size * 2))
        style.font.bold = True
        style._element.get_or_add_rPr().append(element("w:bCs", val="1"))
        style.font.color.rgb = RGBColor.from_string("4B3126")
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.line_spacing = Pt(size * 1.7)
        style.paragraph_format.space_before = Pt(14 if name != "Title" else 8)
        style.paragraph_format.space_after = Pt(5)
    # Use the actual original artwork at its measured A4 coordinates.
    art = store.ROOT / "assets/original"
    cover = section.first_page_header.paragraphs[0]
    floating_art(cover, art / "cover-wordmark.png", 51, 56.95, 99.2, 47.85)
    floating_art(cover, art / "cover-strip.png", 555.59, 0, 39.69, 841.89)
    floating_art(cover, art / "cover-character.png", 294.8, 646.04, 209.75, 195.85)
    footer = section.footer.paragraphs[0]
    floating_art(footer, footer_art(theme), 0, 799.3, 595.28, 42.59)
    rtl_paragraph(footer, False)
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.left_indent = -section.left_margin
    footer.paragraph_format.right_indent = Mm(105) - section.right_margin
    footer.paragraph_format.space_before = footer.paragraph_format.space_after = Pt(0)
    footer.paragraph_format.line_spacing = Pt(42.59)
    page_number(footer, "#FFFFFF")
    first = section.first_page_footer.paragraphs[0]
    rtl_paragraph(first, False)
    first.paragraph_format.space_after = Pt(23)
    first.paragraph_format.line_spacing = Pt(42.59)
    page_number(first, "#4B3126")
    # Native equations keep their own font and LTR semantics.
    mathpr = doc.settings.element.find(
        "{http://schemas.openxmlformats.org/officeDocument/2006/math}mathPr"
    )
    if mathpr is not None:
        font = mathpr.find(
            "{http://schemas.openxmlformats.org/officeDocument/2006/math}mathFont"
        )
        if font is not None:
            font.set(
                "{http://schemas.openxmlformats.org/officeDocument/2006/math}val", MATH
            )
    doc.core_properties.title = content.title
    doc.core_properties.author = "Ctrl+Tea"
    doc.core_properties.subject = content.course


def cover_contents(doc, content, draft):
    """Cover index flows naturally; overflow continues before lecture content.

    Artwork has a measured exclusion zone below 220 mm; a page-specific bottom
    margin via a first section prevents long outlines from colliding with it.
    """
    p = paragraph(doc, content.course, bold=True, color="#3D2D25", size=18)
    p.paragraph_format.right_indent = Mm(15)
    p.paragraph_format.left_indent = Mm(15)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = Pt(35)
    if content.doctor:
        p = paragraph(doc, content.doctor, size=12)
        # The approved cover keeps its former leading and spacing independently
        # of the new body typography.
        p.paragraph_format.line_spacing = Pt(
            (content.settings.font_size + 1)
            * 1.65
            * content.settings.line_spacing
            / 1.45
        )
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.right_indent = Mm(15)
        p.paragraph_format.left_indent = Mm(15)
    if draft:
        p = paragraph(doc, "مسودة للمراجعة", color="#8B3F25", size=12)
        p.paragraph_format.line_spacing = Pt(
            (content.settings.font_size + 1)
            * 1.65
            * content.settings.line_spacing
            / 1.45
        )
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.right_indent = Mm(15)
        p.paragraph_format.left_indent = Mm(15)
    p = paragraph(doc, content.title, bold=True, color="#4B3126", size=22)
    p.style = doc.styles["Title"]
    p.paragraph_format.space_before = Pt(
        95.25 if not content.doctor and not draft else 63.25
    )
    p.paragraph_format.right_indent = Mm(15)
    p.paragraph_format.left_indent = Mm(15)
    p.paragraph_format.space_after = Pt(7)
    p = paragraph(doc, f"المحاضرة {content.number}", color="#6E5543", size=12)
    p.paragraph_format.right_indent = Mm(15)
    p.paragraph_format.left_indent = Mm(15)
    p.paragraph_format.line_spacing = Pt(20)
    p.paragraph_format.space_after = Pt(6)
    # A normal editable RTL Word grid, with native internal links.
    table = doc.add_table(rows=0, cols=2)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table._tbl.tblPr.append(element("w:bidiVisual", val="1"))
    for column, width in zip(table.columns, [14, 144]):
        column.width = Mm(width)
    table._tbl.tblPr.append(element("w:tblW", w=round(158 * 56.6929), type="dxa"))
    border = element("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border.append(element("w:" + side, val="single", sz=4, color="796052"))
    table._tbl.tblPr.append(border)
    margins = element("w:tblCellMar")
    for side, width in [("top", 0), ("bottom", 0), ("left", 80), ("right", 80)]:
        margins.append(element("w:" + side, w=width, type="dxa"))
    table._tbl.tblPr.append(margins)
    for i, section in enumerate(content.sections):
        row = table.add_row()
        row._tr.get_or_add_trPr().append(element("w:cantSplit"))
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = Pt(23.25)
        p = row.cells[0].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        text(p, f"{i+1:02}", bold=True, color="#4B3126", size=10, font="Cairo")
        p = rtl_paragraph(row.cells[1].paragraphs[0])
        p._p.get_or_add_pPr().append(element("w:jc", val="start"))
        hyperlink(p, section.title, section_anchor(section.id), "#4B3126", size=12)
    body = doc.add_section(WD_SECTION_START.NEW_PAGE)
    body.bottom_margin = Mm(max(23, content.settings.margin_mm))
    body.different_first_page_header_footer = False


def build_docx(content, out, draft=False, theme=DEFAULT_THEME, *, typography=ACADEMIC_TYPOGRAPHY):
    token = _MATH_MODE.set(content.settings.math_mode)
    width = _MATH_WIDTH.set((210 - 2 * content.settings.margin_mm - 10) * 72 / 25.4)
    try:
        if content.settings.math_mode == "portable":
            from .portable_math import prepare
            prepare(list(formulas(content)))
        return _build_docx(content, out, draft, theme, typography=typography)
    finally:
        _MATH_MODE.reset(token)
        _MATH_WIDTH.reset(width)


def _build_docx(
    content: LectureDocument,
    out: Path,
    draft=False,
    theme=DEFAULT_THEME,
    *,
    typography=ACADEMIC_TYPOGRAPHY,
):
    validate_theme(theme)
    doc = Document()
    setup(doc, content, theme, typography)
    cover_contents(doc, content, draft)
    math_count = 0
    figure_count = 0
    example_number = 0
    for si, section in enumerate(content.sections):
        dark, medium, light = PALETTES[theme]
        p = academic_heading(
            doc, section.title, dark, 210 - 2 * content.settings.margin_mm
        )
        bookmark(p, section_anchor(section.id), si + 1)
        option = content.settings.layout.get(section.id)
        if option and option.page_before:
            p.paragraph_format.page_break_before = True
        consumed = set()
        for bi, b in enumerate(section.blocks):
            if bi in consumed:
                continue
            start_node = len(doc.element.body) - 1
            following = section.blocks[bi + 1] if bi + 1 < len(section.blocks) else None
            label = b.title or LABELS[b.kind]
            if b.origin == "additional_exercise":
                label = "تمرين توضيحي إضافي" + (" — " + b.title if b.title else "")
            elif b.origin == "book_question":
                label = "سؤال من الكتاب" + (" — " + b.title if b.title else "")
            if b.kind in {"definition", "rule", "example", "note", "warning"}:
                if b.kind == "example":
                    example_number += 1
                lead = academic_label(b, label, example_number if b.kind=="example" else None)
                attached = following if (b.kind in {"rule", "definition"} and following and following.kind=="equation" and not content.settings.layout.get(following.id)) else None
                framed_content(doc, lead, visible_body(b), dark, light, kind=b.kind, equation=attached)
                if attached:
                    consumed.add(bi+1)
            elif b.kind == "equation":
                display_equation(doc, b, dark)
            elif b.kind == "table":
                if b.text:
                    academic_paragraph(doc, b.text)
                if label:
                    block_heading(doc, label, dark)
                table = doc.add_table(rows=1, cols=len(b.headers))
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                # Logical first column is the rightmost one; no manual list reversal.
                table._tbl.tblPr.append(element("w:bidiVisual", val="1"))
                borders = element("w:tblBorders")
                for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                    borders.append(
                        element(
                            "w:" + side,
                            val="nil" if side == "insideV" else "single",
                            sz=3 if side == "insideH" else 4,
                            color=dark[1:],
                        )
                    )
                table._tbl.tblPr.append(borders)
                margins = element("w:tblCellMar")
                for side in ("top", "bottom", "left", "right"):
                    margins.append(element("w:" + side, w="100", type="dxa"))
                table._tbl.tblPr.append(margins)
                table.rows[0]._tr.get_or_add_trPr().append(
                    element("w:tblHeader", val="true")
                )
                data = [b.headers, *b.rows]
                for ri, row in enumerate(data):
                    cells = table.rows[0].cells if ri == 0 else table.add_row().cells
                    for cell, value in zip(cells, row):
                        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                        p = rtl_paragraph(cell.paragraphs[0])
                        p.paragraph_format.space_after = Pt(3)
                        p.paragraph_format.space_before = Pt(3)
                        p.paragraph_format.line_spacing = Pt(23)
                        math_header = ri == 0 and any(
                            is_math for is_math, _ in segments(value)
                        )
                        if math_header:
                            # Writer imports OMML in black even when its run is white.
                            # A light inset preserves native math without changing symbols,
                            # while the surrounding header cell retains the dark theme fill.
                            p._p.get_or_add_pPr().append(
                                element("w:shd", fill=light[1:], val="clear")
                            )
                        text(
                            p,
                            value,
                            bold=ri == 0,
                            color=(
                                dark if math_header else "#FFFFFF" if ri == 0 else None
                            ),
                            size=13.5,
                            book=True,
                        )
                        cell._tc.get_or_add_tcPr().append(
                            element(
                                "w:shd",
                                fill=(
                                    dark[1:]
                                    if ri == 0
                                    else light[1:] if ri % 2 else "FFFFFF"
                                ),
                            )
                        )
                    # A normal row remains intact. A row taller than a page can still flow in Writer.
                    table.rows[ri]._tr.get_or_add_trPr().append(element("w:cantSplit"))
                from .pagination import table_height, keep_table
                if table_height(data, (210 - 2 * content.settings.margin_mm) * 72 / 25.4) <= 280:
                    keep_table(table)
                else:
                    for cell in table.rows[0].cells:
                        cell.paragraphs[-1].paragraph_format.keep_with_next = True
                paragraph(doc).paragraph_format.space_after = Pt(3)
            elif b.kind == "figure":
                if label:
                    block_heading(doc, label, dark)
                if b.text:
                    academic_paragraph(doc, b.text, keep=True)
                svg, png = render(b, theme)
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 1.0
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(0)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.keep_with_next = bool(b.figure.caption)
                image_with_svg(
                    p,
                    svg,
                    png,
                    min(
                        152 if b.figure.kind in ("block_diagram", "circuit", "control_diagram") else 146,
                        210 - 2 * content.settings.margin_mm,
                    ),
                )
                if b.figure.caption:
                    p = paragraph(
                        doc, b.figure.caption, color="#655F55", size=12, book=True
                    )
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.line_spacing = Pt(18)
                figure_count += 1
            elif b.kind == "exercise":
                example_number += 1
                if b.text:
                    flow_text(doc, b.text)
                framed_content(doc, academic_label(b, label, example_number), b.problem,
                               dark, light, kind="exercise", givens=b.givens,
                               keep=bool(b.steps))
                # Short solutions form a compact editorial unit. Long solutions may
                # break at step boundaries; a long step can itself flow with widows.
                compact = (
                    len(b.steps) <= 3
                    and sum(map(len, [b.problem, b.givens, b.result, *b.steps])) <= 650
                )
                if b.steps:
                    p = block_heading(doc, "الحل", dark, size=13)
                    p.paragraph_format.space_before = Pt(5)
                    num_id = numbering(doc, ordered=True)
                    for n, step in enumerate(b.steps):
                        p = list_paragraph(doc, step, num_id)
                        p.paragraph_format.keep_together = len(step) < 450
                        p.paragraph_format.keep_with_next = bool(
                            (compact and n < len(b.steps) - 1)
                            or (b.result and n == len(b.steps) - 1)
                        )
                if b.result:
                    framed_content(doc, "النتيجة", b.result, dark, light, kind="result")
            elif b.kind == "list":
                if label:
                    block_heading(doc, label, dark)
                if b.text:
                    flow_text(doc, b.text, keep=True)
                num_id = numbering(doc, b.ordered)
                for item in b.items:
                    list_paragraph(doc, item, num_id)
            else:
                if label:
                    block_heading(doc, label, dark)
                flow_text(doc, visible_body(b))
            from .pagination import apply
            apply(doc, list(doc.element.body)[start_node:-1], content.settings.layout.get(b.id))
    if content.settings.end_marker:
        # A closing ornament must not create an otherwise empty page. Attach it
        # to the final flowing paragraph. Formula-only endings keep both lines
        # together; table endings keep their last data row with the closing line.
        p = doc.paragraphs[-1]
        has_math = bool(p._p.findall(".//m:oMath", NS))
        if p.text.strip():
            text(p, " — انتهت المحاضرة", color="#766F63", size=10.5, book=True)
        elif has_math:
            p.add_run().add_break()
            text(p, "انتهت المحاضرة", color="#766F63", size=10.5, book=True)
            p.paragraph_format.keep_together = True
        else:
            text(p, "انتهت المحاضرة", color="#766F63", size=10.5, book=True)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.line_spacing = Pt(18)
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
            if doc.tables:
                for cell in doc.tables[-1].rows[-1].cells:
                    cell.paragraphs[-1].paragraph_format.keep_with_next = True
        p.paragraph_format.space_after = Pt(0)
    separate_body_paragraphs(doc)
    protect_math_lines(doc)
    embedded_fonts = 0
    if content.settings.embed_fonts:
        from .font_embedding import embed
        embedded_fonts = embed(doc)
    doc.save(out)
    expected = list(formulas(content))
    with zipfile.ZipFile(out) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        math_count = len(root.findall(".//m:oMath", NS))
        svgs = sum(n.endswith(".svg") for n in z.namelist())
    portable_count = len(root.xpath('.//wp:docPr[@name="CtrlTeaMath"]', namespaces={"wp":"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}))
    if math_count + portable_count != len(expected):
        raise ValueError(
            f"فحص المعادلات لم ينجح: المطلوب {len(expected)} والموجود {math_count}"
        )
    if svgs != figure_count:
        raise ValueError("بعض الرسومات لم تُدرج في مستند Word")
    return {
        "equations": math_count + portable_count,
        "figures": figure_count,
        "math_mode": content.settings.math_mode,
        "portable_math_images": portable_count,
        "embedded_font_faces": embedded_fonts,
        "native_word_math": content.settings.math_mode == "native",
        "word_application_tested": False,
    }


def protect_math_lines(doc):
    """Apply after all block styles: a later caption/heading must not clip math.

    Point-valued python-docx line_spacing defaults to EXACTLY. Writer clips or
    overlaps tall fractions when that survives on a mixed Arabic paragraph.
    AT_LEAST leaves tall formulas room without locking whole blocks together.
    Includes table cells, frames and captions, not just doc.paragraphs.
    """
    from docx.text.paragraph import Paragraph
    for node in doc.element.body.findall(".//w:p", NS):
        if not node.findall(".//m:oMath", NS):
            continue
        p = Paragraph(node, doc)
        spacing = p.paragraph_format.line_spacing
        minimum = max(26, spacing.pt if hasattr(spacing, "pt") else 0)
        p.paragraph_format.line_spacing = Pt(minimum)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
        pr = p._p.get_or_add_pPr()
        snap = pr.find(qn("w:snapToGrid"))
        if snap is None:
            snap = element("w:snapToGrid")
            pr.append(snap)
        snap.set(qn("w:val"), "0")


def writer_math_defaults():
    """Writer has separate Math font defaults and does not honor all OMML rFonts.

    Use its documented FontFormatList / StandardFormat configuration, confined
    to the disposable export profile. FontWeight NORMAL=5, FontItalic NORMAL=2.
    This changes glyph presentation only; the OMML XML is never rewritten.
    """
    namespace = "http://openoffice.org/2001/registry"
    root = etree.Element("{" + namespace + "}items", nsmap={"oor": namespace})
    fonts = etree.SubElement(
        root,
        "item",
        {"{" + namespace + "}path": "/org.openoffice.Office.Math/FontFormatList"},
    )
    for name, italic in [("CtMathRegular", 0), ("CtMathItalic", 2)]:
        node = etree.SubElement(
            fonts,
            "node",
            {"{" + namespace + "}name": name, "{" + namespace + "}op": "replace"},
        )
        for key, value in [
            ("Name", MATH),
            ("CharSet", -1),
            ("Family", 0),
            ("Pitch", 0),
            ("Weight", 5),
            ("Italic", italic),
        ]:
            prop = etree.SubElement(node, "prop", {"{" + namespace + "}name": key})
            etree.SubElement(prop, "value").text = str(value)
    item = etree.SubElement(
        root,
        "item",
        {"{" + namespace + "}path": "/org.openoffice.Office.Math/StandardFormat"},
    )
    for key, value in [
        # Writer's OMML importer ignores individual w:sz, so its Math default
        # must agree with the native Word equation's 14pt size. 18pt made short
        # inline symbols disproportionate to Cairo and changed line wrapping.
        ("BaseSize", MATH_SIZE),
        ("VariableFont", "CtMathItalic"),
        ("FunctionFont", "CtMathRegular"),
        ("NumberFont", "CtMathRegular"),
        ("TextFont", "CtMathRegular"),
    ]:
        prop = etree.SubElement(item, "prop", {"{" + namespace + "}name": key})
        etree.SubElement(prop, "value").text = str(value)
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def to_pdf(docx: Path, *, report=None):
    binary = find_binary("libreoffice")
    if not binary:
        raise ValueError("LibreOffice غير مثبت؛ ثبّته ثم أعد التصدير")
    from .pdf_math import verify_pdf_math

    # Convert into a fresh directory. An older PDF must never make a failed
    # conversion look successful, and no incomplete PDF is published.
    with tempfile.TemporaryDirectory(prefix="ctrltea-lo-") as profile:
        user = Path(profile) / "user"
        user.mkdir()
        (user / "registrymodifications.xcu").write_bytes(writer_math_defaults())
        import os

        env = tool_environment()
        result = subprocess.run(
            [
                binary,
                "-env:UserInstallation=" + Path(profile).as_uri(),
                "--headless",
                "--convert-to",
                'pdf:writer_pdf_Export:{"UseTaggedPDF":{"type":"boolean","value":"true"},"UseLosslessCompression":{"type":"boolean","value":"true"},"ReduceImageResolution":{"type":"boolean","value":"false"}}',
                "--outdir",
                profile,
                str(docx),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            env=env,
        )
        converted = Path(profile) / docx.with_suffix(".pdf").name
        if result.returncode or not converted.exists() or converted.stat().st_size < 1000:
            raise ValueError(
                "تعذر إنتاج PDF من LibreOffice: " + (result.stderr or result.stdout)[-600:]
            )
        math_check = verify_pdf_math(docx, converted)
        from .pdf_math import verify_portable_math
        math_check["portable"] = verify_portable_math(docx, converted)
        pdf = docx.with_suffix(".pdf")
        shutil.copyfile(converted, pdf)
        from .toc import cache_pages
        cache_pages(docx, pdf)
        if report is not None:
            report["pdf_math"] = math_check
    return pdf


def export_lecture(lid, draft=False, progress=lambda n: None):
    current = store.lecture(lid)
    content = LectureDocument.model_validate(current["document"])
    if not content.sections or not any(s.blocks for s in content.sections):
        raise ValueError("أضف محتوى للمحاضرة قبل التصدير")
    check = source_warnings(content, lid)
    hard_errors = [x for x in check["issues"] if x["severity"] == "error"]
    if hard_errors and not draft:
        raise ValueError("تغيّر نص سؤال حرفي. صححه أو صدّر مسودة واضحة للمراجعة.")
    for bid, latex in formulas(content):
        omml(latex)
    progress(25)
    eid = store.uid()
    folder = store.DATA / "exports" / eid
    folder.mkdir()
    docx = folder / "lecture.docx"
    report = build_docx(content, docx, draft, theme=current["theme"])
    progress(65)
    pdf = to_pdf(docx, report=report)
    import fitz

    with fitz.open(pdf) as d:
        report["pages"] = len(d)
        report["internal_links"] = sum(len(p.get_links()) for p in d)
        report["fonts"] = sorted({font[3] for p in d for font in p.get_fonts()})
    report.update(
        {
            "export_id": eid,
            "lecture_id": lid,
            "revision": current["revision"],
            "theme": current["theme"],
            "draft": draft,
            "checks": check,
            "created": store.now(),
            "footer_policy": FOOTER_POLICY,
            "visual_review": "pending",
        }
    )
    (folder / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    progress(100)
    return report
