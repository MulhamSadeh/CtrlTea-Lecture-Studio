from __future__ import annotations

import copy
import hashlib
import io
import re
import subprocess
import zipfile
from lxml import etree
from .runtime import find_binary, tool_environment
from . import store
from .theme import MATH, MATH_SIZE

NS = {
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
INLINE = re.compile(r"(\\\([\s\S]*?\\\)|\$(?!\$)[^\n$]+\$)")


def segments(text):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("\\(") and part.endswith("\\)"):
            yield True, part[2:-2]
        elif part.startswith("$") and part.endswith("$"):
            yield True, part[1:-1]
        else:
            yield False, part


def omml(latex):
    if len(latex) > 12000 or not latex.strip():
        raise ValueError("المعادلة فارغة أو طويلة جدًا")
    if re.search(r"\\(?:input|include|write|openout|def|newcommand|href|url)\b", latex):
        raise ValueError("أمر LaTeX غير مسموح في المعادلة")
    key = hashlib.sha256((f"v5:{MATH}:{MATH_SIZE}:" + latex).encode()).hexdigest()
    cached = store.DATA / "math" / f"{key}.xml"
    if cached.exists():
        return etree.fromstring(cached.read_bytes())
    result = subprocess.run(
        [find_binary("pandoc"), "--from=markdown+tex_math_dollars", "--to=docx"],
        input=("$$\n" + latex + "\n$$").encode(),
        env=tool_environment(),
        capture_output=True,
        timeout=35,
    )
    if result.returncode or result.stderr:
        raise ValueError(
            f'صيغة رياضية غير مدعومة: {latex[:100]}؛ {result.stderr.decode(errors="replace")[:250]}'
        )
    with zipfile.ZipFile(io.BytesIO(result.stdout)) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    maths = root.findall(".//m:oMath", NS)
    if len(maths) != 1:
        raise ValueError(f"تعذر إنشاء معادلة Word أصلية: {latex[:100]}")
    math = copy.deepcopy(maths[0])
    # Canonical dPr child order matters to Writer's streaming OMML importer.
    # Pandoc 3.1 emits endChr before sepChr; Writer then loses the closing delimiter.
    order = {"begChr": 0, "sepChr": 1, "endChr": 2, "grow": 3, "shp": 4, "ctrlPr": 5}
    for properties in math.findall(".//m:dPr", NS):
        properties[:] = sorted(
            properties, key=lambda child: order.get(etree.QName(child).localname, 99)
        )
    # Word math has its own directional layout. Never set RTL on the formula runs.
    for run in math.findall(".//m:r", NS):
        pr = run.find("w:rPr", NS)
        if pr is None:
            pr = etree.Element("{" + NS["w"] + "}rPr")
            run.insert(1 if run.find("m:rPr", NS) is not None else 0, pr)
        # Replace presentation properties rather than appending duplicate values.
        for child in list(pr):
            if etree.QName(child).localname in {"rFonts", "sz", "szCs", "rtl"}:
                pr.remove(child)
        fonts = etree.SubElement(pr, "{" + NS["w"] + "}rFonts")
        for attr in ("ascii", "hAnsi", "cs"):
            fonts.set("{" + NS["w"] + "}" + attr, MATH)
        size = etree.SubElement(pr, "{" + NS["w"] + "}sz")
        size.set("{" + NS["w"] + "}val", str(MATH_SIZE * 2))
        size_cs = etree.SubElement(pr, "{" + NS["w"] + "}szCs")
        size_cs.set("{" + NS["w"] + "}val", str(MATH_SIZE * 2))
        rtl = etree.SubElement(pr, "{" + NS["w"] + "}rtl")
        rtl.set("{" + NS["w"] + "}val", "0")
    cached.write_bytes(etree.tostring(math))
    return math


def formulas(document):
    for section in document.sections:
        for b in section.blocks:
            if b.kind == "equation":
                yield b.id, b.latex
            texts = [
                b.title,
                b.text,
                b.problem,
                b.givens,
                b.result,
                *b.steps,
                *b.items,
                *b.headers,
                *[x for row in b.rows for x in row],
            ]
            if b.figure:
                texts.append(b.figure.caption)
            for text in texts:
                for is_math, value in segments(text):
                    if is_math:
                        yield b.id, value
