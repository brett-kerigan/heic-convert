# Build heic-convert.exe locally. Run from the repo root.
$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python packaging\make_icon.py
.\.venv\Scripts\pyinstaller --clean --noconfirm packaging\heic-convert.spec
Write-Host "Built: dist\heic-convert.exe"
