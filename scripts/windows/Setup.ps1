$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Run-Winget([string]$PackageId) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'WinGet is missing. Install App Installer from Microsoft Store, or install the prerequisites manually (docs/platforms/README_WINDOWS_AR.md).'
    }
    Write-Host "Installing $PackageId ..."
    & winget.exe install --source winget --id $PackageId --exact --architecture x64 --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "WinGet failed for $PackageId. Exit code: $LASTEXITCODE" }
}

function Find-Python312 {
    $Candidates = @()
    if ($env:LOCALAPPDATA) { $Candidates += (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe') }
    if ($env:ProgramFiles) { $Candidates += (Join-Path $env:ProgramFiles 'Python312\python.exe') }
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        $SavedPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $Probe = & $Launcher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null
        $ProbeExit = $LASTEXITCODE
        $ErrorActionPreference = $SavedPreference
        if ($ProbeExit -eq 0 -and $Probe) { $Candidates += ($Probe | Select-Object -Last 1) }
    }
    $OnPath = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($OnPath -and $OnPath.Source -notlike '*WindowsApps*') { $Candidates += $OnPath.Source }
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            $Version = & $Candidate -c 'import sys; print(sys.version[:4])'
            if ($LASTEXITCODE -eq 0 -and $Version -eq '3.12') { return $Candidate }
        }
    }
    return $null
}

try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    $PythonExe = Find-Python312
    if (-not $PythonExe) { Run-Winget 'Python.Python.3.12'; $PythonExe = Find-Python312 }
    if (-not $PythonExe) { throw 'Python 3.12 was not found. Reopen this installer after installing Python 3.12 (x64).' }
    $VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        if (Test-Path -LiteralPath (Join-Path $ProjectRoot '.venv')) {
            throw 'An incompatible .venv already exists. Rename that folder, then rerun setup. Keep data unchanged.'
        }
        & $PythonExe -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }
    $VenvVersion = & $VenvPython -c 'import sys; print(sys.version[:4])'
    if ($LASTEXITCODE -ne 0 -or $VenvVersion -ne '3.12') { throw 'Existing .venv is not Python 3.12. Rename .venv and run setup again; keep data unchanged.' }
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip update failed.' }
    & $VenvPython -m pip install -r requirements-windows.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

    $ProbeCode = @'
import os, sys
from ctrltea.runtime import find_binary, OVERRIDES
try:
    print(find_binary(sys.argv[1]))
except ValueError as error:
    if os.environ.get(OVERRIDES[sys.argv[1]]):
        print('CONFIG_ERROR:'+str(error))
'@
    foreach ($Pair in @(@('pandoc','JohnMacFarlane.Pandoc'), @('libreoffice','TheDocumentFoundation.LibreOffice'), @('tesseract','UB-Mannheim.TesseractOCR'))) {
        $Found = (& $VenvPython -c $ProbeCode $Pair[0] | Out-String).Trim()
        if ($Found.StartsWith('CONFIG_ERROR:')) { throw $Found }
        if (-not $Found) { Run-Winget $Pair[1] }
        $Found = (& $VenvPython -c $ProbeCode $Pair[0] | Out-String).Trim()
        if (-not $Found) { throw "Could not find $($Pair[0]). See README_WINDOWS_AR.md for custom installation paths." }
        Write-Host "$($Pair[0]): $Found"
    }

    $TessFolder = Join-Path $ProjectRoot '.tools\tessdata'
    New-Item -ItemType Directory -Force -Path $TessFolder | Out-Null
    $LanguageHashes = @{
        ara = 'e3206d3dc87fd50c24a0fb9f01838615911d25168f4e64415244b67d2bb3e729'
        eng = '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
    }
    foreach ($Language in @('ara','eng')) {
        $Destination = Join-Path $TessFolder ($Language+'.traineddata')
        if (-not (Test-Path -LiteralPath $Destination) -or (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLower() -ne $LanguageHashes[$Language]) {
            $Partial = $Destination+'.partial'
            Invoke-WebRequest -UseBasicParsing -Uri ("https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/"+$Language+'.traineddata') -OutFile $Partial
            if ((Get-FileHash -LiteralPath $Partial -Algorithm SHA256).Hash.ToLower() -ne $LanguageHashes[$Language]) { throw "OCR download checksum failed: $Language" }
            Move-Item -LiteralPath $Partial -Destination $Destination -Force
        }
    }
    & $VenvPython scripts/windows/install_fonts.py
    if ($LASTEXITCODE -ne 0) { throw 'Font installation failed.' }
    & $VenvPython scripts/check_environment.py --smoke-test
    if ($LASTEXITCODE -ne 0) { throw 'Environment verification failed. Open output/windows-check/report.json for details.' }
    Write-Host 'Installation complete. Open Start-Windows.cmd.' -ForegroundColor Green
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
