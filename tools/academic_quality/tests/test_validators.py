from pathlib import Path
import copy,json,os,sys,subprocess,zipfile
import pytest
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
from ctrltea_validators.core import validate,diagram,math_case,engine,attach_evidence,sha
F=P/'fixtures';APP=os.environ.get('AQ06_APP_ROOT') or (P.parents[1] if (P.parents[1]/'backend/ctrltea').exists() else None)
def get(report,id):return next(c for c in report['checks'] if c['check_id']==id)
def test_math_exact_good_and_bad():
 r=validate(F/'math.json',app_root=APP)
 expected={'row-good':'pass','row-bad':'fail','feedback--':'pass','feedback-+':'pass','feedback-wrong':'fail','fraction':'pass','identity':'pass'}
 for k,s in expected.items():assert get(r,'math.'+k)['status']==s
@pytest.mark.parametrize('name,status',[('control-good.json','pass'),('control-bad.json','fail'),('control-no-sign.json','fail'),('legacy.json','pass')])
def test_existing_figure_models(name,status):assert get(validate(F/name,app_root=APP),'figure.structure')['status']==status
@pytest.mark.parametrize('n,provenance,expect',[(6,'generated','pass'),(7,'generated','fail'),(9,'generated','fail'),(11,'source_crop','not_applicable'),(7,'unknown','unverified')])
def test_cross_subject_raster(n,provenance,expect):
 r=validate(F/f'case{n:02}.png',meta={'provenance':provenance});assert expect in [c['status'] for c in r['checks']]
@pytest.mark.parametrize('body,expected',[
 ('<path d="M10 10 H90" stroke="black"/>','pass'),
 ('<g style="stroke:red"><path d="M10 10 H90"/></g>','fail'),
 ('<style>path {stroke:blue}</style><path d="M10 10 H90"/>','fail'),
 ('<rect width="100" height="100" fill="white"/><path d="M10 10 H90" stroke="black"/>','fail'),
 ('<defs><marker id="a" markerWidth="10" markerHeight="10" refX="5" refY="5"><path d="M0 0L10 5L0 10Z" fill="red"/></marker></defs><path d="M10 50H80" stroke="black" marker-end="url(#a)"/>','fail'),
 ('<filter id="f"/>','unverified'),
 ('<g opacity="0"><rect width="50" height="50" fill="red"/></g><path d="M10 10H90" stroke="black"/>','pass')])
def test_svg_semantics(body,expected):
 s=f'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">{body}</svg>'
 statuses=[v[1] for v in diagram(s.encode(),'svg','generated')];assert expected in statuses
@pytest.mark.parametrize('bad',['<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///etc/passwd"/></svg>','<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg/>','<svg><style>@import "https://example.com";</style></svg>'])
def test_external_svg_rejected(bad):
 with pytest.raises(ValueError):diagram(bad.encode(),'svg','generated')
def test_missing_dependency_not_pass():
 assert engine('row',app_root='/does-not-exist',case={})['status']=='unverified'
def test_docx_native_tables_and_math():
 meta=json.loads((F/'code-meta.json').read_text());r=validate(F/'code-kept.docx',meta=meta,app_root=APP)
 assert get(r,'docx.omml')['status']=='pass';assert get(r,'docx.table.0.expected')['status']=='pass'
def test_missing_omml():assert get(validate(F/'missing-math.docx',meta={'expected_omml':1}),'docx.omml')['status']=='fail'
def test_bad_table_value():
 r=validate(F/'code-kept.docx',meta={'tables':{'0':[['x','value'],['x','999']]}});assert get(r,'docx.table.0.expected')['status']=='fail'
def test_malformed_input(tmp_path):
 p=tmp_path/'bad.pdf';p.write_bytes(b'%PDF-broken');assert validate(p)['summary']['fail']
def test_invalid_selection():assert get(validate(F/'case06.png',checks=['nonsense']),'selection.nonsense')['status']=='unverified'
def test_input_unchanged():
 p=F/'code-kept.docx';before=sha(p);validate(p);assert sha(p)==before
def test_aq05_review_semantics_and_extension(tmp_path):
 review=json.loads((P/'vendor/ctrltea-lecture-reviewer/examples/verified.json').read_text());p=tmp_path/'report.json';p.write_text(json.dumps(review))
 assert get(validate(p),'qa.review')['status']=='pass'
 v=validate(F/'reviewed-lecture.md')
 original=copy.deepcopy(review);out=attach_evidence(review,v);assert review==original and out['parent_review']==original;assert not out['candidate_review']['human_events'];assert out['candidate_review']['assessment']['overall_score']==original['assessment']['overall_score'];assert out['candidate_review']['assessment']['critical_finding_ids']
def test_extension_rejects_other_snapshot():
 review=json.loads((P/'vendor/ctrltea-lecture-reviewer/examples/verified.json').read_text())
 v=validate(F/'case06.png')
 with pytest.raises(ValueError):attach_evidence(review,v)
def test_score_baseline():
 d=json.loads((P/'vendor/ctrltea-lecture-reviewer/references/scoring-input.json').read_text());r=engine('score',data=d);assert abs(r['data']['overall_score']-84.5588235294)<1e-6
def test_qa05_wrong_total(tmp_path):
 r=json.loads((P/'vendor/ctrltea-lecture-reviewer/examples/verified.json').read_text());r['assessment']['overall_score']=100;p=tmp_path/'r.json';p.write_text(json.dumps(r));assert get(validate(p),'qa.review')['status']=='fail'
def test_source_file_hash_and_excerpt(tmp_path):
 s=tmp_path/'source.txt';s.write_text('exact source')
 r=validate(F/'case06.png',meta={'sources':[{'id':'S','path':str(s),'exact_excerpt':'wrong'}]});assert get(r,'source.S')['status']=='fail'
def test_vhdl_not_claimed_compiled(tmp_path):
 p=tmp_path/'example.vhd';p.write_text('entity demo is end demo; architecture rtl of demo is begin end rtl;');r=validate(p);assert get(r,'vhdl.compilation')['status']=='unverified'
def test_cli_machine_and_human_output(tmp_path):
 out=tmp_path/'report.json';proc=subprocess.run([sys.executable,str(P/'validate.py'),str(F/'case06.png'),'--output',str(out)],capture_output=True,text=True);assert proc.returncode==0;assert out.exists() and out.with_suffix('.json.md').exists()

def test_report_counts_and_snapshots():
 from ctrltea_validators.core import check_report
 r=validate(F/'case06.png');assert check_report(r);r['summary']['pass']+=1
 with pytest.raises(ValueError):check_report(r)

@pytest.mark.parametrize('value,expected,status',[('2','3','pass'),('2','4','fail')])
def test_substitution_not_identity(value,expected,status):
 s,r=math_case({'kind':'substitution','expression':{'numerator':['1','1'],'denominator':['1']},'value':value,'expected':expected},APP);assert s==status and 'not a general identity' in r['method']

def test_explicit_branch_reference_mismatch():
 d=json.loads((F/'control-good.json').read_text())['figure']['control'];d['edges'][0]['end']='other'
 assert get(validate(F/'control-good.json',meta={'expected_control':d},app_root=APP),'figure.source_mapping')['status']=='fail'

def test_source_adapter_offline(tmp_path):
 d=json.loads((F/'lecture.json').read_text());d['sections']=d['sections'][:1];d['sections'][0]['blocks']=d['sections'][0]['blocks'][:1];ref=d['sections'][0]['blocks'][0]['refs'][0];ref['quote']='expected';p=tmp_path/'lecture.json';p.write_text(json.dumps(d));pages=[{'source_id':ref['source_id'],'number':ref['page'],'raw':'expected','corrected':None,'excluded':False}]
 assert get(validate(p,meta={'source_pages':pages},app_root=APP),'lecture.source_warnings')['status']=='pass'
 pages[0]['raw']='wrong';assert get(validate(p,meta={'source_pages':pages},app_root=APP),'lecture.source_warnings')['status']=='warning'

@pytest.mark.parametrize('latex,status',[(r'\frac{1}{2}','pass'),(r'\frac{','fail')])
def test_math_conversion_is_separate(latex,status,tmp_path):
 d=json.loads((F/'lecture.json').read_text());d['sections']=d['sections'][:1];b=next(b for b in d['sections'][0]['blocks'] if b['kind']=='equation');b['latex']=latex;d['sections'][0]['blocks']=[b];p=tmp_path/'math.json';p.write_text(json.dumps(d));assert get(validate(p,app_root=APP),'lecture.math_render')['status']==status

def test_external_svg_doctype_is_not_fetched():
 svg=b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd"><svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><path d="M10 10H90" stroke="black"/></svg>'
 assert all(x[1]=='pass' for x in diagram(svg,'svg','generated'))
