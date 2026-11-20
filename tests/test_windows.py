"""Windows path cases and Windows raster path, exercised on the available OS.

These are not a claim that WinGet, GDI or Microsoft Word were run on Windows.
"""
from pathlib import Path
import io
import os
import sys
import zipfile
import fitz
from PIL import Image
import pytest
from ctrltea import runtime,store,figures
from ctrltea.models import Block,Figure,LectureDocument,Reference
from ctrltea import sources
from ctrltea.figures import render
from ctrltea.exporter import build_docx,to_pdf


@pytest.mark.parametrize('tool,relative',[('libreoffice','LibreOffice/program/soffice.com'),('pandoc','Pandoc/pandoc.exe'),('tesseract','Tesseract-OCR/tesseract.exe')])
def test_program_files_with_spaces_and_arabic(tmp_path,monkeypatch,tool,relative):
    base=tmp_path/'Program Files محاضرات';exe=base/relative;exe.parent.mkdir(parents=True);exe.write_bytes(b'test')
    monkeypatch.setattr(runtime,'IS_WINDOWS',True)
    monkeypatch.setattr(runtime.shutil,'which',lambda _:None)
    for key in runtime.OVERRIDES.values():monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('ProgramFiles',str(base))
    assert runtime.find_binary(tool)==str(exe)


def test_custom_paths_take_priority_and_invalid_override_is_not_ignored(tmp_path,monkeypatch):
    exe=tmp_path/'portable tools'/'soffice.com';exe.parent.mkdir();exe.touch()
    monkeypatch.setenv('CTRLTEA_LIBREOFFICE',str(exe))
    assert runtime.find_binary('libreoffice')==str(exe)
    exe.unlink()
    with pytest.raises(ValueError,match='CTRLTEA_LIBREOFFICE'):runtime.find_binary('libreoffice')


def test_local_appdata_pandoc_path(tmp_path,monkeypatch):
    exe=tmp_path/'Programs/Pandoc/pandoc.exe';exe.parent.mkdir(parents=True);exe.touch()
    monkeypatch.setattr(runtime,'IS_WINDOWS',True);monkeypatch.setattr(runtime.shutil,'which',lambda _:None)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));monkeypatch.delenv('CTRLTEA_PANDOC',raising=False)
    assert runtime.find_binary('pandoc')==str(exe)


def test_tessdata_override_is_scoped_to_child_environment(tmp_path,monkeypatch):
    for name in ['ara','eng']:(tmp_path/(name+'.traineddata')).touch()
    monkeypatch.setenv('CTRLTEA_TESSDATA_DIR',str(tmp_path));monkeypatch.setenv('TESSDATA_PREFIX','unchanged')
    env=runtime.tool_environment()
    assert env['TESSDATA_PREFIX']==str(tmp_path)and os.environ['TESSDATA_PREFIX']=='unchanged'
    (tmp_path/'ara.traineddata').unlink()
    with pytest.raises(ValueError,match='ara.traineddata'):runtime.tool_environment()


def test_windows_svg_preview_does_not_import_cairo(monkeypatch):
    monkeypatch.setattr(runtime,'IS_WINDOWS',True)
    monkeypatch.setitem(sys.modules,'cairosvg',None)
    png=runtime.svg_png(b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><rect width="100" height="40" fill="#8B3F25"/></svg>',output_width=500)
    image=Image.open(io.BytesIO(png));assert image.size==(500,200)
    assert image.convert('RGB').getpixel((250,100))==(139,63,37)


@pytest.mark.parametrize('kind',['step','histogram','block_diagram','circuit'])
def test_windows_generated_svg_fallback_keeps_scientific_svg(client,lecture,monkeypatch,kind):
    monkeypatch.setattr(runtime,'IS_WINDOWS',True)
    monkeypatch.setattr(figures,'IS_WINDOWS',True)
    spec={'kind':kind}
    if kind=='histogram':spec.update(values=[25,26,28,30,32,33],bins=3)
    if kind in {'block_diagram','circuit'}:spec.update(nodes=[{'id':'a','label':'Input','x':0,'y':0},{'id':'b','label':'Output','x':300,'y':0}],edges=[{'start':'a','end':'b','kind':'arrow'if kind=='block_diagram'else 'wire'}])
    figure=Figure.model_validate(spec)
    source=sources.register(lecture[1]['id'],'diagnostic.txt',b'Explicit synthetic fixture for renderer tests.')
    svg,png=render(Block(kind='figure',figure=figure,refs=[Reference(source_id=source['id'])]),'olive')
    assert svg.read_bytes().lstrip().startswith((b'<svg',b'<?xml'))
    assert Image.open(png).width==1800


def test_windows_preview_path_real_control_docx_and_pdf(client,tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'IS_WINDOWS',True)
    monkeypatch.setattr(figures,'IS_WINDOWS',True)
    # Runs the Windows raster branches with actual tools on Linux, not a Windows VM.
    source=store.ROOT/'examples/omml-control.document.json';raw=source.read_bytes()
    document=LectureDocument.model_validate_json(raw);before=document.model_dump_json()
    out=tmp_path/'محاضرة عربي English'/ 'windows-path.docx';out.parent.mkdir()
    r=build_docx(document,out,theme='olive');to_pdf(out,report=r)
    assert r['equations']==r['pdf_math']['visible']==100
    assert before==document.model_dump_json()and raw==source.read_bytes()
    with zipfile.ZipFile(out)as z:assert len([n for n in z.namelist()if n.endswith('.svg')])==5
    with fitz.open(out.with_suffix('.pdf'))as pdf:
        assert any('Cairo'in f[3]for p in pdf for f in p.get_fonts())
        footer=pdf[1].get_pixmap();assert max(abs(a-b)for a,b in zip(footer.pixel(20,820)[:3],(85,107,47)))<=2
