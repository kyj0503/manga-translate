# Build the runnable program folder: app venv + app wheel + bundled uv + shortcut.
# Engine, llama.cpp, models and settings in the folder are left untouched on rebuild.
param(
    [string]$Dest = (Join-Path $env:USERPROFILE "Downloads\manga-translate"),
    [string]$Uv = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

# The program folder holds downloads and settings, so it must be separate from the source checkout.
$destFull = [System.IO.Path]::GetFullPath($Dest).TrimEnd('\')
$repoFull = [System.IO.Path]::GetFullPath($repo).TrimEnd('\')
if ($destFull -ieq $repoFull -or $destFull.StartsWith("$repoFull\", [System.StringComparison]::OrdinalIgnoreCase) -or $repoFull.StartsWith("$destFull\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "The program folder ($destFull) overlaps the source folder ($repoFull). Clone the source elsewhere or pass -Dest with another folder."
}

if (-not $Uv) {
    if ($env:UV -and (Test-Path $env:UV)) { $Uv = $env:UV }
    else { $Uv = (Get-Command uv -ErrorAction Stop).Source }
}

$dist = Join-Path $env:TEMP "manga-translate-dist"
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
& $Uv build --wheel --out-dir $dist $repo
if ($LASTEXITCODE -ne 0) { throw "uv build failed" }
$wheel = Get-ChildItem $dist -Filter *.whl | Select-Object -First 1

New-Item -ItemType Directory -Force -Path $Dest, (Join-Path $Dest "tools") | Out-Null
$python = Join-Path $Dest ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    & $Uv venv --python 3.12 (Join-Path $Dest ".venv")
    if ($LASTEXITCODE -ne 0) { throw "uv venv failed" }
}
& $Uv pip install --python $python --reinstall $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw "installing the app failed" }

Copy-Item $Uv (Join-Path $Dest "tools\uv.exe") -Force

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $Dest "manga-translate.lnk"))
$link.TargetPath = Join-Path $Dest ".venv\Scripts\manga-translate.exe"
$link.WorkingDirectory = $Dest
$link.Save()

Write-Host "Built: $Dest"
