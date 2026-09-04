#Requires -Version 5.1
<#
.SYNOPSIS
  从 Windows 开发机同步代码到 47.95.5.18 并触发远程部署

.DESCRIPTION
  1. 读取 scripts/deploy/deploy.config（或 deploy.config.example）
  2. 使用 scp 同步项目到服务器（排除 .git、node_modules 等）
  3. SSH 执行 deploy_prod.sh

.PARAMETER Mode
  远程部署模式，默认 backend（仅重建后端）

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/deploy/push_and_deploy.ps1
  powershell -ExecutionPolicy Bypass -File scripts/deploy/push_and_deploy.ps1 -Mode all
  powershell -ExecutionPolicy Bypass -File scripts/deploy/push_and_deploy.ps1 -Mode backend -SkipSync
#>

param(
    [ValidateSet('all', 'backend', 'frontend', 'up', 'status', 'health')]
    [string]$Mode = 'backend',
    [switch]$SkipSync
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir '..\..')
$ConfigFile = Join-Path $ScriptDir 'deploy.config'
$ConfigExample = Join-Path $ScriptDir 'deploy.config.example'

function Load-DeployConfig {
    param([string]$Path)
    $cfg = @{}
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $idx = $line.IndexOf('=')
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        $cfg[$key] = $val
    }
    return $cfg
}

if (-not (Test-Path $ConfigFile)) {
    if (Test-Path $ConfigExample) {
        Copy-Item $ConfigExample $ConfigFile
        Write-Host "已创建 $ConfigFile ，请按需修改后重新运行" -ForegroundColor Yellow
        exit 1
    }
    throw "缺少配置文件: $ConfigFile"
}

$cfg = Load-DeployConfig $ConfigFile
$DeployHost = $cfg['DEPLOY_HOST']
$DeployUser = $cfg['DEPLOY_USER']
$DeployPort = if ($cfg['DEPLOY_PORT']) { $cfg['DEPLOY_PORT'] } else { '22' }
$DeployPath = $cfg['DEPLOY_PATH']
$PublicUrl = if ($cfg['PUBLIC_URL']) { $cfg['PUBLIC_URL'] } else { "http://$DeployHost" }
$ComposeFile = if ($cfg['COMPOSE_FILE']) { $cfg['COMPOSE_FILE'] } else { 'docker-compose.hub.nginx.47.yml' }
$ComposeOverride = $cfg['COMPOSE_OVERRIDE']
$SshKey = $cfg['SSH_KEY']

if (-not $DeployHost -or -not $DeployUser -or -not $DeployPath) {
    throw "deploy.config 须配置 DEPLOY_HOST、DEPLOY_USER、DEPLOY_PATH"
}

$sshTarget = "${DeployUser}@${DeployHost}"
$sshArgs = @('-p', $DeployPort, '-o', 'StrictHostKeyChecking=accept-new')
$scpArgs = @('-P', $DeployPort, '-o', 'StrictHostKeyChecking=accept-new')
if ($SshKey -and (Test-Path $SshKey)) {
    $sshArgs += @('-i', $SshKey)
    $scpArgs += @('-i', $SshKey)
}

function Invoke-Ssh {
    param([string]$Command)
    & ssh @sshArgs $sshTarget $Command
    if ($LASTEXITCODE -ne 0) { throw "SSH 失败: $Command" }
}

function Sync-Project {
    Write-Host "==> 同步代码到 ${sshTarget}:${DeployPath}" -ForegroundColor Cyan

    $staging = Join-Path $env:TEMP ("ares-deploy-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $staging -Force | Out-Null

    $excludeDirs = @('.git', 'node_modules', 'frontend\node_modules', 'miniprogram\node_modules', '__pycache__', '.pytest_cache', 'release', 'dist', '.cursor')
    $robocopyArgs = @(
        $ProjectRoot,
        $staging,
        '/MIR',
        '/NFL', '/NDL', '/NJH', '/NJS', '/nc', '/ns', '/np'
    )
    foreach ($d in $excludeDirs) {
        $robocopyArgs += '/XD'
        $robocopyArgs += (Join-Path $ProjectRoot $d)
    }

    & robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy 同步失败，exit=$LASTEXITCODE" }

    Invoke-Ssh "mkdir -p '$DeployPath'"
    & scp @scpArgs -r "$staging\*" "${sshTarget}:${DeployPath}/"
    if ($LASTEXITCODE -ne 0) { throw 'scp 上传失败' }

    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "==> 同步完成" -ForegroundColor Green
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Ares 推送部署 -> $DeployHost" -ForegroundColor Cyan
Write-Host " 模式: $Mode" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if (-not $SkipSync) {
    Sync-Project
} else {
    Write-Host "跳过同步（-SkipSync）" -ForegroundColor Yellow
}

$remoteCmd = @(
    "cd '$DeployPath'",
    "chmod +x scripts/deploy/deploy_prod.sh scripts/deploy/pull_base_images.sh",
    "export COMPOSE_FILE='$ComposeFile'",
    $(if ($ComposeOverride) { "export COMPOSE_OVERRIDE='$ComposeOverride'" }),
    "export PUBLIC_URL='$PublicUrl'",
    "./scripts/deploy/deploy_prod.sh $Mode"
) | Where-Object { $_ } -join ' && '

Write-Host "==> 远程执行部署..." -ForegroundColor Cyan
Invoke-Ssh $remoteCmd

Write-Host ""
Write-Host "部署完成" -ForegroundColor Green
Write-Host "  运营后台: $PublicUrl" -ForegroundColor White
Write-Host "  API 健康: ${PublicUrl}/api/health" -ForegroundColor White
Write-Host "  信号接口: ${PublicUrl}/api/ares/signal" -ForegroundColor White
Write-Host "  小程序 BASE_URL 请设为: $PublicUrl" -ForegroundColor Yellow
