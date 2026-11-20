#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from ctrltea_validators import validate,attach_evidence
def main():
 p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--mode',default='auto');p.add_argument('--meta');p.add_argument('--checks',help='comma-separated groups');p.add_argument('--app-root');p.add_argument('--preview');p.add_argument('--output',required=True);p.add_argument('--review',help='AQ05 report to link in a separate envelope');a=p.parse_args()
 output=Path(a.output)
 if output.resolve()==Path(a.input).resolve() or output.exists():p.error('output must be a new path')
 r=validate(a.input,mode=a.mode,meta=json.loads(Path(a.meta).read_text()) if a.meta else {},checks=a.checks.split(',') if a.checks else None,app_root=a.app_root,preview=a.preview)
 if a.review:r=attach_evidence(json.loads(Path(a.review).read_text()),r)
 output.parent.mkdir(parents=True,exist_ok=True)
 with output.open('x') as f:json.dump(r,f,ensure_ascii=False,indent=2)
 base=r.get('candidate_review',{}).get('assessment',{}).get('extensions',{}).get('aq06',{}).get('validation',r)
 summary=output.with_suffix(output.suffix+'.md')
 with summary.open('x') as f:
  f.write('# نتيجة التحقق البرمجي\n\n'+str(base['summary'])+'\n\n| الفحص | الحالة | الحدود |\n|---|---|---|\n')
  for c in base['checks']:f.write('| '+c['check_id']+' | '+c['status']+' | '+c['limits'].replace('|','/')+' |\n')
 print(json.dumps(base['summary']));return 1 if base['summary']['fail'] else 0
if __name__=='__main__':raise SystemExit(main())
