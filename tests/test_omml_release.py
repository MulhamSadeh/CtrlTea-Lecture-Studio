"""Regression checks for native math, mixed direction and the shipped fixtures."""
import zipfile
from pathlib import Path
import fitz
from lxml import etree
import pytest
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_LINE_SPACING
from ctrltea import store
from ctrltea.exporter import (setup,paragraph,protect_math_lines,build_docx,to_pdf,academic_title)
from ctrltea.mathml import NS,omml
from ctrltea.models import LectureDocument
from ctrltea.pdf_math import verify_pdf_math
from scripts.render_examples import verify_content


def test_known_exact_height_pdf_is_rejected_for_overlap():
    base=store.ROOT/'examples/diagnostics/math-overlap/exact-height'
    with pytest.raises(ValueError,match='تداخل'):
        verify_pdf_math(base.with_suffix('.docx'),base.with_suffix('.pdf'))


def test_safe_reference_has_four_visible_native_formulas():
    base=store.ROOT/'examples/diagnostics/math-overlap/protected-height'
    result=verify_pdf_math(base.with_suffix('.docx'),base.with_suffix('.pdf'))
    assert result['required']==result['visible']==4
    assert result['collision_check']['substantial_math_text_collisions']==0


def test_saved_100_formula_lecture_preserves_science(client,tmp_path):
    source=store.ROOT/'examples/omml-control.document.json';raw=source.read_bytes()
    doc=LectureDocument.model_validate_json(raw);before=doc.model_dump_json()
    out=tmp_path/'current.docx';report=build_docx(doc,out,theme='olive')
    to_pdf(out,report=report);verify_content(doc,out)
    assert report['equations']==report['pdf_math']['visible']==100
    assert raw==source.read_bytes() and before==doc.model_dump_json()
    assert not report['word_application_tested']
    with fitz.open(out.with_suffix('.pdf')) as pdf:
        assert any('Cairo'in f[3] for page in pdf for f in page.get_fonts())


@pytest.mark.parametrize('latex',[r'y(t)',r'\frac{dy}{dt}',r'\begin{pmatrix}1&2\\3&4\end{pmatrix}',r'\int_0^\infty e^{-st}dt'])
def test_native_math_font_size_and_ltr(client,latex):
    m=omml(latex)
    assert m.tag=='{'+NS['m']+'}oMath'
    for r in m.findall('.//m:r',NS):
        pr=r.find('w:rPr',NS);fonts=pr.find('w:rFonts',NS)
        assert all(fonts.get('{'+NS['w']+'}'+x)=='Latin Modern Math'for x in ['ascii','hAnsi','cs'])
        assert pr.find('w:sz',NS).get('{'+NS['w']+'}val')=='28'
        assert pr.find('w:szCs',NS).get('{'+NS['w']+'}val')=='28'
        assert pr.find('w:rtl',NS).get('{'+NS['w']+'}val')=='0'


@pytest.mark.parametrize('container',['body','cell'])
def test_math_height_survives_final_styles(client,container):
    d=Document();setup(d,LectureDocument(title='اختبار'),'olive')
    parent=d if container=='body'else d.add_table(rows=1,cols=1).cell(0,0)
    p=paragraph(parent,r'نص عربي Output \(\frac{dy}{dt}=u(t)\) ثم شرح.',book=True)
    p.paragraph_format.line_spacing=Pt(10)
    p.paragraph_format.line_spacing_rule=WD_LINE_SPACING.EXACTLY
    protect_math_lines(d);protect_math_lines(d)
    assert p.paragraph_format.line_spacing_rule==WD_LINE_SPACING.AT_LEAST
    assert p.paragraph_format.line_spacing.pt>=26
    assert p._p.find('w:dir/m:oMath',NS)is not None
    assert len(p._p.findall('w:pPr/w:snapToGrid',NS))==1


def test_heading_colon_rule_without_duplicate_punctuation(client):
    d=Document();setup(d,LectureDocument(title='اختبار'),'olive')
    p=d.add_paragraph();academic_title(p,'عنوان:','#556B2F')
    assert p.text=='عنوان:'
    assert p._p.find('w:pPr/w:pBdr/w:bottom',NS)is not None


@pytest.mark.parametrize('name',['Cairo-Regular.ttf','Cairo-Bold.ttf'])
def test_reader_cairo_font_is_served(client,name):
    response=client.get('/document-fonts/'+name)
    assert response.status_code==200
    assert response.content==(store.ROOT/'assets/fonts'/name).read_bytes()


def test_normal_text_keeps_cairo_and_arabic_direction(client):
    d=Document();setup(d,LectureDocument(title='اختبار'),'olive')
    p=paragraph(d,'الخرج Output (A) واضح.',book=True)
    assert p._p.find('w:pPr/w:bidi',NS).get('{'+NS['w']+'}val')=='1'
    for f in p._p.findall('.//w:rFonts',NS):
        assert all(f.get('{'+NS['w']+'}'+x)=='Cairo'for x in ['ascii','hAnsi','cs'])
