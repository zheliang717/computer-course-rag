param(
    [ValidateSet('Export','Import','Verify')][string]$Action = 'Verify',
    [string]$PackagePath,
    [string]$ExportDirectory,
    [switch]$NoOpen
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Docker([string[]]$Parts) {
    $result = & docker @Parts
    if ($LASTEXITCODE -ne 0) { throw 'Docker command failed. See the preceding message; existing data was not automatically removed.' }
    return $result
}
function Write-Json($Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
}
function File-Hash($Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function In-Package($Root, $Relative) {
    if (-not $Relative -or [IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)') { throw 'Invalid package path.' }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $path = [IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (-not $path.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) { throw 'Package path escapes its directory.' }
    return $path
}
function Image-Archive($Manifest) {
    if ($Manifest.format -eq 1) { return 'images.tar' }
    if ($Manifest.format -eq 2 -and $Manifest.image_archive -eq 'images.tar.gz') { return 'images.tar.gz' }
    throw 'Unsupported migration image archive.'
}
function Key-Stacks($Manifest) {
    if ($Manifest.format -eq 1) { return $Manifest.stacks }
    if ('key_stacks' -notin @($Manifest.PSObject.Properties.Name)) { throw 'Missing model key inventory.' }
    $keys = @($Manifest.key_stacks)
    if (@($keys | Select-Object -Unique).Count -ne $keys.Count) { throw 'Duplicate model key inventory.' }
    foreach ($name in $keys) { if ($name -notin $Manifest.stacks) { throw 'Unexpected model key stack.' } }
    return $keys
}
function Compress-Images($Root) {
    $sourcePath = In-Package $Root 'images.tar'
    $targetPath = In-Package $Root 'images.tar.gz'
    $rawBytes = (Get-Item -LiteralPath $sourcePath).Length
    $expected = File-Hash $sourcePath
    $source = [IO.File]::OpenRead($sourcePath)
    $target = [IO.File]::Open($targetPath, [IO.FileMode]::CreateNew)
    $gzip = $null
    try {
        $gzip = [IO.Compression.GZipStream]::new($target, [IO.Compression.CompressionLevel]::Optimal, $true)
        $source.CopyTo($gzip)
    } finally {
        if ($gzip) { $gzip.Dispose() }
        $target.Dispose(); $source.Dispose()
    }
    # Verify the full decompressed bytes before removing our own temporary tar.
    $inputFile = [IO.File]::OpenRead($targetPath)
    $decoder = [IO.Compression.GZipStream]::new($inputFile, [IO.Compression.CompressionMode]::Decompress)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { $actual = [BitConverter]::ToString($algorithm.ComputeHash($decoder)).Replace('-','').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $decoder.Dispose(); $inputFile.Dispose() }
    if ($actual -ne $expected) { throw 'Compressed image verification failed; original tar was preserved.' }
    Remove-Item -LiteralPath $sourcePath
    return $rawBytes
}
function Check-Package($Root) {
    $m = Get-Content -LiteralPath (Join-Path $Root 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($m.format -notin @(1,2) -or $m.stacks.Count -lt 1 -or $m.files.Count -lt 1) { throw 'Unsupported or incomplete migration package.' }
    if (@($m.stacks | Select-Object -Unique).Count -ne $m.stacks.Count) { throw 'Duplicate stacks in package.' }
    foreach ($entry in $m.files) {
        $path = In-Package $Root $entry.path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Package file missing: $($entry.path)" }
        if ((File-Hash $path) -ne $entry.sha256) { throw "Checksum failed: $($entry.path)" }
    }
    $required = @((Image-Archive $m),'project/compose.yaml','project/.env','project/scripts/portable.ps1')
    $keyStacks = @(Key-Stacks $m)
    foreach ($name in $m.stacks) {
        if ($name -notin @('local','preview')) { throw 'Unexpected stack in package.' }
        $required += "database/$name.dump"
        if ($name -in $keyStacks) { $required += "config/$name/model-config.key" }
        if ($name -eq 'preview') { $required += @('project/compose.funnel.yaml','project/.private/funnel/stack.env') }
    }
    foreach ($name in $required) {
        if ($name -notin @($m.files | ForEach-Object { $_.path.Replace('\','/') })) { throw "Required file is not covered by checksums: $name" }
    }
    return $m
}
function Stack($Name, $Root) {
    if ($Name -eq 'local') {
        return @{ name='local'; project='computer-course-rag'; user='rag'; db='rag';
            compose=@('compose','-p','computer-course-rag','--env-file',(Join-Path $Root '.env'),'-f',(Join-Path $Root 'compose.yaml'));
            volumes=@('computer-course-rag_postgres_data','computer-course-rag_config_data'); web='http://127.0.0.1:5173';
            dump=(Join-Path $Root 'backups/portable-local.dump'); mounted='/backups/portable-local.dump' }
    }
    return @{ name='preview'; project='rag-funnel'; user='rag_preview'; db='rag_preview';
        compose=@('compose','-p','rag-funnel','--env-file',(Join-Path $Root '.private/funnel/stack.env'),'-f',(Join-Path $Root 'compose.funnel.yaml'));
        volumes=@('rag-funnel_preview_postgres','rag-funnel_preview_config'); web='http://127.0.0.1:18080';
        dump=(Join-Path $Root 'backups/funnel/portable-preview.dump'); mounted='/backups/portable-preview.dump' }
}
function Copy-Tree($Source, $Destination, [string[]]$Excluded=@()) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $parts = @($Source,$Destination,'/E','/COPY:DAT','/DCOPY:DAT','/R:1','/W:1','/NFL','/NDL','/NJH','/NJS','/NP')
    if ($Excluded.Count) { $parts += @('/XD') + $Excluded }
    & robocopy @parts | Out-Null
    if ($LASTEXITCODE -ge 8) { throw 'Copy failed. The incomplete package is retained for inspection.' }
}
function Wait-Ready($Url) {
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        try { if ((Invoke-RestMethod ($Url+'/health') -TimeoutSec 3).status -eq 'ok') { return } } catch { }
        Start-Sleep -Seconds 2
    }
    throw "Services were preserved but did not become ready: $Url . Check Docker logs before retrying."
}

if ($Action -eq 'Verify') {
    if (-not $PackagePath) { throw 'Specify -PackagePath for Verify.' }
    $null = Check-Package ([IO.Path]::GetFullPath($PackagePath))
    Write-Output 'Package checksums and required files verified.'
    exit 0
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'The double-click migration helper currently supports Windows. Docker Linux containers are required.' }
Get-Command docker -ErrorAction Stop | Out-Null
if ((Invoke-Docker @('info','--format','{{.OSType}}')) -ne 'linux') { throw '请先启动 Docker Desktop，并切换到 Linux 容器。' }
Push-Location $projectRoot
try {
    if ($Action -eq 'Export') {
        $names = @('local')
        $preview = @(Invoke-Docker @('ps','-aq','--filter','label=com.docker.compose.project=rag-funnel'))
        if ($preview.Count) { $names += 'preview' }
        $stamp = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6)
        if (-not $ExportDirectory) { $ExportDirectory = Join-Path (Split-Path -Parent $projectRoot) 'zhixue-migration-packages' }
        $exportRoot = [IO.Path]::GetFullPath($ExportDirectory).TrimEnd([IO.Path]::DirectorySeparatorChar)
        $sourceRoot = [IO.Path]::GetFullPath($projectRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
        if ($exportRoot -eq $sourceRoot -or $exportRoot.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'ExportDirectory must be outside the project folder.' }
        New-Item -ItemType Directory -Force -Path $exportRoot | Out-Null
        $pack = In-Package $exportRoot "zhixue-$stamp"
        New-Item -ItemType Directory -Path $pack | Out-Null
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl = [Security.AccessControl.DirectorySecurity]::new()
        $acl.SetOwner($sid); $acl.SetAccessRuleProtection($true, $false)
        foreach ($identity in @($sid, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'), [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))) {
            $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
        }
        Set-Acl -LiteralPath $pack -AclObject $acl
        $images = @()
        $models = @()
        $keyStacks = @()
        foreach ($name in $names) {
            $s = Stack $name $projectRoot
            Write-Host "正在备份 $name 数据库与模型配置..."
            foreach ($service in @('postgres','api','web')) {
                $ids = @(Invoke-Docker ($s.compose + @('ps','--all','--quiet',$service)))
                if ($ids.Count -ne 1) { throw "Missing or ambiguous $name service: $service" }
                $item = (Invoke-Docker @('inspect',$ids[0]) | Out-String | ConvertFrom-Json)[0]
                $reference = $item.Config.Image
                if ($reference -notmatch '@' -and ($reference -split '/')[-1] -notmatch ':') { $reference += ':latest' }
                $image = (Invoke-Docker @('image','inspect',$reference) | Out-String | ConvertFrom-Json)[0]
                if ($image.Id -ne $item.Image) { throw 'An image tag differs from the running service. Reconcile the release before exporting.' }
                if ($image.Os -ne 'linux' -or $image.Architecture -ne 'amd64') { throw 'This migration helper expects the verified linux/amd64 release.' }
                $images += $reference
                if ($service -eq 'api') {
                    $provider = @($item.Config.Env | Where-Object { $_.StartsWith('EMBEDDING_PROVIDER=') })
                    $model = @($item.Config.Env | Where-Object { $_.StartsWith('EMBEDDING_MODEL=') })
                    if ($provider.Count -ne 1 -or $model.Count -ne 1) { throw 'Embedding settings must be explicit for a complete export.' }
                    if ($provider[0].Substring(19) -ne 'hashing') { $models += $model[0].Substring(16) }
                    $dest = Join-Path $pack "config/$name"
                    New-Item -ItemType Directory -Force -Path $dest | Out-Null
                    $null = Invoke-Docker @('cp',($ids[0]+':/app/config-data/.'),$dest)
                    if (Test-Path -LiteralPath (Join-Path $dest 'model-config.key') -PathType Leaf) { $keyStacks += $name }
                    else {
                        $encrypted = Invoke-Docker @('exec',$ids[0],'python','-c','from app.database import get_session_factory; from app.models import ModelRuntimeConfig; s=get_session_factory()(); r=s.get(ModelRuntimeConfig,1); print(bool(r and r.api_key_ciphertext)); s.close()')
                        if (($encrypted -join '').Trim() -ne 'False') { throw 'The model encryption key is missing for saved encrypted credentials. Export stopped.' }
                    }
                }
                if ($service -eq 'postgres') {
                    $dest = Join-Path $pack 'database'
                    New-Item -ItemType Directory -Force -Path $dest | Out-Null
                    $remote = '/tmp/portable-'+$stamp+'.dump'
                    $null = Invoke-Docker @('exec',$ids[0],'pg_dump','-U',$s.user,'-d',$s.db,'-Fc','--no-owner','--no-acl',('--file='+$remote))
                    $null = Invoke-Docker @('cp',($ids[0]+':'+$remote),(Join-Path $dest ($name+'.dump')))
                    # Remove only this explicitly named temporary export inside the container.
                    $null = Invoke-Docker @('exec',$ids[0],'rm','--',$remote)
                }
            }
        }
        Write-Host '正在复制程序、配置和模型缓存...'
        Copy-Tree $projectRoot (Join-Path $pack 'project') @('.git','.venv','node_modules','__pycache__','.pytest_cache','*.egg-info','backups','reports','tmp','portable-packages','migration','test-results','playwright-report','.qa','.private','models-cache')
        if ('preview' -in $names) {
            Copy-Tree (Join-Path $projectRoot '.private/funnel') (Join-Path $pack 'project/.private/funnel') @('reports')
        }
        $models = @($models | Select-Object -Unique)
        if ($models.Count) {
            $cacheRoot = Join-Path $projectRoot 'models-cache'
            $excludedModels = @()
            $huggingFaceModels = @($models | Where-Object { $_ -match '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' })
            # Unknown local model paths retain the complete cache rather than risk an incomplete export.
            if ($huggingFaceModels.Count -eq $models.Count) {
                $requiredModels = @($models | ForEach-Object { 'models--' + $_.Replace('/','--') })
                foreach ($modelName in $requiredModels) {
                    if (-not (Test-Path -LiteralPath (Join-Path $cacheRoot $modelName)) -and -not (Test-Path -LiteralPath (Join-Path $cacheRoot "hub/$modelName"))) { throw 'The active embedding model cache is missing; export stopped.' }
                }
                foreach ($base in @($cacheRoot, (Join-Path $cacheRoot 'hub'))) {
                    if (Test-Path -LiteralPath $base) {
                        $excludedModels += @(Get-ChildItem -LiteralPath $base -Directory -Filter 'models--*' | Where-Object { $_.Name -notin $requiredModels } | ForEach-Object { $_.FullName })
                        foreach ($repository in @(Get-ChildItem -LiteralPath $base -Directory -Filter 'models--*' | Where-Object { $_.Name -in $requiredModels })) {
                            # Robocopy dereferences snapshot file links. Retain the standalone
                            # snapshots/refs and avoid also copying their duplicate blob bytes.
                            if (Test-Path -LiteralPath (Join-Path $repository.FullName 'snapshots') -PathType Container) {
                                $excludedModels += (Join-Path $repository.FullName 'blobs')
                            }
                        }
                    }
                }
            }
            Copy-Tree $cacheRoot (Join-Path $pack 'project/models-cache') $excludedModels
        }
        $null = Invoke-Docker (@('image','save','-o',(In-Package $pack 'images.tar')) + @($images | Select-Object -Unique))
        Write-Host '正在压缩运行镜像并校验完整性...'
        $imageBytes = Compress-Images $pack
        $launcher = "@echo off`r`nchcp 65001 >nul`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0project\scripts\portable.ps1`" -Action Import -PackagePath `"%~dp0.`"`r`nif errorlevel 1 echo Import stopped. Keep this window and package for inspection.`r`npause`r`n"
        [IO.File]::WriteAllText((Join-Path $pack 'Import.cmd'),$launcher,[Text.Encoding]::ASCII)
        Write-Host '正在生成文件校验值...'
        $files = @(Get-ChildItem -LiteralPath $pack -File -Recurse | ForEach-Object {
            @{ path=$_.FullName.Substring($pack.Length+1).Replace('\','/'); sha256=(File-Hash $_.FullName) }
        })
        Write-Json (Join-Path $pack 'manifest.json') @{ format=2; image_archive='images.tar.gz'; image_uncompressed_bytes=$imageBytes; embedding_models=$models; key_stacks=@($keyStacks); bundle_id=$stamp; created_at=(Get-Date).ToString('o'); platform='linux/amd64'; stacks=$names; files=$files }
        [IO.File]::WriteAllText((Join-Path $pack 'READ-ME.txt'),"Private migration package. Contains databases and credentials. Do not upload it to GitHub.`r`nInstall Docker Desktop (Linux containers) on the new Windows x64 PC, then double-click Import.cmd.`r`nTailscale must be logged in and enabled separately on the new PC. Unsaved browser drafts are not included.`r`n",[Text.Encoding]::UTF8)
        Write-Host "导出完成。请把这个完整文件夹复制到新电脑：$pack"
        if (-not $NoOpen) { Invoke-Item -LiteralPath $pack }
    } else {
        if (-not $PackagePath) {
            Add-Type -AssemblyName System.Windows.Forms
            $picker = New-Object System.Windows.Forms.FolderBrowserDialog
            $picker.Description = '请选择之前导出的 zhixue 迁移包文件夹'
            if ($picker.ShowDialog() -ne 'OK') { throw 'Import cancelled.' }
            $PackagePath = $picker.SelectedPath
        }
        $pack = [IO.Path]::GetFullPath($PackagePath)
        Write-Host '正在校验迁移包，请稍候...'
        $m = Check-Package $pack
        if ($m.platform -ne 'linux/amd64' -or (Invoke-Docker @('info','--format','{{.Architecture}}')) -notin @('x86_64','amd64')) { throw 'This package needs an x64 Docker engine.' }
        $target = In-Package $pack 'project'
        # Reject any existing installation before loading images or restoring data.
        foreach ($name in $m.stacks) {
            $s = Stack $name $target
            if (@(Invoke-Docker @('ps','-aq','--filter',('label=com.docker.compose.project='+$s.project))).Count) { throw "当前电脑已有 $($s.project)，为保留现有数据，本次导入已停止。" }
            foreach ($volume in $s.volumes) {
                if (@(Invoke-Docker @('volume','ls','--quiet','--filter',('name=^'+$volume+'$'))).Count) { throw "当前电脑已有数据卷 $volume，本次导入已停止，不会覆盖现有数据。" }
            }
        }
        $ports = @(5173,8000,5432)
        if ('preview' -in $m.stacks) { $ports += 18080 }
        $busyPorts = @([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -in $ports } | Select-Object -ExpandProperty Port -Unique)
        if ($busyPorts.Count) { throw ('Required ports are already in use: '+($busyPorts -join ', ')+'. Import did not create or overwrite databases.') }
        Write-Host '正在导入运行镜像，请保持窗口打开...'
        $null = Invoke-Docker @('image','load','-i',(In-Package $pack (Image-Archive $m)))
        foreach ($name in $m.stacks) {
            $s = Stack $name $target
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $s.dump) | Out-Null
            Copy-Item -LiteralPath (In-Package $pack "database/$name.dump") -Destination $s.dump
            $null = Invoke-Docker ($s.compose + @('create','--no-build','postgres','api','web'))
            $api = @(Invoke-Docker ($s.compose + @('ps','--all','--quiet','api')))[0]
            if ($name -in @(Key-Stacks $m)) { $null = Invoke-Docker @('cp',((In-Package $pack "config/$name")+'\.'),($api+':/app/config-data/')) }
            $null = Invoke-Docker ($s.compose + @('up','-d','--no-build','--wait','postgres'))
            $null = Invoke-Docker ($s.compose + @('exec','-T','postgres','pg_restore','-U',$s.user,'-d',$s.db,'--exit-on-error','--no-owner','--no-acl',$s.mounted))
        }
        foreach ($name in $m.stacks) {
            $s = Stack $name $target
            $null = Invoke-Docker ($s.compose + @('up','-d','--no-build','api','web'))
            Wait-Ready $s.web
            Write-Host "服务已就绪：$($s.web)"
        }
        Write-Host '导入完成，账号和模型配置已恢复。公网访问还需在新电脑登录 Tailscale 并启用 Funnel。'
        Start-Process 'http://127.0.0.1:5173/'
    }
} finally { Pop-Location }
