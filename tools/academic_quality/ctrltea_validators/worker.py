"""Bounded subprocess adapter. Only fixed operations; no uploaded code execution."""
import sys,json,os,importlib.util
from pathlib import Path
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main(d):
 op=d['op'];root=Path(d['app_root']) if d.get('app_root') else None
 if root:sys.path.insert(0,str(root/'backend'))
 if op=='row':
  if root is None:raise ImportError('AQ04 app root required')
  return load(root/'backend/ctrltea/skills/ctrltea-lecture-authoring/scripts/check_math.py','aq04_math').verify(d['case'])
 if op=='review':
  p=Path(__file__).resolve().parents[1]/'vendor/ctrltea-lecture-reviewer/scripts/review_record.py'
  m=load(p,'aq05_record');m.validate(d['report']);return m.project(d['report'])
 if op=='score':
  p=Path(__file__).resolve().parents[1]/'vendor/ctrltea-lecture-reviewer/scripts/score_units.py'
  return load(p,'aq05_score').score(d['data'])
 if op=='svg':
  import cairosvg,base64
  return {'png':base64.b64encode(cairosvg.svg2png(bytestring=d['svg'].encode(),output_width=1000,output_height=1000)).decode()}
 from ctrltea.models import LectureDocument,Figure,ControlDiagram
 if op=='structure':
  from ctrltea.author_validation import validate_result
  if 'run_id' in d['document']:sections=validate_result(d['document'],manifest=d.get('manifest'),check_math=False);doc=LectureDocument(sections=sections)
  else:doc=LectureDocument.model_validate(d['document'])
  return {'sections':len(doc.sections),'blocks':sum(len(s.blocks) for s in doc.sections)}
 if op=='math_render':
  from ctrltea.author_validation import math_errors
  from ctrltea import store
  from ctrltea.runtime import find_binary
  if not find_binary('pandoc'):raise ImportError('Pandoc unavailable; OMML conversion unverified')
  (Path(os.environ['CTRLTEA_DATA_DIR'])/'math').mkdir(parents=True,exist_ok=True)
  doc=LectureDocument.model_validate({'sections':d['document']['sections']});errors=math_errors(doc)
  return {'ok':not errors,'errors':errors,'limit':'OMML conversion only; not mathematical truth'}
 if op=='figure':
  f=Figure.model_validate(d['figure'])
  if f.kind=='control_diagram':
   from ctrltea.control_diagrams import diagram
   out=diagram(f.control)
   return {'kind':f.kind,'geometry_valid':True,'rendered_type':type(out).__name__,'limit':'does not prove source topology or equivalence'}
  return {'kind':f.kind,'geometry_valid':None,'limit':'legacy model validated; subject topology unsupported'}
 if op=='sources':
  from ctrltea.sources import source_warnings
  from unittest.mock import patch
  doc=LectureDocument.model_validate({'sections':d['document']['sections']})
  with patch('ctrltea.store.effective_pages',return_value=d['pages']):return source_warnings(doc,'offline-validation')
 if op=='pdf_math':
  from ctrltea.pdf_math import verify_pdf_math
  return verify_pdf_math(d['docx'],d['pdf'])
 raise ValueError('unsupported operation')
if __name__=='__main__':
 try:result={'status':'ok','data':main(json.load(sys.stdin))}
 except (ImportError,OSError) as e:result={'status':'unverified','error':str(e)}
 except Exception as e:result={'status':'error','error':str(e)[:3000],'exception':type(e).__name__}
 print(json.dumps(result,ensure_ascii=False))
