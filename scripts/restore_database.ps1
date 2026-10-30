param(
    [Parameter(Mandatory = $true)][string]$Backup,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
if (-not $Force) { throw '恢复会覆盖当前数据库，请确认备份后增加 -Force。' }
$projectDir = Split-Path -Parent $PSScriptRoot
$backupDir = [IO.Path]::GetFullPath((Join-Path $projectDir 'backups'))
$source = [IO.Path]::GetFullPath($Backup)
if (-not $source.StartsWith($backupDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw '恢复文件必须位于项目 backups 目录内。'
}
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw '备份文件不存在。' }
$name = Split-Path -Leaf $source
$checksumFile = "$source.sha256"
if (Test-Path -LiteralPath $checksumFile) {
    $expected = ((Get-Content -LiteralPath $checksumFile -Raw).Trim() -split '\s+')[0]
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
    if ($expected -ne $actual) { throw '备份校验失败，文件可能已损坏或被修改。' }
}

Push-Location $projectDir
try {
    docker compose -p computer-course-rag stop api
    docker compose -p computer-course-rag exec -T postgres pg_restore -U rag -d rag --clean --if-exists --no-owner --no-acl "/backups/$name"
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore 执行失败。API 保持停止，请检查数据库后再启动。' }
    docker compose -p computer-course-rag start api
} finally {
    Pop-Location
}
Write-Output "数据库已从 $source 恢复。"
