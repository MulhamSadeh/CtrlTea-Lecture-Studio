"""Local report consistency, scoring and append-only decision records. Not RBAC."""
import argparse, copy, hashlib, json
from pathlib import Path
from jsonschema import Draft202012Validator
WEIGHTS={'scientific':30,'completeness':20,'math':20,'diagrams_tables':15,'writing':10,'organization':5}
SCHEMA=Path(__file__).resolve().parents[1]/'references/report.schema.json'
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def near(a,b):return a is not None and abs(a-b)<0.000001
def require(ok,msg):
    if not ok:raise ValueError(msg)
def validate(report):
    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(report)
    a=report['assessment'];require(digest(a)==report['assessment_sha256'],'assessment changed')
    doc=a['document']; sources=a['sources']; ev=a['evidence']; fs=a['findings']; ds=a['dimensions']; cov=a['coverage']
    artifacts=[doc['id']]+[s['id'] for s in sources]
    require(len(set(artifacts))==len(artifacts),'duplicate artifact')
    eids=[e['id'] for e in ev];require(len(eids)==len(set(eids)),'duplicate evidence')
    emap={e['id']:e for e in ev}
    for e in ev:require(e['artifact_id'] in artifacts,'unknown evidence artifact')
    def refs(ids):require(all(x in emap for x in ids),'unknown evidence reference')
    require(len(ds)==6 and {d['criterion'] for d in ds}==set(WEIGHTS),'six unique criteria required')
    denom=sum(d['weight'] for d in ds if d['status']!='not_applicable')
    for d in ds:
        require(d['weight']==WEIGHTS[d['criterion']],'incorrect rubric weight');refs(d['evidence_ids'])
        us=d['units']; require(len({u['id'] for u in us})==len(us),'duplicate unit')
        for u in us:
            refs(u['evidence_ids'])
            if u['status']=='verified':require(u['rating'] is not None and u['evidence_ids'],'verified unit needs rating and evidence')
            else:require(u['rating'] is None,'unknown unit must not be scored')
        if d['status']=='verified':
            require(us and all(u['status']=='verified' for u in us) and d['evidence_ids'],'verified dimension needs verified units and evidence')
            require(near(d['score'],25*sum(u['rating'] for u in us)/len(us)),'dimension score mismatch')
        else:require(d['score'] is None,'unverified or N/A dimension cannot have full score')
        if d['status']=='not_applicable':require(not us,'N/A must not contain units')
        expected=0 if d['status']=='not_applicable' else d['weight']*100/denom
        require(near(d['effective_weight'],expected),'effective weight mismatch')
    if not sources or cov['source_fidelity']!='verified':
        require(next(d for d in ds if d['criterion']=='completeness')['status'] in ('unverified','partially_verified'),'missing source fidelity cannot become N/A or verified')
    if cov['status']=='complete':require(not cov['unreviewed_locations'],'complete coverage has unread locations')
    eligible=bool(denom) and cov['status']=='complete' and cov['source_fidelity']=='verified' and bool(sources) and all(d['status'] in ('verified','not_applicable') for d in ds)
    if eligible:
        expected=sum(d['weight']*d['score'] for d in ds if d['status']=='verified')/denom
        require(near(a['overall_score'],expected) and a['withheld_reason'] is None,'overall score mismatch')
    else:require(a['overall_score'] is None and a['withheld_reason'],'overall score must be withheld')
    ids=[f['id'] for f in fs];require(len(ids)==len(set(ids)),'duplicate finding')
    critical={f['id'] for f in fs if f['critical_status']!='none'}
    require(len(a['critical_finding_ids'])==len(set(a['critical_finding_ids'])) and set(a['critical_finding_ids'])==critical,'critical list mismatch')
    for f in fs:
        refs(f['evidence_ids']);refs(f['source_evidence_ids'])
        require(f['evidence_ids'],'finding requires observed evidence, including limitations')
        require(all(emap[i]['artifact_id']!=doc['id'] for i in f['source_evidence_ids']),'source evidence must identify source artifact')
        if f['severity']=='critical':require(f['id'] in critical,'critical severity requires critical status')
        if f['critical_status']=='confirmed':require(f['verification_status']=='verified','confirmed critical requires verified evidence')
    project(report)
    return True
def project(r):
    a=r['assessment'];fs={f['id']:f for f in a['findings']};states={i:'open' for i in fs};supp={};events=set();approval=None
    critical=set(a['critical_finding_ids']);docsha=a['document']['sha256']
    for e in r['human_events']:
        require(e['event_id'] not in events,'duplicate event');events.add(e['event_id'])
        require(docsha is not None and e['snapshot_sha256']==docsha,'event bound to wrong or unknown snapshot')
        action=e['action'];targets=e['finding_ids'];require(len(targets)==len(set(targets)) and all(i in fs for i in targets),'bad event targets')
        if action=='verify_fix':
            require(e['actor_kind']=='reviewer' and e['verification'] is not None and e['scope']=='finding','verification needs reviewer evidence')
            require(e['verification']['new_document_sha256']!=docsha,'correction must identify new snapshot')
            require(targets and all(states[i]=='pending_verification' for i in targets),'fix must precede verification')
            for i in targets:states[i]='fixed_in_new_snapshot' if e['verification']['outcome']=='resolved' else 'open'
            continue
        require(e['actor_kind'] in ('human','simulated_human') and e['verification'] is None,'human instruction required')
        if action=='approve_with_exceptions':
            require(e['scope']=='snapshot','approval scope must be snapshot')
            # All findings still belong to the old snapshot, even if a correction was verified elsewhere.
            require(set(targets)==set(fs),'approval must enumerate every unresolved finding in reviewed snapshot')
            require(all(i in e['critical_reasons'] for i in critical),'critical override requires individual reasons')
            approval={'label':'Approved with Exceptions','event_id':e['event_id'],'actor_kind':e['actor_kind'],'snapshot_sha256':docsha,'exceptions':targets}
            continue
        require(targets,'finding action needs targets')
        if action in ('ignore_lecture','ignore_rule'):
            require(e['scope']==('lecture' if action=='ignore_lecture' else 'rule') and e['rule_id'] and e['rule_version'],'explicit rule and scoped suppression required')
            require(all(fs[i]['rule_id']==e['rule_id'] and fs[i]['rule_version']==e['rule_version'] for i in targets),'suppression rule mismatch')
            for i in targets:supp[i]={'rule_id':e['rule_id'],'rule_version':e['rule_version'],'scope':e['scope'],'event_id':e['event_id']}
        elif action=='restore':
            require(e['scope'] in ('finding','rule','lecture'),'invalid restore scope')
            require(all(states[i] in ('ignored','deferred') for i in targets),'restore requires ignored/deferred')
            for i in targets:supp.pop(i,None)
        else:require(e['scope']=='finding','finding scope required')
        new={'fix':'pending_verification','ignore':'ignored','ignore_lecture':'ignored','ignore_rule':'ignored','defer':'deferred','restore':'open'}[action]
        for i in targets:states[i]=new
    stale=r['current_document_sha256']!=docsha or docsha is None
    return {'finding_states':states,'active_suppressions':supp,'approval_history_latest':approval,'current_approval':None if stale else approval,'document_status':'Needs review' if stale or not approval else 'Approved with Exceptions','critical_review_required':bool(critical),'critical_finding_ids':sorted(critical),'assessment_score_unchanged':a['overall_score']}
def append(r,event):
    validate(r);out=copy.deepcopy(r);out['human_events'].append(event);validate(out);return out
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['validate','status','append']);p.add_argument('report');p.add_argument('--event');p.add_argument('--output');args=p.parse_args()
    r=json.loads(Path(args.report).read_text());validate(r)
    if args.command=='append':
        if not args.event or not args.output:p.error('append requires --event and --output; input is never overwritten')
        require(Path(args.output).resolve()!=Path(args.report).resolve(),'do not overwrite original report')
        r=append(r,json.loads(Path(args.event).read_text()))
        with Path(args.output).open('x') as f:json.dump(r,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'valid':True,**project(r)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
