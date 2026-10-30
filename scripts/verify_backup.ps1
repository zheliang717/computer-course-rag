param(
    [Parameter(Mandatory = $true)][string]$Backup
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$backupDir = [IO.Path]::GetFullPath((Join-Path $projectDir 'backups'))
$source = [IO.Path]::GetFullPath($Backup)
if (-not $source.StartsWith($backupDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw '校验文件必须位于项目 backups 目录内。'
}
$name = Split-Path -Leaf $source
$checksumFile = "$source.sha256"
if (-not (Test-Path -LiteralPath $checksumFile)) { throw '缺少 SHA-256 校验文件。' }
$expected = ((Get-Content -LiteralPath $checksumFile -Raw).Trim() -split '\s+')[0]
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
if ($expected -ne $actual) { throw '备份校验失败，文件可能已损坏或被修改。' }
$verifyDb = 'rag_restore_verify_' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
$created = $false

Push-Location $projectDir
try {
    docker compose -p computer-course-rag exec -T postgres createdb -U rag $verifyDb
    if ($LASTEXITCODE -ne 0) { throw '无法创建独立备份验证数据库。' }
    $created = $true
    docker compose -p computer-course-rag exec -T postgres pg_restore -U rag -d $verifyDb --no-owner --no-acl "/backups/$name"
    if ($LASTEXITCODE -ne 0) { throw '备份无法恢复到验证数据库。' }
    $tableCount = docker compose -p computer-course-rag exec -T postgres psql -U rag -d $verifyDb -Atc "select count(*) from information_schema.tables where table_schema='public';"
    $userCount = docker compose -p computer-course-rag exec -T postgres psql -U rag -d $verifyDb -Atc 'select count(*) from users;'
    if ([int]$tableCount -lt 10 -or [int]$userCount -lt 1) { throw '恢复后的结构或核心数据不完整。' }
    Write-Output "备份校验通过：$tableCount 张公共表，$userCount 个用户。"
} finally {
    if ($created) { docker compose -p computer-course-rag exec -T postgres dropdb -U rag $verifyDb | Out-Null }
    Pop-Location
}
