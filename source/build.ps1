param(
    [string]$BuildWork = (Join-Path $PSScriptRoot 'build'),
    [string]$DistPath = (Join-Path $PSScriptRoot '../app'),
    [string]$Python = (Join-Path $PSScriptRoot '.venv/Scripts/python.exe')
)
$ErrorActionPreference = 'Stop'
$BuildWork = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BuildWork)
$DistPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DistPath)
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw '找不到建置用 Python。請建立 Python 3.14.10 x64 虛擬環境，並依 README 安裝雜湊鎖定的套件。'
}
$Python = (Resolve-Path -LiteralPath $Python).Path
$appIcon = Join-Path $PSScriptRoot 'assets/app.ico'
$appAssets = Join-Path $PSScriptRoot 'assets'
$runtimeHook = Join-Path $PSScriptRoot 'windowed_runtime.py'
$qpdfBundle = Join-Path $PSScriptRoot 'tools/qpdf'
$requiredQpdf = @('qpdf.exe', 'qpdf30.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
$qpdfManifest = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $PSScriptRoot 'qpdf-sha256.txt')) {
    if ($line -match '^\s*(#.*)?$') { continue }
    if ($line -notmatch '^([0-9a-f]{64})\s+([a-z0-9_.]+)$') { throw 'qpdf SHA-256 清單格式錯誤。' }
    if ($Matches[2] -notin $requiredQpdf -or $qpdfManifest.ContainsKey($Matches[2])) {
        throw 'qpdf SHA-256 清單含有非預期或重複的檔案。'
    }
    $qpdfManifest.Add($Matches[2], $Matches[1])
}
$qpdfItems = @(Get-ChildItem -LiteralPath $qpdfBundle -Force)
if ($qpdfManifest.Count -ne $requiredQpdf.Count -or $qpdfItems.Count -ne $requiredQpdf.Count) {
    throw 'qpdf 封裝檔案與 SHA-256 清單不符。'
}
foreach ($item in $qpdfItems) {
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        !$qpdfManifest.ContainsKey($item.Name) -or
        (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash -ne $qpdfManifest[$item.Name]) {
        throw "qpdf 檔案未通過 SHA-256 驗證：$($item.Name)"
    }
}
$license = Join-Path $PSScriptRoot 'LICENSE'
$notices = Join-Path $PSScriptRoot 'THIRD_PARTY_NOTICES.txt'
foreach ($required in @($appIcon, $runtimeHook, $license, $notices, (Join-Path $PSScriptRoot 'requirements.lock.txt'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "缺少建置必要檔案：$required" }
}
& $Python -I -c "import platform, struct, sys; sys.exit(not (sys.version_info[:3] == (3, 14, 10) and platform.machine() == 'AMD64' and struct.calcsize('P') == 8 and sys.prefix != sys.base_prefix))"
if ($LASTEXITCODE -ne 0) { throw '需要 Python 3.14.10 x64 虛擬環境。' }
& $Python -I -m pip check
if ($LASTEXITCODE -ne 0) { throw '建置套件相依檢查失敗。' }

Push-Location -LiteralPath $PSScriptRoot
try {
    $excludes = foreach ($module in @('numpy', 'psutil', 'yaml', 'charset_normalizer')) { '--exclude-module', $module }
    & $Python -I -m PyInstaller --noconfirm --clean --onedir --contents-directory _internal --windowed --noupx --name PDFUnlocker --icon $appIcon --add-data "$appAssets;assets" --add-data "$qpdfBundle;tools/qpdf" --add-data "$license;." --add-data "$notices;." @excludes --collect-all customtkinter --runtime-hook $runtimeHook --hidden-import smoke --hidden-import test_core --distpath $DistPath --workpath $BuildWork --specpath $BuildWork app.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 建置失敗。' }
} finally {
    Pop-Location
}
