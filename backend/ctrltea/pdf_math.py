"""Verify painted PDF formulas, rather than equating OMML presence with success.

Writer's tagged PDF gives each native Math object a Formula structure element
and a physical bounding box. Check its actual text-paint operations and pixels,
then match the required OMML text tokens to distinct visible formula regions.
This detects a missing Math component even when soffice returns exit status 0.
"""

from collections import Counter
import re
import unicodedata
import zipfile

import fitz
from lxml import etree
import numpy as np

from .mathml import NS


def tokens(value):
    # Decompose accents: Writer may emit a spacing dot (U+02D9) whereas OMML
    # uses combining U+0307. Composition could attach it to an unrelated token.
    value = unicodedata.normalize("NFKD", value).translate(
        str.maketrans({"−": "-", "‐": "-", "\u2061": "", "\u2062": ""})
    )
    return Counter(c for c in value if not c.isspace() and unicodedata.category(c) != "Cf")


def required_tokens(math):
    value = "".join(math.xpath(".//m:t/text()", namespaces=NS))
    # Operators, fences and accents can live in properties rather than m:t.
    for tag in ("naryPr/chr", "accPr/chr", "dPr/begChr", "dPr/endChr"):
        parent, child = tag.split("/")
        value += "".join(math.xpath(f".//m:{parent}/m:{child}/@m:val", namespaces=NS))
    return tokens(value)


def verify_math_text_collisions(document, root):
    """Reject substantial glyph collisions between math and narrative text.

    Font em boxes are conservative, so mere contact is allowed. Format controls
    have synthetic boxes in Writer and must never count as printed letters.
    Accents/symbol fonts inside equations are also not surrounding prose.
    This complements the token/ink guard; it is not a full page-layout proof.
    """
    def family(value):
        return re.sub(r"[^a-z0-9]", "", value.lower().split("+")[-1])

    math_fonts = {family(v) for v in root.xpath(
        ".//m:oMath//w:rFonts/@w:ascii", namespaces=NS)}
    prose_fonts = {family(v) for v in root.xpath(
        ".//w:r[not(ancestor::m:oMath)]/w:rPr/w:rFonts/@w:ascii",
        namespaces=NS)} - math_fonts
    checks = 0
    for page_index, page in enumerate(document):
        traces = [s for s in page.get_texttrace()
                  if s.get("type") != 3 and s.get("opacity", 1) >= .1]
        math = [s for s in traces if any(f in family(s["font"]) for f in math_fonts)]
        prose = [s for s in traces if any(f in family(s["font"]) for f in prose_fonts)]
        for formula in math:
            for narrative in prose:
                if not fitz.Rect(formula["bbox"]).intersects(fitz.Rect(narrative["bbox"])):
                    continue
                for cp, _, _, mb in formula["chars"]:
                    if chr(cp).isspace() or unicodedata.category(chr(cp)) == "Cf":
                        continue
                    a = fitz.Rect(mb)
                    for cq, _, _, tb in narrative["chars"]:
                        if chr(cq).isspace() or unicodedata.category(chr(cq)) == "Cf":
                            continue
                        b = fitz.Rect(tb)
                        overlap = a & b
                        checks += 1
                        minimum = min(a.get_area(), b.get_area())
                        if (minimum and overlap.width > .6 and overlap.height > 1.5
                                and overlap.get_area() / minimum > .35):
                            raise ValueError(
                                f"تداخل بين معادلة والنص في الصفحة {page_index+1}. "
                                "لم يُعتمد PDF؛ أعد التصدير بعد تصحيح ارتفاع السطر واتجاهه."
                            )
    return {"substantial_math_text_collisions": 0, "glyph_pairs_checked": checks}


def verify_pdf_math(docx, pdf):
    with zipfile.ZipFile(docx) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    maths = root.findall(".//m:oMath", NS)
    expected = [required_tokens(m) for m in maths]
    with fitz.open(pdf) as document:
        page_refs = {document.page_xref(i): i for i in range(len(document))}
        regions = []
        for xref in range(1, document.xref_length()):
            if document.xref_get_key(xref, "S") != ("name", "/Formula"):
                continue
            _, page_ref = document.xref_get_key(xref, "Pg")
            page_index = page_refs.get(int(page_ref.split()[0])) if page_ref != "null" else None
            _, bounds = document.xref_get_key(xref, "A/BBox")
            numbers = re.findall(r"-?(?:\d+(?:\.\d*)?|\.\d+)", bounds)
            if page_index is None or len(numbers) != 4:
                raise ValueError("تعذر تحديد موضع معادلة في PDF؛ لا يمكن اعتماد ظهورها.")
            page = document[page_index]
            rectangle = fitz.Rect(*map(float, numbers)) * page.transformation_matrix
            regions.append((page_index, rectangle))
        if len(regions) != len(maths):
            raise ValueError(
                f"فحص ظهور المعادلات في PDF فشل: المطلوب {len(maths)} "
                f"والمُصيَّر {len(regions)}. تأكد من تثبيت LibreOffice Math "
                "مع Writer، ثم أعد التصدير. ملف Word الأصلي محفوظ."
            )
        page_traces = {}
        visible = []
        evidence = []
        for number, (page_index, rectangle) in enumerate(regions, 1):
            page = document[page_index]
            if rectangle.is_empty or not page.rect.contains(rectangle):
                raise ValueError(f"المعادلة {number} في الصفحة {page_index+1} مقصوصة أو خارج الصفحة.")
            if page_index not in page_traces:
                page_traces[page_index] = page.get_texttrace()
            letters = []
            area = rectangle + (-0.8, -0.8, 0.8, 0.8)
            for span in page_traces[page_index]:
                if span.get("type") == 3 or span.get("opacity", 1) < .1:
                    continue
                for char, glyph, origin, bbox in span["chars"]:
                    x0, y0, x1, y1 = bbox
                    if area.contains(fitz.Point((x0+x1)/2, (y0+y1)/2)):
                        letters.append(chr(char))
            found = tokens("".join(letters))
            image = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rectangle,
                                    colorspace=fitz.csGRAY, alpha=False)
            pixels = np.frombuffer(image.samples, dtype=np.uint8)
            contrast = int(pixels.max())-int(pixels.min()) if pixels.size else 0
            if not found or contrast < 40 or np.count_nonzero(pixels < 130) < 4:
                raise ValueError(f"المعادلة {number} في الصفحة {page_index+1} لا تحتوي رموزًا مرئية قابلة للقراءة.")
            visible.append(found)
            evidence.append(dict(page=page_index+1, bbox=list(rectangle),
                                 text="".join(letters), ink_checked=True))
        # Physical table order can differ from logical RTL cell order. Match
        # complete token inventories, consuming a distinct region per formula.
        candidates = [[j for j, found in enumerate(visible) if not (need-found)]
                      for need in expected]
        assigned = {}

        def match(start):
            # Iterative augmenting paths also handle long lectures containing
            # thousands of repeated inline variables without recursion limits.
            queue, seen = [start], {start}
            previous = {}
            for index in queue:
                for region in candidates[index]:
                    if region not in assigned:
                        while index != start:
                            assigned[region] = index
                            index, region = previous[index]
                        assigned[region] = start
                        return True
                    owner = assigned[region]
                    if owner not in seen:
                        seen.add(owner)
                        previous[owner] = (index, region)
                        queue.append(owner)
            return False

        for index in sorted(range(len(expected)), key=lambda i: len(candidates[i])):
            if not match(index):
                sample = "".join(maths[index].xpath(".//m:t/text()", namespaces=NS))
                raise ValueError(f"بعض رموز المعادلة {index+1} غير ظاهرة في PDF: {sample[:100]}")
        for region, index in assigned.items():
            evidence[region]["omml_index"] = index+1
        collision_check = verify_math_text_collisions(document, root)
    return dict(required=len(maths), visible=len(regions), all_tokens_present=True,
                painted_regions_checked=True, method="tagged-formula-text-and-ink",
                collision_check=collision_check, formulas=evidence)


def verify_portable_math(docx, pdf):
    """Require each embedded formula bitmap to appear in the exported PDF."""
    import io
    import hashlib
    from pathlib import PurePosixPath
    from PIL import Image
    def digest(data):
        with Image.open(io.BytesIO(data)) as image:
            rgb = image.convert('RGB')
            return (rgb.size, hashlib.sha256(rgb.tobytes()).hexdigest())
    ns = dict(NS, wp='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
              a='http://schemas.openxmlformats.org/drawingml/2006/main',
              r='http://schemas.openxmlformats.org/officeDocument/2006/relationships')
    expected = Counter()
    with zipfile.ZipFile(docx) as package:
        root = etree.fromstring(package.read('word/document.xml'))
        targets = {r.get('Id'):r.get('Target') for r in etree.fromstring(package.read('word/_rels/document.xml.rels'))}
        for inline in root.xpath('.//wp:inline[wp:docPr[@name="CtrlTeaMath"]]', namespaces=ns):
            rid = inline.xpath('.//a:blip/@r:embed', namespaces=ns)[0]
            expected[digest(package.read(str(PurePosixPath('word') / targets[rid])))] += 1
    if not expected:
        return {'required': 0, 'visible': 0, 'painted_images_checked': True}
    found = Counter()
    evidence = []
    with fitz.open(pdf) as document:
        for page in document:
            for xref in {info[0] for info in page.get_images()}:
                key = digest(document.extract_image(xref)['image'])
                if key not in expected:
                    continue
                for rectangle in page.get_image_rects(xref):
                    if not page.rect.contains(rectangle) or rectangle.is_empty:
                        raise ValueError('معادلة مصورة خارج مساحة الصفحة')
                    found[key] += 1
                    evidence.append({'page': page.number + 1, 'bbox': list(rectangle)})
    if expected - found:
        raise ValueError('بعض المعادلات الثابتة غير ظاهرة في PDF؛ لم يُعتمد التصدير')
    return {'required': sum(expected.values()), 'visible': sum(found.values()),
            'painted_images_checked': True, 'formulas': evidence}
