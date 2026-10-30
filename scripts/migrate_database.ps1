$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$previousUrl = $env:DATABASE_URL
$env:DATABASE_URL = 'postgresql+psycopg://rag:rag@127.0.0.1:5432/rag'
Push-Location $projectDir
try {
    & .\.venv\Scripts\alembic.exe upgrade head
    if ($LASTEXITCODE -ne 0) { throw '数据库迁移失败。' }
    & .\.venv\Scripts\alembic.exe current
} finally {
    Pop-Location
    if ($null -eq $previousUrl) { Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue }
    else { $env:DATABASE_URL = $previousUrl }
}
