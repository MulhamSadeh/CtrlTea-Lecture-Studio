from pathlib import Path
import base64,copy,hashlib,io,json,os,re,subprocess,sys,tempfile,zipfile
from fractions import Fraction as F
VERSION='AQ06-1.0.0'
STATUSES=('pass','fail','warning','unverified','not_applicable')
LIMIT='This check does not prove complete scientific correctness.'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def limits():
 try:
  import resource
  resource.setrlimit(resource.RLIMIT_CPU,(35,35));resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(100*1024**2,100*1024**2))
 except ImportError:pass
def engine(op,app_root=None,**kw):
 with tempfile.TemporaryDirectory(prefix='ctrltea-check-') as td:
  env=os.environ.copy();env.update(CTRLTEA_DATA_DIR=td,MPLCONFIGDIR=td,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
  env['PYTHONPATH']=os.pathsep.join(str(Path(p).resolve()) for p in os.environ.get('PYTHONPATH','').split(os.pathsep) if p)
  request={'op':op,'app_root':str(Path(app_root).resolve()) if app_root else None,**kw}
  try:
   r=subprocess.run([sys.executable,str(Path(__file__).with_name('worker.py'))],input=json.dumps(request),text=True,capture_output=True,timeout=45,env=env,cwd=td,preexec_fn=limits if os.name=='posix' else None)
   if r.returncode:return {'status':'unverified','error':'worker stopped or dependency failed','diagnostic':r.stderr[-1500:]}
   return json.loads(r.stdout)
  except (subprocess.TimeoutExpired,json.JSONDecodeError,OSError) as e:return {'status':'unverified','error':str(e)}
def xml(data):
 from lxml import etree
 if b'<!ENTITY' in data.upper() or re.search(br'<!DOCTYPE[^>]*\[',data,re.I):raise ValueError('internal DTD/entities unsupported')
 return etree.fromstring(data,etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,huge_tree=False))
def raster(data):
 from PIL import Image
 im=Image.open(io.BytesIO(data))
 if im.width*im.height>20_000_000:raise ValueError('image too large')
 im.load()
 alpha=('A' in im.getbands() or 'transparency' in im.info)
 rgba=im.convert('RGBA');visible=nonblack=white=transparent=0
 for r,g,b,a in rgba.getdata():
  if a==0:transparent+=1;continue
  visible+=1;nonblack+=int((r,g,b)!=(0,0,0));white+=int((r,g,b)==(255,255,255))
 border=[rgba.getpixel((x,y))[3] for x in range(im.width) for y in (0,im.height-1)]+[rgba.getpixel((x,y))[3] for y in range(im.height) for x in (0,im.width-1)]
 return {'width':im.width,'height':im.height,'has_alpha':alpha,'visible_pixels':visible,'nonblack_visible_pixels':nonblack,'white_visible_pixels':white,'transparent_pixels':transparent,'border_transparent_fraction':sum(a==0 for a in border)/len(border),'tolerance':0}
def diagram(data,kind,provenance):
 if provenance in ('source_crop','photograph','unrelated'):
  return [('style.scope','not_applicable',{'provenance':provenance},'source classification supplied by caller, not inferred; scientific accuracy unchecked')]
 if provenance not in ('generated','reconstructed'):
  return [('style.scope','unverified',{'provenance':provenance},'human provenance classification required')]
 notes=[]
 if kind=='svg':
  root=xml(data);text=data.decode();unsupported=[]
  if root.tag.split('}')[-1]!='svg':raise ValueError('not an SVG root')
  for e in root.iter():
   name=e.tag.split('}')[-1] if isinstance(e.tag,str) else ''
   if name in ('script','foreignObject','filter','linearGradient','radialGradient','animate','animateTransform','set'):unsupported.append(name)
   for k,v in e.attrib.items():
    if k.lower().startswith('on'):raise ValueError('SVG event handler forbidden')
    if k.endswith('href') and not(v.startswith('#') or v.startswith('data:image/png;base64,') or v.startswith('data:image/jpeg;base64,')):raise ValueError('external SVG reference forbidden')
  if '@import' in text.lower() or '<?xml-stylesheet' in text.lower():raise ValueError('external CSS forbidden')
  for target in re.findall(r'url\s*\((.*?)\)',text,re.I):
   if not target.strip(' \t\n\"\'').startswith('#'):raise ValueError('external CSS URL forbidden')
  if unsupported:return [('style.svg_features','unverified',{'unsupported':sorted(set(unsupported))},'renderer differences for filters, gradients, animation are not certified')]
  rendered=engine('svg',svg=text)
  if rendered['status']!='ok':return [('style.render','unverified',rendered,'CairoSVG unavailable or failed')]
  data=base64.b64decode(rendered['data']['png']);notes.append(('style.svg_render','pass',{'inspection':'XML references, inherited attributes/CSS, paths/use/markers via CairoSVG rasterization'},'one renderer at 1000×1000; small/subpixel elements may be missed; not cross-renderer certification'))
 r=raster(data)
 notes.append(('style.black','fail' if r['nonblack_visible_pixels'] else ('pass' if r['visible_pixels'] else 'warning'),r,'exact RGB=0 for alpha>0; transparent RGB ignored; empty image is not a valid scientific diagram'))
 transparent='fail' if not r['has_alpha'] or not r['transparent_pixels'] or r['white_visible_pixels']>r['width']*r['height']*.5 else ('pass' if r['border_transparent_fraction']>=0.95 else 'unverified')
 notes.append(('style.transparent',transparent,r,'checks exterior border/background evidence; internal opaque semantic regions require human inspection'))
 return notes
def trim(p):
 p=list(map(F,p));assert p and len(p)<=64
 while len(p)>1 and p[-1]==0:p.pop()
 return p
def mul(a,b):
 out=[F(0)]*(len(a)+len(b)-1)
 for i,x in enumerate(a):
  for j,y in enumerate(b):out[i+j]+=x*y
 return trim(out)
def add(a,b,sign=1):return trim([(a[i] if i<len(a) else 0)+sign*(b[i] if i<len(b) else 0) for i in range(max(len(a),len(b)))])
def rational_function(v):
 n,d=trim(v['numerator']),trim(v['denominator']);assert any(d),'zero denominator';return n,d
def math_case(c,app):
 kind=c['kind']
 if kind=='row':
  r=engine('row',app,case=c);return ('unverified',r) if r['status']=='unverified' else ('fail',r) if r['status']=='error' else ('pass' if r['data']['ok'] else 'fail',r['data'])
 if kind=='fraction':
  actual=F(c['value']);expected=F(c['expected']);return ('pass' if actual==expected else 'fail',{'actual':str(actual),'expected':str(expected),'method':'exact rational arithmetic'})
 if kind=='substitution':
  n,d=rational_function(c['expression']);x=F(c['value']);num=sum(v*x**i for i,v in enumerate(n));den=sum(v*x**i for i,v in enumerate(d));assert den,'undefined at supplied value'
  actual=num/den;expected=F(c['expected']);return ('pass' if actual==expected else 'fail',{'actual':str(actual),'expected':str(expected),'at':str(x),'method':'exact rational substitution at one point; not a general identity proof'})
 if kind in ('identity','feedback'):
  if kind=='identity':n,d=rational_function(c['left'])
  else:
   gn,gd=rational_function(c['forward']);hn,hd=rational_function(c['feedback']);assert c['sign'] in ('+','-')
   n=mul(gn,hd);d=add(mul(gd,hd),mul(gn,hn),1 if c['sign']=='-' else -1);assert any(d),'singular feedback denominator'
  en,ed=rational_function(c['expected']);eq=mul(n,ed)==mul(en,d)
  return ('pass' if eq else 'fail',{'numerator':list(map(str,n)),'denominator':list(map(str,d)),'expected':c['expected'],'method':'exact polynomial cross multiplication, ascending coefficients','domain':'original supplied denominators and closed-loop denominator must be nonzero; cancellations do not certify internal equivalence'})
 return 'unverified',{'unsupported':kind}
class Run:
 def __init__(self,path,checks):
  self.path=Path(path);self.selected=set(checks or []);self.rows=[];self.hash=sha(path)
 def wants(self,name):return not self.selected or name in self.selected
 def add(self,id,status,actual,expected='',limits_=LIMIT,location=None):
  assert status in STATUSES
  self.rows.append({'check_id':id,'implementation':VERSION,'snapshot_sha256':self.hash,'location':location or self.path.name,'status':status,'expected':expected,'actual':actual,'evidence':actual,'limits':limits_,'reproduce':'run validate.py on the same input with the same sidecar and options'})
 def call(self,id,op,app,**kw):
  r=engine(op,app,**kw);s='unverified' if r['status']=='unverified' else ('fail' if r['status']=='error' or r.get('data',{}).get('ok') is False else 'pass');self.add(id,s,r);return r
def docx_checks(r,data,meta,app,preview):
 from lxml import etree
 z=zipfile.ZipFile(io.BytesIO(data));infos=z.infolist()
 if len(infos)>5000 or sum(i.file_size for i in infos)>100_000_000:raise ValueError('DOCX package size limit')
 root=xml(z.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math','a':'http://schemas.openxmlformats.org/drawingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
 maths=root.findall('.//m:oMath',ns);tables=root.findall('.//w:tbl',ns)
 count=len(maths);expected=meta.get('expected_omml')
 r.add('docx.omml','pass' if expected is None or count==expected else 'fail',{'count':count,'empty':sum(not ''.join(m.itertext()).strip() for m in maths)},f'expected count {expected}' if expected is not None else 'inventory only; no expected count',limits_='XML presence is not scientific correctness or visibility')
 if any(not ''.join(m.itertext()).strip() for m in maths):r.add('docx.empty_math','fail',{'empty_equations':True})
 td=[]
 for i,t in enumerate(tables):
  rows=t.findall('w:tr',ns);widths=[];merges=False
  for row in rows:
   width=0
   for cell in row.findall('w:tc',ns):
    span=cell.find('w:tcPr/w:gridSpan',ns);width+=int(span.get('{'+ns['w']+'}val')) if span is not None else 1
    merges |= cell.find('w:tcPr/w:vMerge',ns) is not None
   widths.append(width)
  td.append({'table':i,'rows':len(rows),'column_spans':widths,'vertical_merges':merges})
  if widths and len(set(widths))>1:r.add(f'docx.table.{i}.width','warning',td[-1],limits_='omitted grid columns or merges may explain widths; not an automatic scientific error')
  expect=meta.get('tables',{}).get(str(i))
  if expect:
   actual=[[''.join(c.itertext()) for c in row.findall('w:tc',ns)] for row in rows]
   # w:t only avoids XML attribute values, preserving source cell text.
   actual=[[''.join(c.xpath('.//w:t/text()',namespaces=ns)) for c in row.findall('w:tc',ns)] for row in rows]
   r.add(f'docx.table.{i}.expected','pass' if actual==expect else 'fail',actual,expected=expect)
 r.add('docx.tables','pass',td,'native editable table inventory; values checked only against explicit expectations')
 bookmarks=set(root.xpath('.//w:bookmarkStart/@w:name',namespaces=ns));anchors=root.xpath('.//w:hyperlink/@w:anchor',namespaces=ns);missing=[x for x in anchors if x not in bookmarks]
 r.add('docx.links','fail' if missing else 'pass',{'anchors':len(anchors),'missing':missing},'all internal hyperlink anchors resolve; field-code TOC updates not executed')
 empty=[];code=[];bidi=0
 for i,p in enumerate(root.findall('.//w:p',ns)):
  style=p.find('w:pPr/w:pStyle',ns);name=style.get('{'+ns['w']+'}val','') if style is not None else '';text=''.join(p.xpath('.//w:t/text()',namespaces=ns))
  if re.search('heading|عنوان',name,re.I) and not text.strip():empty.append(i)
  if re.search('code|source|program',name,re.I):code.append({'paragraph':i,'style':name,'keep_next':p.find('w:pPr/w:keepNext',ns) is not None,'keep_lines':p.find('w:pPr/w:keepLines',ns) is not None})
  bidi+=len(p.findall('w:pPr/w:bidi',ns))
 r.add('docx.headings','warning' if empty else 'pass',{'empty_heading_paragraphs':empty})
 r.add('docx.code_layout','warning' if any(not x['keep_lines'] for x in code) else 'unverified',{'code_paragraphs':code},limits_='style-based detection; actual splits require rendered PDF and explicit block boundaries')
 r.add('docx.direction','unverified',{'bidi_paragraphs':bidi},limits_='RTL/LTR counts do not establish correct mixed-script rendering')
 rels=xml(z.read('word/_rels/document.xml.rels'));missing=[]
 for e in rels:
  target=e.get('Target','')
  if e.get('TargetMode')=='External':continue
  import posixpath
  resolved=posixpath.normpath('word/'+target) if not target.startswith('/') else target[1:]
  if resolved not in z.namelist():missing.append(target)
 r.add('docx.relationships','fail' if missing else 'pass',{'missing':missing})
 relationship_map={e.get('Id'):e.get('Target') for e in rels if e.get('TargetMode')!='External'}
 from PIL import Image
 import posixpath
 for i,drawing in enumerate(root.findall('.//w:drawing',ns)):
  ext=drawing.find('.//wp:extent',ns);blip=drawing.find('.//a:blip',ns)
  if ext is None or blip is None:continue
  target=relationship_map.get(blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'))
  if not target:continue
  part=posixpath.normpath('word/'+target)
  if part not in z.namelist():continue
  if drawing.find('.//a:srcRect',ns) is not None:r.add(f'docx.aspect.{i}','unverified','explicit crop transform');continue
  try:
   im=Image.open(io.BytesIO(z.read(part)));cx,cy=int(ext.get('cx')),int(ext.get('cy'))
   delta=abs((cx/cy)/(im.width/im.height)-1) if cy else 999
   r.add(f'docx.aspect.{i}','warning' if delta>.02 else 'pass',{'part':part,'relative_ratio_change':delta},'aspect ratio within 2% rounding tolerance',limits_='stretch warning only; deliberate stretch requires human judgment')
  except (OSError,ValueError,ZeroDivisionError):r.add(f'docx.aspect.{i}','unverified','unsupported dimensions or image type')
 for n in z.namelist():
  if n.startswith('word/media/') and n.lower().endswith(('.png','.svg','.jpg','.jpeg')):
   prov=meta.get('images',{}).get(n,'unknown')
   try:
    for cid,status,actual,lim in diagram(z.read(n),'svg' if n.endswith('.svg') else 'raster',prov):r.add('docx.'+n+'.'+cid,status,actual,limits_=lim,location=n)
   except Exception as e:r.add('docx.'+n+'.asset','unverified' if isinstance(e,ImportError) else 'fail',{'error':str(e)},location=n,limits_='asset could not be inspected; other assets continue')
 r.add('docx.image_layout','unverified',{'drawing_extents':len(root.findall('.//wp:extent',ns))},limits_='aspect ratios/cropping transforms not certified; inspect rendered preview')
 if preview:
  unsafe=[e.get('Target') for e in rels if e.get('TargetMode')=='External' and not e.get('Type','').endswith('/hyperlink')]
  if unsafe or any('vbaProject' in n or '/embeddings/' in n for n in z.namelist()):
   r.add('docx.preview','unverified',{'external_or_active_content':unsafe},limits_='render disabled for external resources/macros/embedded objects');return
  import shutil
  soffice=shutil.which('libreoffice') or shutil.which('soffice')
  if not soffice:r.add('docx.preview','unverified','LibreOffice unavailable');return
  preview=Path(preview);preview.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(prefix='ctrltea-render-') as td:
   env=os.environ.copy();profile=Path(td)/'profile';out=Path(td)/'out';out.mkdir()
   try:
    proc=subprocess.run([soffice,'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','pdf:writer_pdf_Export:{"UseTaggedPDF":{"type":"boolean","value":"true"},"UseLosslessCompression":{"type":"boolean","value":"true"},"ReduceImageResolution":{"type":"boolean","value":"false"}}','--outdir',str(out),str(r.path.resolve())],capture_output=True,timeout=60,env=env)
    pdf=out/(r.path.stem+'.pdf')
    if not pdf.exists():r.add('docx.preview','unverified',proc.stderr.decode(errors='replace')[:1500]);return
    dest=preview/(r.path.stem+'-'+r.hash[:12]+'.pdf')
    if dest.exists():raise ValueError('preview output exists; choose a new directory')
    shutil.copyfile(pdf,dest);r.add('docx.preview','pass',{'pdf':str(dest),'sha256':sha(dest)},limits_='LibreOffice conversion only; no Windows/Word certification')
    r.call('docx.pdf_math','pdf_math',app,docx=str(r.path.resolve()),pdf=str(dest.resolve()))
   except subprocess.TimeoutExpired:r.add('docx.preview','unverified','render timeout')
 else:r.add('docx.preview','unverified','preview not requested')
def pdf_checks(r,data,meta,app,preview):
 import fitz
 doc=fitz.open(stream=data,filetype='pdf');count=len(doc);expected=meta.get('expected_pages')
 r.add('pdf.pages','unverified' if expected is None else 'pass' if count==expected else 'fail',{'actual_pages':count},expected=expected or 'approved page count unavailable')
 texts=[];density=[]
 for i,p in enumerate(doc):
  text=p.get_text();texts.append(text);pix=p.get_pixmap(matrix=fitz.Matrix(.5,.5),colorspace=fitz.csGRAY,alpha=False);ink=sum(v<245 for v in pix.samples)/len(pix.samples);density.append(ink)
  if preview:
   out=Path(preview);out.mkdir(parents=True,exist_ok=True);target=out/f'{r.path.stem}-{r.hash[:8]}-page-{i+1}.png'
   if target.exists():raise ValueError('preview exists')
   p.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(target)
 r.add('pdf.trailing','warning' if density and density[-1]<0.005 else 'unverified',{'ink_fractions':density,'trailing_text_length':len(texts[-1].strip()) if texts else 0},limits_='low ink is a candidate only; headers/footers and scan noise affect result; no automatic layout approval')
 for b in meta.get('code_blocks',[]):
  starts=[i+1 for i,t in enumerate(texts) if b['start'] in t];ends=[i+1 for i,t in enumerate(texts) if b['end'] in t]
  s='unverified' if len(starts)!=1 or len(ends)!=1 else 'warning' if starts!=ends else 'pass'
  r.add('pdf.code.'+b['id'],s,{'start_pages':starts,'end_pages':ends},'explicit unique code markers on same page',limits_='a split is a presentation warning, not code syntax failure')
 if meta.get('docx'):
  r.call('pdf.math','pdf_math',app,docx=str(Path(meta['docx']).resolve()),pdf=str(r.path.resolve()))
 else:r.add('pdf.math','unverified','matching DOCX unavailable')
 r.add('pdf.visual_integrity','unverified',{'pages':count,'preview_requested':bool(preview)},limits_='missing arrows/labels, clipping, table completeness and readable scaling need source-grounded visual review; white PDF page does not establish intrinsic alpha')
def source_files(r,meta):
 for s in meta.get('sources',[]):
  p=Path(s['path'])
  if not p.is_file():r.add('source.'+s['id'],'fail',{'missing':str(p)});continue
  actual={'sha256':sha(p)};ok=not s.get('sha256') or s['sha256']==actual['sha256']
  if p.suffix.lower()=='.pdf':
   import fitz
   with fitz.open(p) as pdf:
    actual['pages']=len(pdf);ok &= all(type(n)==int and 1<=n<=len(pdf) for n in s.get('pages',[]))
  if s.get('exact_excerpt') is not None:
   if p.suffix.lower() not in ('.txt','.md'):r.add('source.excerpt.'+s['id'],'unverified','exact text mapping requires TXT/MD; scanned/PDF excerpt not inferred')
   else:ok &= s['exact_excerpt'] in p.read_text()
  r.add('source.'+s['id'],'pass' if ok else 'fail',actual,'file/hash/page/exact-text resolution only; not truth of citation')
def validate(path,*,mode='auto',meta=None,checks=None,app_root=None,preview=None):
 if app_root is None:
  candidate=Path(__file__).resolve().parents[3]
  if (candidate/'backend/ctrltea').exists():app_root=candidate
 meta=meta or {};r=Run(path,checks);data=r.path.read_bytes()
 if len(data)>50_000_000:raise ValueError('input exceeds 50 MB')
 kinds={'diagram','docx','pdf','structured','math','review','score','code'}
 try:
  if mode=='auto':
   if data.startswith(b'%PDF-'):mode='pdf'
   elif zipfile.is_zipfile(io.BytesIO(data)):
    with zipfile.ZipFile(io.BytesIO(data)) as z:mode='docx' if 'word/document.xml' in z.namelist() else 'unsupported'
   elif data.lstrip().startswith((b'<svg',b'<?xml')):mode='diagram'
   elif data.startswith((b'\x89PNG',b'\xff\xd8')):mode='diagram'
   elif r.path.suffix.lower() in ('.vhd','.vhdl'):mode='code'
   elif data.lstrip().startswith(b'{'):
    d=json.loads(data);mode='review' if 'assessment' in d else 'score' if 'dimensions' in d else 'math' if 'calculations' in d else 'structured' if 'sections' in d or 'figure' in d else 'unsupported'
   else:mode='unsupported'
  unknown=r.selected-kinds
  for name in sorted(unknown):r.add('selection.'+name,'unverified','unknown check group')
  if mode not in kinds:r.add('format','unverified','unsupported format')
  elif not r.wants(mode):r.add('selection','not_applicable',{'detected':mode,'requested':sorted(r.selected)})
  elif mode=='diagram':
   kind='svg' if data.lstrip().startswith(b'<') else 'raster'
   for cid,status,actual,lim in diagram(data,kind,meta.get('provenance','unknown')):r.add(cid,status,actual,limits_=lim)
  elif mode=='docx':docx_checks(r,data,meta,app_root,preview)
  elif mode=='pdf':pdf_checks(r,data,meta,app_root,preview)
  elif mode=='code':
   import shutil
   text=data.decode();entities=re.findall(r'\bentity\s+(\w+)\s+is\b',text,re.I);architectures=re.findall(r'\barchitecture\s+(\w+)\s+of\s+(\w+)\s+is\b',text,re.I)
   r.add('vhdl.structure','warning' if not entities or not architectures else 'pass',{'entities':entities,'architectures':architectures},limits_='lexical inventory only; comments and strings may imitate declarations; not syntax or elaboration')
   r.add('vhdl.compilation','unverified',{'ghdl_available':bool(shutil.which('ghdl'))},limits_='compiler not run; requires separately authorized isolated compilation scope; no uploaded code executed')
  elif mode in ('review','score'):r.call('qa.'+mode,mode,app_root,**({'report':json.loads(data)} if mode=='review' else {'data':json.loads(data)}))
  elif mode=='math':
   d=json.loads(data)
   for i,c in enumerate(d['calculations']):
    try:status,actual=math_case(c,app_root);r.add('math.'+str(c.get('id',i)),status,actual)
    except Exception as e:r.add('math.'+str(i),'fail',{'error':str(e)},'valid explicitly supported arithmetic input')
  elif mode=='structured':
   d=json.loads(data)
   if 'figure' in d:
    r.call('figure.structure','figure',app_root,figure=d['figure'])
    if 'expected_control' in meta:
     r.add('figure.source_mapping','pass' if d['figure'].get('control')==meta['expected_control'] else 'fail',{'matches_explicit_reference':d['figure'].get('control')==meta['expected_control']},'exact supplied structured reference including branches/signs/routes',limits_='reference must itself be approved; does not infer a graph from a scanned image')
    r.add('figure.scientific_equivalence','unverified','geometry alone cannot prove equivalence or source branch placement')
   else:
    r.call('lecture.schema','structure',app_root,document=d,manifest=meta.get('manifest'))
    r.call('lecture.math_render','math_render',app_root,document=d)
    for s in d.get('sections',[]):
     for b in s.get('blocks',[]):
      if b.get('figure'):r.call('figure.'+str(b.get('id')),'figure',app_root,figure=b['figure'])
    if 'source_pages' in meta:
     out=r.call('lecture.source_warnings','sources',app_root,document=d,pages=meta['source_pages'])
     if out.get('data',{}).get('issues'):r.rows[-1]['status']='warning'
    else:r.add('lecture.source_warnings','unverified','offline effective source pages not supplied; live database never queried')
  if meta.get('sources'):source_files(r,meta)
 except ImportError as e:r.add('dependency','unverified',{'missing':str(e)})
 except Exception as e:r.add('input','fail',{'error':str(e)[:1500],'type':type(e).__name__},'well-formed bounded input')
 if not r.rows:r.add('empty','unverified','no applicable checks executed')
 if sha(path)!=r.hash:raise RuntimeError('input changed during validation')
 return {'schema_version':'1.0.0','implementation':VERSION,'document':{'name':r.path.name,'sha256':r.hash},'mode':mode,'sidecar_sha256':hashlib.sha256(json.dumps(meta,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'checks':r.rows,'summary':{s:sum(x['status']==s for x in r.rows) for s in STATUSES}}
def attach_evidence(review,validation):
 """Separate compatible extension envelope, never changes assessment or events."""
 check_report(validation)
 r=engine('review',report=review)
 if r['status']!='ok':raise ValueError('invalid AQ05 report: '+str(r))
 if review['assessment']['document']['sha256']!=validation['document']['sha256']:raise ValueError('snapshot mismatch')
 # assessment.extensions changes its hash. Do not mutate it: create an explicit candidate.
 candidate=copy.deepcopy(review);candidate['review_id']=review['review_id']+'-aq06-evidence'
 candidate['assessment']['extensions']['aq06']={'version':'1.0.0','validation':validation,'parent_review_id':review['review_id'],'requires_reassessment':True}
 candidate['human_events']=[]
 encoded=json.dumps(candidate['assessment'],ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
 candidate['assessment_sha256']=hashlib.sha256(encoded.encode()).hexdigest()
 out=engine('review',report=candidate)
 if out['status']!='ok':raise ValueError('candidate contract failure')
 return {'parent_review':copy.deepcopy(review),'candidate_review':candidate,'note':'candidate has unchanged prior scores, not reassessed; no inherited approvals; parent events retained intact'}
def check_report(report):
 from jsonschema import Draft202012Validator
 schema=json.loads((Path(__file__).resolve().parents[1]/'validation-report.schema.json').read_text());Draft202012Validator(schema).validate(report)
 if any(c['snapshot_sha256']!=report['document']['sha256'] for c in report['checks']):raise ValueError('mixed check snapshots')
 expected={s:sum(c['status']==s for c in report['checks']) for s in STATUSES}
 if report['summary']!=expected:raise ValueError('incorrect status counts')
 return True
