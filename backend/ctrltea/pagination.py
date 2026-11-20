"""Presentation metadata is independent of scientific authoring blocks."""
import math
from docx.text.paragraph import Paragraph
from docx.shared import Pt
from docx.oxml.ns import qn
from .models import LayoutOptions


def table_height(rows, width_pt):
    columns = max((len(row) for row in rows), default=1)
    capacity = max(8, (width_pt / columns - 12) / (13.5 * .55))
    return sum(max([1] + [math.ceil(len(cell) / capacity) for cell in row]) * 23 + 10 for row in rows)


def keep_table(table):
    for i, row in enumerate(table.rows):
        for cell in row.cells:
            for j, p in enumerate(cell.paragraphs):
                p.paragraph_format.keep_with_next = i < len(table.rows)-1 or j < len(cell.paragraphs)-1
                p.paragraph_format.keep_together = True


def apply(doc, nodes, option=None):
    from .exporter import rtl_paragraph
    option = option or LayoutOptions()
    paragraphs = [Paragraph(p, doc) for node in nodes for p in
                  ([node] if node.tag == qn('w:p') else node.findall('.//' + qn('w:p')))]
    if not paragraphs:
        return
    if option.page_before:
        if nodes[0].tag == qn('w:p'):
            paragraphs[0].paragraph_format.page_break_before = True
        else:
            marker = doc.add_paragraph()
            nodes[0].addprevious(marker._p)
            marker.paragraph_format.page_break_before = True
            marker.paragraph_format.keep_with_next = True
            marker.paragraph_format.space_after = Pt(0)
            marker.paragraph_format.line_spacing = Pt(1)
    if option.keep_together == 'keep':
        for p in paragraphs:
            p.paragraph_format.keep_together = True
            p.paragraph_format.keep_with_next = True
        paragraphs[-1].paragraph_format.keep_with_next = option.keep_with_next
    elif option.keep_together == 'split':
        for p in paragraphs:
            if not p._p.xpath('./w:pPr/w:pBdr'):
                p.paragraph_format.keep_with_next = False
            p.paragraph_format.keep_together = False
        paragraphs[-1].paragraph_format.keep_with_next = option.keep_with_next
    elif option.keep_with_next:
        paragraphs[-1].paragraph_format.keep_with_next = True
    if option.direction != 'auto':
        for p in paragraphs:
            if p._p.xpath('.//m:oMath') and not p.text.strip():
                continue
            rtl_paragraph(p, option.direction == 'rtl')
            p.alignment = 2 if option.direction == 'rtl' else 0
