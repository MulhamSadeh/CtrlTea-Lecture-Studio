"""Compute provisional rubric scores from explicit units; does not judge evidence."""
import json,sys
WEIGHTS={'scientific':30,'completeness':20,'math':20,'diagrams_tables':15,'writing':10,'organization':5}
def score(data):
    assert set(data['dimensions'])==set(WEIGHTS),'six criteria required'
    scores={};denom=0
    for k,d in data['dimensions'].items():
        s=d['status'];assert s in ('verified','partially_verified','unverified','not_applicable')
        assert isinstance(d['reason'],str) and d['reason'].strip()
        if s=='not_applicable':assert not d['ratings'];scores[k]=None;continue
        denom+=WEIGHTS[k]
        if s!='verified':scores[k]=None;continue
        rs=d['ratings'];assert rs and all(type(x)==int and 0<=x<=4 for x in rs)
        scores[k]=25*sum(rs)/len(rs)
    eligible=denom and data['complete_coverage'] is True and data['source_fidelity_verified'] is True and all(d['status'] in ('verified','not_applicable') for d in data['dimensions'].values())
    return {'dimension_scores':scores,'effective_weights':{k:0 if d['status']=='not_applicable' else WEIGHTS[k]*100/denom for k,d in data['dimensions'].items()},'overall_score':sum(WEIGHTS[k]*v for k,v in scores.items() if v is not None)/denom if eligible else None,'note':'حساب فقط؛ الأدلة والحرجة والتفويض لا تتحقق بهذه الأداة'}
if __name__=='__main__':print(json.dumps(score(json.load(sys.stdin)),ensure_ascii=False,indent=2))
