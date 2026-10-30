param(
    [ValidateSet('Prepare','Build','Start','Stop','Status','Backup','LocalStart','LocalStop')]
    [string]$Action = 'Status',
    [string]$SeedBackup
)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$privateDir = Join-Path $projectDir '.private/funnel'
$envPath = Join-Path $privateDir 'stack.env'
$markerPath = Join-Path $privateDir 'initialized.json'
$composePath = Join-Path $projectDir 'compose.funnel.yaml'
$tailscaleExe = Join-Path $env:ProgramFiles 'Tailscale/tailscale.exe'
$target = 'http://127.0.0.1:18080'

function Invoke-Stack([string[]]$Parameters) {
    & docker compose -p rag-funnel --env-file $envPath -f $composePath @Parameters
    if ($LASTEXITCODE -ne 0) { throw '独立内测栈操作失败；未自动删除数据，请保留输出排查。' }
}
function Write-PrivateText([string]$Path, [string]$Value) {
    [IO.File]::WriteAllText($Path, $Value, [Text.UTF8Encoding]::new($false))
}
function New-RandomSecret {
    $bytes = [byte[]]::new(48)
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}
function Protect-PrivateDirectory {
    New-Item -ItemType Directory -Force -Path $privateDir | Out-Null
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($sid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($identity in @($sid, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'), [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    Set-Acl -LiteralPath $privateDir -AclObject $acl
}
function Assert-OwnFunnel {
    $raw = & $tailscaleExe funnel status --json
    if ($LASTEXITCODE -ne 0) { throw '无法读取Funnel配置。' }
    $config = $raw | ConvertFrom-Json
    if ($config.TCP -and @($config.TCP.PSObject.Properties | Where-Object Name -ne '443').Count) {
        throw '此设备还有其他端口的Serve/Funnel配置，拒绝自动修改。'
    }
    if ($config.TCP.'443' -and (-not $config.TCP.'443'.HTTPS -or -not $config.Web)) {
        throw '443端口已有非本项目网页代理配置，拒绝自动修改。'
    }
    if ($config.Web) {
        foreach ($site in $config.Web.PSObject.Properties) {
            if (-not $site.Name.EndsWith(':443')) { throw '发现其他端口的网页服务，拒绝自动修改。' }
            foreach ($handler in $site.Value.Handlers.PSObject.Properties) {
                if ($handler.Name -ne '/' -or $handler.Value.Proxy -ne $target) { throw '此设备已有其他Serve/Funnel服务，拒绝覆盖。请先人工核对。' }
            }
        }
    }
    return $config
}
function Assert-LocalReady {
    if (-not (Test-Path -LiteralPath $markerPath)) { throw '请先执行Prepare，不能公开未加固的空白副本。' }
    $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
    if ($marker.database -ne 'rag_preview' -or $marker.users_rotated -lt 1) { throw '副本初始化标记无效。' }
    foreach ($service in @('postgres','api')) {
        $id = Invoke-Stack -Parameters @('ps','-q',$service)
        if (-not $id) { throw '副本服务尚未启动。' }
        $published = & docker inspect $id --format '{{json .HostConfig.PortBindings}}'
        if ($LASTEXITCODE -ne 0 -or ($published -ne 'null' -and $published -ne '{}')) { throw '副本数据库或API存在主机发布端口，拒绝公开。' }
    }
    $webId = Invoke-Stack -Parameters @('ps','-q','web')
    $bindings = (& docker inspect $webId --format '{{json .HostConfig.PortBindings}}') | ConvertFrom-Json
    $ports = @($bindings.'80/tcp')
    if ($ports.Count -ne 1 -or $ports[0].HostIp -ne '127.0.0.1' -or $ports[0].HostPort -ne '18080') { throw '网页端口不是预期的本机18080，拒绝公开。' }
    $health = Invoke-RestMethod "$target/health" -TimeoutSec 15
    if ($health.status -ne 'ok') { throw '副本健康检查未通过。' }
}

Push-Location $projectDir
try {
    if ($Action -eq 'Prepare') {
        Protect-PrivateDirectory
        if (Test-Path -LiteralPath $markerPath) {
            Write-Output '副本已初始化，未重复复制数据、重置密码或覆盖密钥。使用LocalStart启动，Start公开。'
            return
        }
        if (-not (Test-Path -LiteralPath $envPath)) {
            $secretText = "PREVIEW_DB_PASSWORD=$(New-RandomSecret)`nPREVIEW_AUTH_SECRET=$(New-RandomSecret)`nPREVIEW_API_IMAGE=computer-course-rag-api:latest`nPREVIEW_WEB_IMAGE=computer-course-rag-web:public`n"
            Write-PrivateText $envPath $secretText
        }
        New-Item -ItemType Directory -Force -Path (Join-Path $projectDir 'backups/funnel'), (Join-Path $privateDir 'reports') | Out-Null
        # Export effective model settings only into an ACL-protected local transfer file.
        # Never print the JSON: it can include the existing provider credential.
        $exportCode = 'import json; from app.config import get_settings; from app.database import get_session_factory; from app.model_config import ModelConfigService; s=get_settings(); s=ModelConfigService(get_session_factory(),s.model_config_secret_path).load(s); fields=[k for k in type(s).model_fields if k.startswith(("llm_", "retrieval_", "embedding_"))]; print(json.dumps({k:getattr(s,k) for k in fields}))'
        $modelTransfer = & docker exec computer-course-rag-api-1 python -c $exportCode
        if ($LASTEXITCODE -ne 0) { throw '读取本机模型配置失败；没有输出或保存明文到公开位置。' }
        $effective = $modelTransfer | ConvertFrom-Json
        # Restored vectors require the exact source model, not merely a model
        # with the same output size. Keep these non-secret fields explicit.
        $environmentText = Get-Content -LiteralPath $envPath -Raw
        foreach ($field in @('provider','model','dimensions')) {
            $key = 'PREVIEW_EMBEDDING_' + $field.ToUpperInvariant()
            $value = [string]$effective.('embedding_' + $field)
            if (-not $value -or $value -match '[\r\n$"#]') { throw '检索模型配置无效，未创建副本。' }
            $line = "$key=$value"
            if ($environmentText -match "(?m)^$key=") {
                $environmentText = [regex]::Replace($environmentText, "(?m)^$key=[^\r\n]*", $line)
            } else { $environmentText = $environmentText.TrimEnd() + "`n$line`n" }
        }
        Write-PrivateText $envPath $environmentText
        Write-PrivateText (Join-Path $privateDir 'model-transfer.json') ($modelTransfer -join "`n")

        $seedState = Join-Path $privateDir 'seed-state.json'
        if (-not (Test-Path -LiteralPath $seedState)) {
            if (-not $SeedBackup) {
                $name = 'rag-funnel-seed-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump'
                $SeedBackup = & (Join-Path $PSScriptRoot 'backup_database.ps1') -Name $name
            }
            $source = (Resolve-Path -LiteralPath $SeedBackup).Path
            $allowed = [IO.Path]::GetFullPath((Join-Path $projectDir 'backups')) + [IO.Path]::DirectorySeparatorChar
            if (-not $source.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) { throw '种子备份必须在项目backups目录内。' }
            $checksum = "$source.sha256"
            if (-not (Test-Path -LiteralPath $checksum)) { throw '种子备份缺少校验文件。' }
            $expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0]
            if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expected) { throw '种子备份校验失败。' }
            $leaf = Split-Path -Leaf $source
            $copy = Join-Path $projectDir "backups/funnel/$leaf"
            if (-not (Test-Path -LiteralPath $copy)) { Copy-Item -LiteralPath $source -Destination $copy }
            if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne $expected) { throw '副本备份校验失败。' }
            Write-PrivateText $seedState (@{file=$leaf; sha256=$expected; restored=$false} | ConvertTo-Json)
        }
        $seed = Get-Content -LiteralPath $seedState -Raw | ConvertFrom-Json
        Invoke-Stack -Parameters @('config','--quiet')
        Invoke-Stack -Parameters @('up','-d','--wait','--wait-timeout','60','postgres')
        if (-not $seed.restored) {
            $tables = Invoke-Stack -Parameters @('exec','-T','postgres','psql','-U','rag_preview','-d','rag_preview','-Atc',"select count(*) from information_schema.tables where table_schema='public';")
            if ([int]$tables -ne 0) { throw '目标副本不是空库，拒绝覆盖。请检查此前恢复结果。' }
            Invoke-Stack -Parameters @('exec','-T','postgres','pg_restore','-U','rag_preview','-d','rag_preview','--no-owner','--no-acl',"/backups/$($seed.file)")
            $seed.restored = $true
            Write-PrivateText $seedState ($seed | ConvertTo-Json)
        }
        Invoke-Stack -Parameters @('run','--rm','--no-deps','bootstrap')
        if (-not (Test-Path -LiteralPath $markerPath)) { throw '副本加固标记未生成；不能公开。' }
        Write-Output "副本数据库已恢复并加固。账号清单仅保存在 $privateDir\accounts.json，请勿发送整份清单。"
        Write-Output '下一步构建内测网页镜像，再执行LocalStart核对；本命令不自动开放Funnel。'
        return
    }
    if (-not (Test-Path -LiteralPath $envPath)) { throw '请先执行Prepare。' }
    switch ($Action) {
        'Build' {
            $publicWebImage = 'computer-course-rag-web:public'
            $imageMatch = [regex]::Match((Get-Content -LiteralPath $envPath -Raw), '(?m)^PREVIEW_WEB_IMAGE=([^\r\n]+)')
            if ($imageMatch.Success) { $publicWebImage = $imageMatch.Groups[1].Value.Trim() }
            $savedFlag = $env:VITE_PUBLIC_PREVIEW
            Push-Location (Join-Path $projectDir 'frontend')
            try {
                $env:VITE_PUBLIC_PREVIEW = 'true'
                & npm.cmd run build
                if ($LASTEXITCODE -ne 0) { throw '内测前端构建失败。' }
                & docker build -t $publicWebImage .
                if ($LASTEXITCODE -ne 0) { throw '内测网页镜像构建失败。' }
            } finally {
                # The image already holds the public build. Leave local dist in
                # normal development mode, so a later local rebuild stays local.
                $env:VITE_PUBLIC_PREVIEW = $null
                & npm.cmd run build
                $restoreExit = $LASTEXITCODE
                $env:VITE_PUBLIC_PREVIEW = $savedFlag
                Pop-Location
                if ($restoreExit -ne 0) { throw '本机dist恢复失败，请清除VITE_PUBLIC_PREVIEW后重新构建。' }
            }
            Write-Output '内测镜像已构建，本机dist已恢复；未替换本机镜像或重置数据库。'
        }
        'LocalStart' { Invoke-Stack -Parameters @('up','-d','--no-build','postgres','api','web'); Write-Output "内测副本本机入口：$target" }
        'LocalStop' { Invoke-Stack -Parameters @('stop'); Write-Output '仅停止内测副本，数据卷保留。公开入口需另执行Stop关闭。' }
        'Start' {
            Assert-LocalReady
            if (-not (Test-Path -LiteralPath $tailscaleExe)) { throw '请先安装Tailscale。' }
            $state = (& $tailscaleExe status --json) | ConvertFrom-Json
            if ($state.BackendState -ne 'Running') { throw '请先登录并连接Tailscale。' }
            $null = Assert-OwnFunnel
            & $tailscaleExe funnel --bg --https=443 $target
            if ($LASTEXITCODE -ne 0) { throw 'Funnel尚未启用，请按提示完成账号侧授权后重试。' }
            $config = Assert-OwnFunnel
            $dns = $state.Self.DNSName.TrimEnd('.')
            $key = "${dns}:443"
            if (-not $config.AllowFunnel.$key) { throw '未确认公网开关开启，不将私有Serve当作公网部署成功。' }
            $url = "https://$dns/"
            Write-PrivateText (Join-Path $privateDir 'public-url.txt') $url
            Write-Output "已启用公网入口：$url"
        }
        'Stop' {
            if (-not (Test-Path -LiteralPath $tailscaleExe)) { throw 'Tailscale程序不存在。' }
            $null = Assert-OwnFunnel
            & $tailscaleExe funnel --bg --https=443 off
            if ($LASTEXITCODE -ne 0) { throw '未确认Funnel已关闭，请查看状态。' }
            Write-Output '已关闭本项目443公开入口，未删除数据库和账号。'
        }
        'Status' {
            Invoke-Stack -Parameters @('ps')
            if (Test-Path -LiteralPath $tailscaleExe) { & $tailscaleExe funnel status }
            if (Test-Path -LiteralPath $markerPath) { Get-Content -LiteralPath $markerPath }
        }
        'Backup' {
            $name = 'rag-funnel-preview-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump'
            Invoke-Stack -Parameters @('exec','-T','postgres','pg_dump','-U','rag_preview','-d','rag_preview','-Fc','--no-owner','--no-acl',"--file=/backups/$name")
            $path = Join-Path $projectDir "backups/funnel/$name"
            Write-PrivateText "$path.sha256" ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() + "  $name")
            Write-Output "备份已保存：$path。恢复模型配置还需要独立的preview_config卷，请同时保管。"
        }
    }
} finally { Pop-Location }
