# Local SQLite demo, no Docker required. Run from repository root.
$ErrorActionPreference = 'Stop'
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Create .venv and install requirements.txt first. See README.md.' }
if (-not $env:SECRET_KEY) {
    $env:SECRET_KEY = & ./.venv/Scripts/python.exe -c 'import secrets; print(secrets.token_hex(32))'
}
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = 'sqlite:///./local.db' }
& ./.venv/Scripts/python.exe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migrations failed.' }
& ./.venv/Scripts/python.exe -m app.cli seed-demo
if ($LASTEXITCODE -ne 0) { throw 'Demo data could not be loaded.' }
& ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
