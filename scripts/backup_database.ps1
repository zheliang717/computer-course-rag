param(
    [string]$Name = "rag-$(Get-Date -Format 'yyyyMMdd-HHmmss').dump"
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$backupDir = Join-Path $projectDir 'backups'
if ($Name -notmatch '^[A-Za-z0-9._-]+\.dump$') {
    throw '备份名称只能包含字母、数字、点、下划线和连字符，并以 .dump 结尾。'
}
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$target = Join-Path $backupDir $Name

Push-Location $projectDir
try {
    docker compose -p computer-course-rag exec -T postgres pg_dump -U rag -d rag -Fc --no-owner --no-acl --file="/backups/$Name"
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump 执行失败。' }
} finally {
    Pop-Location
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$target.sha256" -Value "$hash  $Name" -Encoding ascii
Write-Output $target
