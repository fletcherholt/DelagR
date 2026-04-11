$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$iconDir = Join-Path $repoRoot "build\assets"
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null
$iconPath = Join-Path $iconDir "delagr.ico"

python -c "from pathlib import Path; from PIL import Image; src = Path('icon.png'); out = Path(r'$iconPath'); img = Image.open(src).convert('RGBA'); img.save(out, format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name DelagR `
  --icon $iconPath `
  --collect-all webview `
  src\delagr.py

Write-Host ""
Write-Host "Built:" (Join-Path $repoRoot "dist\DelagR.exe")

