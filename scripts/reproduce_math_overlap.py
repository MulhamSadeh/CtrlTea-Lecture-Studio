"""Reproduce exact-height overlap using the actual Writer conversion."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
from docx import Document
from docx.shared import Pt,Mm
from docx.enum.text import WD_LINE_SPACING
from ctrltea import store
from ctrltea.models import LectureDocument
from ctrltea.exporter import setup,paragraph,protect_math_lines,writer_math_defaults
from ctrltea.pdf_math import verify_pdf_math


def reproduce(output):
    output.mkdir(parents=True,exist_ok=True)
    d=Document();setup(d,LectureDocument(title='اختبار المعادلات المختلطة'),'olive')
    d.sections[0].left_margin=d.sections[0].right_margin=Mm(50)
    d.sections[0].different_first_page_header_footer=False
    p=paragraph(d,r'هذه عبارة عربية قبل الكسر \(\frac{d^2y(t)}{dt^2}=u(t)\) وبعده شرح بالعربية. '*4,book=True)
    p.paragraph_format.line_spacing=Pt(12);p.paragraph_format.line_spacing_rule=WD_LINE_SPACING.EXACTLY
    results={}
    for name in ['exact-height','protected-height']:
        if name=='protected-height':protect_math_lines(d)
        source=output/(name+'.docx');d.save(source)
        with tempfile.TemporaryDirectory(prefix='ct-overlap-profile-') as tmp:
            profile=Path(tmp);(profile/'user').mkdir()
            (profile/'user/registrymodifications.xcu').write_bytes(writer_math_defaults())
            r=subprocess.run([shutil.which('soffice')or shutil.which('libreoffice'),'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','pdf:writer_pdf_Export:{"UseTaggedPDF":{"type":"boolean","value":"true"}}','--outdir',str(output),str(source)],env=dict(os.environ,FONTCONFIG_FILE=str(store.ROOT/'assets/fonts.conf')),capture_output=True,timeout=120)
            if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
        try:results[name]={'accepted':True,'check':verify_pdf_math(source,source.with_suffix('.pdf'))}
        except ValueError as error:results[name]={'accepted':False,'error':str(error)}
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    return results

if __name__=='__main__':
    import sys
    with tempfile.TemporaryDirectory(prefix='ct-overlap-data-')as tmp:
        store.DATA=Path(tmp)/'data';store.init();print(json.dumps(reproduce(Path(sys.argv[1]).resolve()),ensure_ascii=False,indent=2))
