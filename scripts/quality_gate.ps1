param([switch]$IsolatedIntegration)
$ErrorActionPreference = 'Stop'
$env:STORAGE_BACKEND = 'memory'
$env:EMBEDDING_PROVIDER = 'hashing'
$env:LLM_PROVIDER = 'offline'
$env:AUTH_REQUIRED = 'false'
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location frontend
try { npm run build; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } } finally { Pop-Location }
if (-not $IsolatedIntegration) { exit 0 }
if ($env:LIVE_API_URL -ne 'http://127.0.0.1:18084' -or $env:LIVE_DATABASE_URL -notmatch '/rag_today_dev_20261028$') {
    throw 'Integration tests require the explicit isolated API/database copy. No live service will be restarted.'
}
$env:LIVE_API_TESTS = '1'
& .\.venv\Scripts\python.exe -m pytest -q tests/test_live_platform.py tests/test_live_business_flows.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe scripts/performance_gate.py --base-url $env:LIVE_API_URL
exit $LASTEXITCODE
