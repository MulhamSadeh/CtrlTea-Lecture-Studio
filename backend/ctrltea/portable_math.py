"""Verified formula bitmaps with editable LaTeX retained in the lecture.

The existing equation engine runs on isolated LTR pages, once per unique
formula. Word receives high-resolution pixels, never a mixed-direction object.
"""
import copy
import hashlib
import json
import tempfile
from pathlib import Path
import fitz
from docx import Document
from docx.shared import Mm, Pt
from docx.enum.text import WD_LINE_SPACING
from . import store
from .mathml import omml


def paths(latex):
    key = hashlib.sha256(('portable-v1:' + latex).encode()).hexdigest()
    folder = store.DATA / 'math'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (key + '.png'), folder / (key + '.json')


def prepare(formulas):
    missing = [latex for latex in dict.fromkeys(latex for _, latex in formulas)
               if not all(p.exists() for p in paths(latex))]
    if not missing:
        return
    from .exporter import to_pdf, element
    with tempfile.TemporaryDirectory(prefix='ctrltea-formula-') as directory:
        for offset in range(0, len(missing), 80):
            batch = missing[offset:offset + 80]
            doc = Document()
            section = doc.sections[0]
            section.page_width, section.page_height = Mm(210), Mm(297)
            section.top_margin = section.bottom_margin = Mm(15)
            section.left_margin = section.right_margin = Mm(19)
            for i, latex in enumerate(batch):
                p = doc.add_paragraph()
                p.paragraph_format.page_break_before = i > 0
                p.paragraph_format.line_spacing = 1.0
                p._p.get_or_add_pPr().append(element('w:bidi', val='0'))
                p._p.append(copy.deepcopy(omml(latex)))
            target = Path(directory) / 'formulas.docx'
            doc.save(target)
            report = {}
            pdf = to_pdf(target, report=report)
            evidence = sorted(report['pdf_math']['formulas'], key=lambda item: item['omml_index'])
            if len(evidence) != len(batch):
                raise ValueError('لم تكتمل معاينة المعادلات الثابتة')
            with fitz.open(pdf) as rendered:
                for latex, item in zip(batch, evidence):
                    page = rendered[item['page'] - 1]
                    rect = fitz.Rect(item['bbox']) + (-1.5, -1.5, 1.5, 1.5)
                    if not page.rect.contains(rect):
                        raise ValueError('معادلة أكبر من مساحة الطباعة؛ قسّمها إلى معادلات أقصر')
                    png, metadata = paths(latex)
                    page.get_pixmap(matrix=fitz.Matrix(5, 5), clip=rect, alpha=False).save(png)
                    metadata.write_text(json.dumps({'width_pt': rect.width, 'height_pt': rect.height}), encoding='utf-8')


def insert(p, latex, width_limit_pt):
    from .exporter import element
    png, metadata = paths(latex)
    if not png.exists() or not metadata.exists():
        prepare([('', latex)])
    info = json.loads(metadata.read_text())
    scale = min(1.0, width_limit_pt / info['width_pt'])
    if scale < .7:
        raise ValueError('المعادلة طويلة جدًا؛ قسّمها بدل تصغيرها إلى حجم غير مقروء')
    run = p.add_run()
    run._r.get_or_add_rPr().append(element('w:rtl', val='0'))
    image = run.add_picture(str(png), width=Pt(info['width_pt'] * scale), height=Pt(info['height_pt'] * scale))
    image._inline.docPr.set('name', 'CtrlTeaMath')
    image._inline.docPr.set('descr', 'CtrlTea LaTeX: ' + latex)
    p.paragraph_format.line_spacing = Pt(max(26, info['height_pt'] * scale + 4))
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
