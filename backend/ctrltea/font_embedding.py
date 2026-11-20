"""Embed the bundled OFL/GUST fonts in the portable Word package."""
from uuid import uuid4
from lxml import etree
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.part import Part
from docx.opc.packuri import PackURI
from docx.oxml.ns import qn
from .runtime import ROOT

FAMILIES = {
    'Cairo': ('Cairo-Regular.ttf', 'Cairo-Bold.ttf'),
    'Noto Naskh Arabic': ('NotoNaskhArabic-Regular.ttf', 'NotoNaskhArabic-Bold.ttf'),
    'Noto Sans Arabic': ('NotoSansArabic-Regular.ttf', 'NotoSansArabic-Bold.ttf'),
    'Source Sans 3': ('SourceSans3-Regular.ttf', 'SourceSans3-Bold.ttf'),
    'Source Serif 4': ('SourceSerif4-Regular.ttf', 'SourceSerif4-Bold.ttf'),
    'Latin Modern Math': ('LatinModernMath-Regular.otf', None),
}


def embed(doc):
    part = doc.part.part_related_by(RT.FONT_TABLE)
    root = etree.fromstring(part.blob)
    count = 0
    for family, files in FAMILIES.items():
        font = next((el for el in root if el.get(qn('w:name')) == family), None)
        if font is None:
            font = etree.SubElement(root, qn('w:font'))
            font.set(qn('w:name'), family)
        for face, filename in zip(('embedRegular', 'embedBold'), files):
            if filename is None:
                continue
            key = uuid4()
            mask = key.bytes[::-1]
            data = bytearray((ROOT / 'assets/fonts' / filename).read_bytes())
            for i in range(32):
                data[i] ^= mask[i % 16]
            font_part = Part(PackURI('/word/fonts/' + key.hex + '.odttf'),
                             'application/vnd.openxmlformats-officedocument.obfuscatedFont',
                             bytes(data), doc.part.package)
            relation = part.relate_to(font_part, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/font')
            node = etree.SubElement(font, qn('w:' + face))
            node.set(qn('r:id'), relation)
            node.set(qn('w:fontKey'), '{' + str(key).upper() + '}')
            count += 1
    part._blob = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
    node = etree.SubElement(doc.settings.element, qn('w:embedTrueTypeFonts'))
    node.set(qn('w:val'), 'true')
    return count
