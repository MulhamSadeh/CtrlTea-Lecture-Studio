"""Build a closed, CRC-verified ZIP before exposing its final filename."""
from pathlib import Path
import argparse,hashlib,os,tempfile,zipfile
ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'node_modules','__pycache__','.git','.venv','.pytest_cache','.ruff_cache','data','output','.mypy_cache'}


def package(destination):
    destination=destination.resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    paths=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and
        not any(x in EXCLUDE or x.endswith('.egg-info') or (x.startswith('.')and x!='.gitignore') for x in p.relative_to(ROOT).parts)
        and p.suffix not in {'.pyc','.tsbuildinfo'} and p.resolve()!=destination]
    with tempfile.NamedTemporaryFile(dir=destination.parent,prefix='ct-release-',suffix='.partial',delete=False)as f:temporary=Path(f.name)
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as archive:
            for path in paths:archive.write(path,str(Path('ctrltea-studio')/path.relative_to(ROOT)))
        with zipfile.ZipFile(temporary)as archive:
            assert archive.testzip() is None
            assert 'ctrltea-studio/frontend/dist/index.html'in archive.namelist()
            assert 'ctrltea-studio/backend/ctrltea/pdf_math.py'in archive.namelist()
        with temporary.open('rb')as f:os.fsync(f.fileno())
        os.replace(temporary,destination)
        digest=hashlib.sha256(destination.read_bytes()).hexdigest()
        return {'path':str(destination),'files':len(paths),'bytes':destination.stat().st_size,'sha256':digest}
    finally:temporary.unlink(missing_ok=True)

if __name__=='__main__':
    import json
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args()
    print(json.dumps(package(args.output),indent=2))
