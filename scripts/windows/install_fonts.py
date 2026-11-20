"""Install bundled fonts for the current Windows user, without admin rights."""
from pathlib import Path
import ctypes
import hashlib
import os
import shutil
import sys


def install():
    if sys.platform!='win32':raise RuntimeError('This font installer runs on Windows only.')
    import winreg
    from ctypes import wintypes
    root=Path(__file__).resolve().parents[2]
    target=Path(os.environ['LOCALAPPDATA'])/'Microsoft/Windows/Fonts'
    target.mkdir(parents=True,exist_ok=True)
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    gdi.AddFontResourceExW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_void_p]
    gdi.AddFontResourceExW.restype=ctypes.c_int
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.SendMessageTimeoutW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_size_t)]
    sources=sorted((root/'assets/fonts').glob('*.ttf'))+sorted((root/'assets/fonts').glob('*.otf'))+sorted((root/'frontend/public/fonts').glob('*.ttf'))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows NT\CurrentVersion\Fonts')as key:
        for source in sources:
            digest=hashlib.sha256(source.read_bytes()).hexdigest()[:12]
            path=target/f'CtrlTea-{source.stem}-{digest}{source.suffix}'
            # Unique versioned filenames avoid overwriting fonts loaded by Word.
            if not path.exists():shutil.copyfile(source,path)
            winreg.SetValueEx(key,'CtrlTea '+source.stem,0,winreg.REG_SZ,str(path))
            gdi.AddFontResourceExW(str(path),0,None)
    result=ctypes.c_size_t()
    user.SendMessageTimeoutW(0xffff,0x001d,0,0,2,1000,ctypes.byref(result))
    print(f'Registered {len(sources)} bundled fonts for the current user.')

if __name__=='__main__':install()
