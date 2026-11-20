"""Re-export the saved lectures without authoring or persistent data changes."""
from pathlib import Path
import argparse,json,tempfile
from ctrltea import store,bundles
from ctrltea.models import LectureDocument
from ctrltea.exporter import build_docx,to_pdf
from ctrltea.theme import PALETTES
from render_examples import verify_content


def render_one(document,out,theme):
    before=document.model_dump_json()
    report=build_docx(document,out,theme=theme)
    to_pdf(out,report=report);report.update(verify_content(document,out))
    assert document.model_dump_json()==before
    import fitz
    with fitz.open(out.with_suffix('.pdf')) as pdf:report['pages']=len(pdf)
    report['scientific_content_unchanged']=True
    return report


def run(output,all_themes=False):
    output.mkdir(parents=True,exist_ok=True);previous=store.DATA;reports={}
    try:
        with tempfile.TemporaryDirectory(prefix='ct-render-') as temp:
            store.DATA=Path(temp)/'data';store.init()
            for name,source in [('Control_OMML_Fixed','omml-control.document.json'),('Control_Study_Notes','study-control.document.json')]:
                raw=(store.ROOT/'examples'/source).read_bytes()
                document=LectureDocument.model_validate_json(raw)
                for theme in PALETTES if all_themes else ['olive']:
                    key=name if theme=='olive'else name+'_'+theme
                    reports[key]=render_one(document,output/(key+'.docx'),theme)
                assert raw==(store.ROOT/'examples'/source).read_bytes()
            restored=bundles.import_course((store.ROOT/'examples/projects/statistics-project.zip').read_bytes())
            lid=store.all_rows('SELECT id FROM lectures WHERE course_id=?',(restored['course_id'],))[0]['id']
            doc=LectureDocument.model_validate(store.lecture(lid)['document'])
            for theme in PALETTES if all_themes else ['honey']:
                name='Statistics_Study_Notes'+(''if theme=='honey'else '_'+theme)
                reports[name]=render_one(doc,output/(name+'.docx'),theme)
    finally:store.DATA=previous
    (output/'verification.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2))
    return reports

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=store.ROOT/'examples/study-exports');p.add_argument('--all-themes',action='store_true');a=p.parse_args();print(json.dumps(run(a.output.resolve(),a.all_themes),ensure_ascii=False,indent=2))
