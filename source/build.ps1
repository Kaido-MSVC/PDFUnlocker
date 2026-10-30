param([string]$BuildWork = (Join-Path $PSScriptRoot 'build'))
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# Always build with the project's Python 3.13 venv, never whatever "python" resolves to on PATH.
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Missing $python. Create it with: py -3.13 -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.lock.txt" -ErrorAction Continue
    exit 1
}
& $python -c "import sys; sys.exit(sys.version_info[:2] != (3, 13))"
if ($LASTEXITCODE -ne 0) { throw '.venv must be Python 3.13' }
& $python make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
$appIcon = Join-Path $PSScriptRoot 'assets/app.ico'
$appAssets = Join-Path $PSScriptRoot 'assets'
$runtimeHook = Join-Path $PSScriptRoot 'windowed_runtime.py'
$qpdfBundle = Join-Path $PSScriptRoot 'tools/qpdf'
foreach ($required in @('qpdf.exe', 'qpdf30.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $qpdfBundle $required))) { throw "Missing bundled qpdf file: $required" }
}
$license = Join-Path $PSScriptRoot 'LICENSE'
$notices = Join-Path $PSScriptRoot 'THIRD_PARTY_NOTICES.txt'
foreach ($required in @($license, $notices)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing license file: $required" }
}
# Unused packages; guards against them leaking in if they ever get installed in the venv.
$excludes = foreach ($module in @('numpy', 'psutil', 'yaml', 'charset_normalizer')) { '--exclude-module', $module }
& $python -m PyInstaller --noconfirm --clean --onedir --windowed --noupx --name PDFUnlocker --icon $appIcon --add-data "$appAssets;assets" --add-data "$qpdfBundle;tools/qpdf" --add-data "$license;." --add-data "$notices;." @excludes --collect-all customtkinter --runtime-hook $runtimeHook --hidden-import smoke --hidden-import test_core --distpath ../app --workpath $BuildWork --specpath $BuildWork app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
