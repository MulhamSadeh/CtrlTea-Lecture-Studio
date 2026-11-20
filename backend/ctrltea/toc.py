"""Native page references, cached from the final PDF for the Word download."""
import zipfile
from lxml import etree
from docx.oxml.ns import qn
from docx.shared import Pt
from .mathml import NS


def page_reference(p, anchor):
    from .exporter import element
    for kind in ('begin', 'instruction', 'separate', 'result', 'end'):
        run = p.add_run()
        run.font.size = Pt(10)
        if kind == 'instruction':
            node = element('w:instrText')
            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            node.text = ' PAGEREF ' + anchor + ' '
            run._r.append(node)
        elif kind == 'result':
            run.text = '…'
        else:
            run._r.append(element('w:fldChar', fldCharType=kind))


def cache_pages(docx, pdf):
    import fitz
    with zipfile.ZipFile(docx) as package:
        files = {n: package.read(n) for n in package.namelist()}
    root = etree.fromstring(files['word/document.xml'])
    anchors = root.xpath('.//w:hyperlink/@w:anchor', namespaces=NS)
    if not anchors:
        return
    # Only title hyperlinks are created in the cover index. Page fields are
    # deliberately not hyperlinks, so each row has exactly one destination.
    with fitz.open(pdf) as document:
        names = document.resolve_names() if hasattr(document, 'resolve_names') else {}
        named_pages = {anchor: names[anchor]['page'] + 1 for anchor in anchors
                       if anchor in names and names[anchor].get('page', -1) >= 0}
        links = [link for page in document for link in sorted(page.get_links(), key=lambda link: (link['from'].y0, link['from'].x0))
                 if link.get('kind') == fitz.LINK_GOTO]
    # Wrapped titles may produce more than one link rectangle. Collapse only
    # repeated rectangles at the same row, never different sections on a page.
    destinations = []
    previous = None
    for link in links:
        row = (link.get('page'), round(link['from'].y0 / 10))
        if row != previous:
            destinations.append(link['page'] + 1)
        previous = row
    if len(named_pages) == len(anchors):
        pages = named_pages
    elif len(destinations) == len(anchors):
        pages = dict(zip(anchors, destinations))
    else:
        # Keep native PAGEREF fields instead of caching guessed page numbers.
        return
    for p in root.findall('.//w:p', NS):
        anchor, result = None, False
        for run in p.findall('w:r', NS):
            instruction = run.find('w:instrText', NS)
            if instruction is not None and 'PAGEREF' in (instruction.text or ''):
                anchor = instruction.text.split()[1]
            marker = run.find('w:fldChar', NS)
            if marker is not None:
                kind = marker.get(qn('w:fldCharType'))
                if kind == 'separate':
                    result = True
                elif kind == 'end':
                    anchor, result = None, False
            t = run.find('w:t', NS)
            if anchor in pages and result and t is not None:
                t.text = str(pages[anchor])
    files['word/document.xml'] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
    with zipfile.ZipFile(docx, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in files.items():
            package.writestr(name, data)
