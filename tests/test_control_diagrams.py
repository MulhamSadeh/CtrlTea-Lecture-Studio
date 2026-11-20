"""AQ-04: structural failures, source sequence, topology-derived exact checks and export."""
import copy
import json
from fractions import Fraction as Q
from pathlib import Path
from io import BytesIO
import zipfile
import pytest
from PIL import Image
from lxml import etree
from ctrltea.models import Figure, Block, LectureDocument
from ctrltea import figures, sources, authoring, store
from ctrltea.exporter import build_docx

CASES=json.loads((Path(__file__).parent/'fixtures/aq04_control_sequence.json').read_text())


def graph_output(figure,s):
    """Solve all node signals from actual edges by rational Gaussian elimination.

    A closed whitelist maps the *rendered* block labels to independent arithmetic.
    This is a finite exact-sample test, not a general symbolic equivalence claim.
    """
    gain={r'\frac{4}{s}':4/s,r'\frac{2}{s}':2/s,'3':Q(3),r'\frac{s+4}{s}':(s+4)/s,r'\frac{s}{s+4}':s/(s+4),r'\frac{2}{s+4}':2/(s+4),r'\frac{2}{s+10}':2/(s+10),r'\frac{2(s+4)}{s(s+10)}':2*(s+4)/(s*(s+10))}
    ns=figure['control']['nodes'];es=figure['control']['edges'];ids={n['id']:i for i,n in enumerate(ns)};m=[]
    for n in ns:
        row=[Q(0)]*(len(ns)+1);row[ids[n['id']]]=Q(1)
        if n['kind']=='input':row[-1]=Q(1)
        else:
            for e in es:
                if e['end']==n['id']:
                    g=gain[n['math']] if n['kind']=='block' else Q(-1 if e.get('sign')=='-' else 1)
                    row[ids[e['start']]]-=g
        m.append(row)
    for i in range(len(ns)):
        pivot=next(j for j in range(i,len(ns)) if m[j][i]);m[i],m[pivot]=m[pivot],m[i]
        div=m[i][i];m[i]=[v/div for v in m[i]]
        for j in range(len(ns)):
            if i!=j:
                coeff=m[j][i];m[j]=[a-coeff*b for a,b in zip(m[j],m[i])]
    return m[ids[next(n['id'] for n in ns if n['kind']=='output')]][-1]


@pytest.mark.parametrize('case',CASES,ids=[f'stage-{i+1}' for i in range(len(CASES))])
def test_source_sequence_topology_and_vector(case):
    f=Figure.model_validate(case['figure'])
    from ctrltea.control_diagrams import diagram
    svg=etree.fromstring(diagram(f.control).encode())
    assert len(svg.xpath('//*[@data-node]'))==len(f.control.nodes)
    assert len(svg.xpath('//*[@data-sign]'))==sum(e.end in {n.id for n in f.control.nodes if n.kind=='sum'} for e in f.control.edges)
    assert not svg.xpath('//*[local-name()="image"]')
    for s in map(Q,['1/2','1','2','5','11']):assert graph_output(case['figure'],s)==2*(s+4)/(s*(s+10))


@pytest.mark.parametrize('fault',['node','sign_missing','sign_extra','port','degree','diagonal','reversed','crossing','overlap','bad_math','duplicate','isolated'])
def test_rejects_ambiguous_or_invalid_graph(fault):
    f=copy.deepcopy(CASES[0]['figure']);g=f['control'];ns=g['nodes'];es=g['edges']
    if fault=='node':es[0]['end']='missing'
    elif fault=='sign_missing':es[1]['sign']=''
    elif fault=='sign_extra':es[0]['sign']='+'
    elif fault=='port':es[1]['end_port']='unknown'
    elif fault=='degree':es.pop()
    elif fault=='diagonal':es[0]['bends']=[dict(x=90,y=150)]
    elif fault=='reversed':es[0]['start_port']='left'
    elif fault=='crossing':es[8]['bends']=[dict(x=650,y=80),dict(x=700,y=80),dict(x=700,y=230),dict(x=240,y=230),dict(x=240,y=80)]
    elif fault=='overlap':ns[3]['x']=ns[4]['x']
    elif fault=='bad_math':ns[0]['math']=r'\unsupported{x}'
    elif fault=='duplicate':ns[1]['id']=ns[0]['id']
    elif fault=='isolated':ns.append(dict(id='alone',kind='block',x=100,y=600,math='1'))
    with pytest.raises(ValueError):Figure.model_validate(f)


@pytest.mark.parametrize('sign',['-','+'])
def test_feedback_sign_changes_transfer(sign):
    f=copy.deepcopy(CASES[6]['figure']);f['control']['edges'][-1]['sign']=sign
    parsed=Figure.model_validate(f)
    from ctrltea.control_diagrams import diagram
    assert f'data-sign="{sign}"' in diagram(parsed.control)
    for s in map(Q,['1','5','11']):
        g=2/(s+4);h=3;p=(s+4)/s
        assert graph_output(f,s)==p*g/(1+(1 if sign=='-' else -1)*g*h)
    if sign=='+':assert graph_output(f,Q(5))!=graph_output(CASES[6]['figure'],Q(5))


def test_transparent_png_and_docx_vector(client,tmp_path):
    b=Block(kind='figure',figure=CASES[0]['figure'],refs=[dict(source_id='test',page=2)])
    svg,png=figures.render(b,'olive');im=Image.open(png).convert('RGBA')
    assert im.getchannel('A').getextrema()==(0,255)
    assert im.getpixel((0,0))[3]==0
    assert all(r==g==bl==0 for r,g,bl,a in im.getdata() if a)
    doc=LectureDocument(title='اختبار الرسوم',sections=[dict(title='الرسم',blocks=[b])])
    path=tmp_path/'control.docx';build_docx(doc,path)
    with zipfile.ZipFile(path) as z:
        assert any(n.startswith('word/media/') and n.endswith('.svg') for n in z.namelist())
        assert any(n.startswith('word/media/') and n.endswith('.png') for n in z.namelist())
        assert b'svgBlip' in z.read('word/document.xml')


def test_partial_figure_edit_preserves_manual_work_and_conflicts(client,lecture):
    _,l=lecture;lid=l['id'];url=f'/api/lectures/{lid}'
    source=sources.register(lid,'approved.txt','مثال معتمد'.encode(),role='primary');sources.extract(source['id'])
    old=store.lecture(lid);doc=old['document']
    doc['sections']=[dict(id='drawing',title='الرسم',palette='cinnamon',complete=False,blocks=[dict(id='figure1',kind='figure',figure=CASES[-1]['figure'],refs=[dict(source_id=source['id'],page=1)]),dict(id='manual',kind='explanation',text='تحرير يدوي محفوظ',refs=[])]),dict(id='other',title='قسم آخر',palette='cinnamon',complete=False,blocks=[dict(kind='explanation',text='لا تغيّر هذا النص',refs=[])])]
    r=client.put(url,json={'document':doc,'revision':old['revision']});r.raise_for_status()
    def payload():
        _,raw=authoring.packet(lid,['drawing'])
        with zipfile.ZipFile(BytesIO(raw)) as z:
            current=json.loads(z.read('current.json'));manifest=json.loads(z.read('manifest.json'))
        section=copy.deepcopy(current['sections'][0]);section['blocks'][0]['figure']['control']['nodes'][2]['math']=r'\frac{2s+8}{s^2+10s}'
        return {'run_id':manifest['run_id'],'sections':[section]}
    proposal=payload();before=store.lecture(lid)
    doc=copy.deepcopy(before['document']);doc['sections'][0]['blocks'][1]['text']='تعديل متزامن محفوظ'
    r=client.put(url,json={'document':doc,'revision':before['revision']});r.raise_for_status()
    p=client.post(url+'/authoring/preview',json={'result':proposal});p.raise_for_status();assert p.json()['conflicts']
    r=client.post(url+'/authoring/import',json={'result':proposal,'revision':p.json()['revision']});assert r.status_code==409
    proposal=payload();before=store.lecture(lid)['document'];p=client.post(url+'/authoring/preview',json={'result':proposal});p.raise_for_status();assert not p.json()['conflicts']
    r=client.post(url+'/authoring/import',json={'result':proposal,'revision':p.json()['revision']});r.raise_for_status()
    after=r.json()['document'];expected=copy.deepcopy(before);expected['sections'][0]['blocks'][0]['figure']['control']['nodes'][2]['math']=r'\frac{2s+8}{s^2+10s}'
    assert after==expected
    image=client.post('/api/figures/preview',json={'block':after['sections'][0]['blocks'][0],'palette':'cinnamon'})
    image.raise_for_status()
    assert b'data-node' in image.content


@pytest.mark.parametrize('windows',[False,True])
def test_arrowheads_have_ink_in_both_raster_engines(monkeypatch,windows):
    from ctrltea import runtime
    from ctrltea.control_diagrams import diagram
    monkeypatch.setattr(runtime,'IS_WINDOWS',windows)
    spec=Figure.model_validate(CASES[0]['figure']).control
    svg=diagram(spec).encode();root=etree.fromstring(svg)
    assert len(root.xpath('//*[@data-arrow]'))==len(spec.edges)
    assert not root.xpath('//*[local-name()="marker"]')
    im=Image.open(BytesIO(runtime.svg_png(svg,output_width=1800))).convert('RGBA')
    xmin,ymin,width,height=map(float,root.get('viewBox').split());scale=1800/width
    nodes={n.id:n for n in spec.nodes}
    for e in spec.edges:
        x,y=nodes[e.end].port(e.end_port)
        px,py=(e.bends[-1].x,e.bends[-1].y) if e.bends else nodes[e.start].port(e.start_port)
        length=((x-px)**2+(y-py)**2)**.5;ux,uy=(x-px)/length,(y-py)/length
        # Offset beyond the thin shaft, inside the triangle, away from the junction dot.
        sx,sy=x-5.5*ux-2*uy,y-5.5*uy+2*ux
        assert im.getpixel((round((sx-xmin)*scale),round((sy-ymin)*scale)))[3]>100
