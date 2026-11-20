"""Small platform boundary for external programs and SVG preview pixels."""
from pathlib import Path
import os
import shutil
import sys

IS_WINDOWS = sys.platform == 'win32'
ROOT = Path(__file__).resolve().parents[2]
OVERRIDES = {'pandoc':'CTRLTEA_PANDOC','libreoffice':'CTRLTEA_LIBREOFFICE','tesseract':'CTRLTEA_TESSERACT'}


def find_binary(tool):
    variable = OVERRIDES[tool]
    if os.environ.get(variable):
        candidate = Path(os.environ[variable]).expanduser()
        if candidate.is_file(): return str(candidate.resolve())
        raise ValueError(f'{variable}: المسار المحدد غير موجود: {candidate}')
    names = {'pandoc':['pandoc'], 'tesseract':['tesseract'],
             'libreoffice':['soffice.com','soffice.exe','libreoffice','soffice'] if IS_WINDOWS else ['libreoffice','soffice']}[tool]
    for name in names:
        found = shutil.which(name)
        if found: return found
    if IS_WINDOWS:
        suffixes = {'pandoc':['Pandoc/pandoc.exe','Programs/Pandoc/pandoc.exe','Microsoft/WinGet/Links/pandoc.exe'],
                    'libreoffice':['LibreOffice/program/soffice.com','LibreOffice/program/soffice.exe'],
                    'tesseract':['Tesseract-OCR/tesseract.exe','Programs/Tesseract-OCR/tesseract.exe']}[tool]
        for key in ['ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA']:
            if not os.environ.get(key): continue
            for suffix in suffixes:
                path = Path(os.environ[key])/suffix
                if path.is_file(): return str(path)
    guide='Install-Windows.cmd' if IS_WINDOWS else 'README_AR.md'
    raise ValueError(f'{tool} غير مثبت أو لم يُعثر عليه؛ راجع {guide}.')


def tool_environment():
    env = dict(os.environ)
    if not IS_WINDOWS:
        env.setdefault('FONTCONFIG_FILE',str(ROOT/'assets/fonts.conf'))
    tessdata = env.get('CTRLTEA_TESSDATA_DIR')
    local = ROOT/'.tools/tessdata'
    if tessdata:
        path=Path(tessdata).expanduser()
        if not all((path/(lang+'.traineddata')).is_file()for lang in ['ara','eng']):
            raise ValueError('CTRLTEA_TESSDATA_DIR يجب أن يحتوي ara.traineddata وeng.traineddata')
        env['TESSDATA_PREFIX']=str(path.resolve())
    elif IS_WINDOWS and not env.get('TESSDATA_PREFIX') and all((local/(lang+'.traineddata')).is_file()for lang in ['ara','eng']):
        env['TESSDATA_PREFIX']=str(local)
    return env


def svg_png(svg, *, output_width=None):
    """Only preview/fallback pixels; the original scientific SVG is kept."""
    if not IS_WINDOWS:
        import cairosvg
        return cairosvg.svg2png(bytestring=svg,output_width=output_width)
    import math
    import fitz
    with fitz.open(stream=svg,filetype='svg')as document:
        page=document[0]
        width=output_width or math.ceil(page.rect.width*96/72)
        if page.rect.width<=0 or width<=0:raise ValueError('أبعاد SVG غير صالحة')
        return page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width,width/page.rect.width),alpha=True).tobytes('png')
