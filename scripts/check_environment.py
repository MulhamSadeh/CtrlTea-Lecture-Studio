"""Run on the target computer; checks tools, OCR and real native-math export."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from ctrltea.runtime import find_binary,tool_environment


def check(smoke=False):
    report={'platform':sys.platform,'python':sys.version.split()[0],'checks':{},'passed':False}
    for tool in ['pandoc','libreoffice','tesseract']:
        try:report['checks'][tool]={'ok':True,'path':find_binary(tool)}
        except ValueError as error:report['checks'][tool]={'ok':False,'error':str(error)}
    if not all(x['ok']for x in report['checks'].values()):return report
    env=tool_environment()
    langs=subprocess.run([find_binary('tesseract'),'--list-langs'],env=env,capture_output=True,text=True,timeout=30)
    available=langs.stdout.split()
    report['checks']['ocr_languages']={'ok':langs.returncode==0 and all(x in available for x in ['ara','eng']),'available':available}
    report['checks']['built_frontend']={'ok':(ROOT/'frontend/dist/index.html').is_file()}
    report['passed']=all(x['ok']for x in report['checks'].values())
    if not report['passed']or not smoke:return report
    from ctrltea import store
    from ctrltea.models import LectureDocument,Section,Block
    from ctrltea.exporter import build_docx,to_pdf
    import fitz
    from PIL import Image,ImageDraw,ImageFont
    destination=ROOT/'output/windows-check';destination.mkdir(parents=True,exist_ok=True)
    previous=store.DATA
    try:
        with tempfile.TemporaryDirectory(prefix='ct-check-')as tmp:
            store.DATA=Path(tmp)/'data';store.init()
            doc=LectureDocument(title='اختبار تثبيت',sections=[Section(title='فحص الاتجاه والمعادلات',blocks=[
                Block(kind='definition',title='تنسيق اختباري',text=r'نص عربي مع Input وOutput، والرمز \(y(t)\).'),
                Block(kind='equation',latex=r'\frac{a}{b}=x'),
                Block(kind='table',headers=['رمز','وصف'],rows=[[r'\(u(t)\)','نص عربي (A)']]),
                Block(kind='note',text=r'فحص ارتفاع السطر: \(\int_0^1 t\,dt\).')])])
            path=destination/'Native_Math_Check.docx';result=build_docx(doc,path);to_pdf(path,report=result)
            with fitz.open(path.with_suffix('.pdf'))as pdf:
                fonts=sorted({f[3]for p in pdf for f in p.get_fonts()})
                expected_fonts=any('Cairo'in f for f in fonts)and any('LatinModernMath'in f.replace('-','')for f in fonts)
            report['checks']['native_math_export']={'ok':result['pdf_math']['visible']==4 and expected_fonts,'equations':result['equations'],'fonts':fonts,'pdf':str(path.with_suffix('.pdf'))}
            image=Image.new('RGB',(1200,240),'white')
            font=ImageFont.truetype(str(ROOT/'assets/fonts/Cairo-Regular.ttf'),65)
            ImageDraw.Draw(image).text((50,50),'CTRL TEA 123',fill='black',font=font)
            png=Path(tmp)/'ocr.png';image.save(png)
            ocr=subprocess.run([find_binary('tesseract'),str(png),'stdout','-l','ara+eng','--psm','6'],env=env,capture_output=True,text=True,timeout=60)
            report['checks']['actual_ocr']={'ok':ocr.returncode==0 and '123'in ocr.stdout and 'CTRL'in ocr.stdout.upper() and 'Failed loading language'not in ocr.stderr,'text':ocr.stdout.strip()}
    finally:store.DATA=previous
    report['passed']=all(x['ok']for x in report['checks'].values())
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--smoke-test',action='store_true');args=p.parse_args()
    try:r=check(args.smoke_test)
    except Exception as error:r={'passed':False,'error':str(error)}
    folder=ROOT/'output/windows-check';folder.mkdir(parents=True,exist_ok=True)
    (folder/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,result in r.get('checks',{}).items():print(('OK  'if result['ok']else 'FAIL')+' '+name+(' — '+result.get('error','')if not result['ok']else ''))
    if 'error'in r:print(r['error'])
    print('Report: '+str(folder/'report.json'))
    sys.exit(0 if r['passed']else 1)
