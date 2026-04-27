$ErrorActionPreference = "Stop"

python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

Write-Host "Bootstrap completed."
Write-Host "Run dev server: .\\scripts\\run_dev.ps1"
Write-Host "Run tests: pytest"
Write-Host "Run lint: ruff check ."
