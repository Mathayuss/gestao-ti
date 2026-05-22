param(
  [switch]$Force,
  [switch]$Check,
  [switch]$InstallDocker
)

$ErrorActionPreference = "Stop"
$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

function Fail($Message) {
  Write-Error $Message
  exit 1
}

function Test-Command($Name) {
  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-DockerDesktopPath {
  $paths = @()
  if ($env:ProgramFiles) {
    $paths += (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe")
  }
  $ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  if ($ProgramFilesX86) {
    $paths += (Join-Path $ProgramFilesX86 "Docker\Docker\Docker Desktop.exe")
  }
  if ($env:LOCALAPPDATA) {
    $paths += (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
  }

  foreach ($path in $paths) {
    if ($path -and (Test-Path $path)) {
      return $path
    }
  }
  return $null
}

function Add-DockerCliToPath {
  $paths = @()
  if ($env:ProgramFiles) {
    $paths += (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin")
  }
  $ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  if ($ProgramFilesX86) {
    $paths += (Join-Path $ProgramFilesX86 "Docker\Docker\resources\bin")
  }

  foreach ($path in $paths) {
    if ($path -and (Test-Path (Join-Path $path "docker.exe")) -and ($env:Path -notlike "*$path*")) {
      $env:Path = "$env:Path;$path"
    }
  }
}

function Show-DockerInstallHelp {
  Write-Host ""
  Write-Host "Docker Desktop nao foi encontrado."
  Write-Host "Instale o Docker Desktop, abra-o uma vez e execute este instalador novamente."
  Write-Host ""
  if (Test-Command "winget") {
    Write-Host "Opcao automatica:"
    Write-Host "  .\scripts\install-windows.ps1 -InstallDocker"
    Write-Host ""
    Write-Host "Ou manualmente:"
    Write-Host "  winget install -e --id Docker.DockerDesktop"
  } else {
    Write-Host "Instale manualmente pelo site oficial do Docker Desktop."
  }
  Write-Host ""
}

function Install-DockerDesktop {
  if (-not (Test-Command "winget")) {
    Show-DockerInstallHelp
    Fail "winget nao encontrado. Instale o Docker Desktop manualmente e execute novamente."
  }

  Write-Host ""
  Write-Host "Instalando Docker Desktop via winget..."
  winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) {
    Fail "Falha ao instalar Docker Desktop via winget."
  }

  Write-Host ""
  Write-Host "Docker Desktop instalado."
  Write-Host "Abra o Docker Desktop, finalize a configuracao inicial e execute este instalador novamente."
  Write-Host "Pode ser necessario reiniciar o Windows ou o PowerShell."
  exit 0
}

function Wait-DockerReady {
  Write-Host "Aguardando Docker Desktop ficar pronto..."
  for ($i = 1; $i -le 60; $i++) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
      Write-Host "OK: Docker Desktop em execucao."
      return
    }
    Start-Sleep -Seconds 3
  }
  Fail "Docker nao ficou pronto dentro do tempo esperado. Abra o Docker Desktop e tente novamente."
}

function Ensure-Docker {
  Add-DockerCliToPath

  if (-not (Test-Command "docker")) {
    $dockerDesktop = Get-DockerDesktopPath
    if ($dockerDesktop) {
      Write-Host ""
      Write-Host "Docker Desktop parece estar instalado, mas o comando docker nao esta disponivel nesta sessao."
      Write-Host "Feche e abra o PowerShell novamente, ou reinicie o Windows se a instalacao acabou de ser feita."
      Write-Host "Depois execute: .\scripts\install-windows.ps1"
      exit 1
    }
    if ($InstallDocker) {
      Install-DockerDesktop
    }
    if (-not $Check) {
      $installNow = Read-Host "Docker Desktop nao encontrado. Instalar via winget agora? [s/N]"
      if ($installNow -match "^[sS]$") {
        Install-DockerDesktop
      }
    }
    Show-DockerInstallHelp
    Fail "Docker Desktop e obrigatorio para instalar o TI Control."
  }

  docker compose version *> $null
  if ($LASTEXITCODE -ne 0) {
    Fail "Docker Compose nao esta disponivel. Atualize o Docker Desktop."
  }

  docker info *> $null
  if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = Get-DockerDesktopPath
    if ($dockerDesktop) {
      Write-Host "Docker instalado, mas nao esta em execucao. Abrindo Docker Desktop..."
      Start-Process $dockerDesktop
      Wait-DockerReady
      return
    }
    Fail "Docker nao esta rodando. Abra o Docker Desktop e tente novamente."
  }
}

function New-RandomHex([int]$Bytes) {
  $buffer = New-Object byte[] $Bytes
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $rng.GetBytes($buffer)
  } finally {
    if ($null -ne $rng) {
      $rng.Dispose()
    }
  }
  return -join ($buffer | ForEach-Object { $_.ToString("x2") })
}

function Read-Default($Label, $Default) {
  $value = Read-Host "$Label [$Default]"
  if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
  return $value.Trim()
}

function Test-PortInUse([int]$Port) {
  $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  return $null -ne $connection
}

function Assert-Port($Value, $Label) {
  $parsed = 0
  if (-not [int]::TryParse($Value, [ref]$parsed)) {
    Fail "$Label deve ser numerica."
  }
  if ($parsed -lt 1 -or $parsed -gt 65535) {
    Fail "$Label deve estar entre 1 e 65535."
  }
}

function Assert-PostgresIdentifier($Value, $Label) {
  if ($Value -notmatch "^[A-Za-z_][A-Za-z0-9_]{1,62}$") {
    Fail "$Label deve ter 2 a 63 caracteres e usar letras, numeros ou underline, iniciando por letra/underline."
  }
}

function Assert-Url($Value) {
  if ($Value -notmatch "^https?://\S+$") {
    Fail "URL publica deve comecar com http:// ou https://."
  }
}

Ensure-Docker

if ($Check) {
  Write-Host "OK: Docker e Docker Compose disponiveis."
  Write-Host "OK: instalador Windows pronto para executar."
  exit 0
}

if ((Test-Path ".env") -and -not $Force) {
  $overwrite = Read-Host "Arquivo .env ja existe. Sobrescrever? [s/N]"
  if ($overwrite -notmatch "^[sS]$") {
    Fail "Instalacao cancelada para preservar o .env atual."
  }
}

Write-Host ""
Write-Host "TI Control - instalacao com PostgreSQL"
Write-Host ""

$AppPort = Read-Default "Porta web da aplicacao" "5000"
$PostgresPort = Read-Default "Porta local do PostgreSQL" "5432"
$PostgresDb = Read-Default "Nome do banco" "ticontrol_db"
$PostgresUser = Read-Default "Usuario do banco" "ticontrol"
$AppBaseUrl = Read-Default "URL publica" "http://localhost:$AppPort"

Assert-Port $AppPort "Porta web"
Assert-Port $PostgresPort "Porta PostgreSQL"
Assert-PostgresIdentifier $PostgresDb "Nome do banco"
Assert-PostgresIdentifier $PostgresUser "Usuario do banco"
Assert-Url $AppBaseUrl

if (Test-PortInUse ([int]$AppPort)) {
  Fail "A porta web $AppPort ja esta em uso."
}
if (Test-PortInUse ([int]$PostgresPort)) {
  Fail "A porta PostgreSQL $PostgresPort ja esta em uso."
}

$PostgresPassword = New-RandomHex 24
$SecretKey = New-RandomHex 32
$SetupToken = New-RandomHex 18
$SessionSecure = if ($AppBaseUrl -match "^https://") { "1" } else { "0" }

$EnvContent = @"
SECRET_KEY=$SecretKey
APP_BASE_URL=$AppBaseUrl
APP_PORT=$AppPort
FLASK_DEBUG=0
SESSION_SECURE=$SessionSecure
SHOW_DEMO_CREDENTIALS=0
AUTO_SEED_DEMO=0
SERVICE_NAME=ti-control
BUILD_VERSION=0.1.1-BETA
ENVIRONMENT=local
SETUP_TOKEN=$SetupToken
WEB_CONCURRENCY=2
WEB_THREADS=4
GUNICORN_TIMEOUT=60
SELF_UPDATE_ENABLED=1
SELF_UPDATE_AUTO_RESTART=1
METRICS_TOKEN=
SMTP_ENABLED=0
POSTGRES_DB=$PostgresDb
POSTGRES_USER=$PostgresUser
POSTGRES_PASSWORD=$PostgresPassword
POSTGRES_PORT=$PostgresPort
"@

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path $RootDir ".env"), $EnvContent, $Utf8NoBom)

Write-Host ""
Write-Host "Subindo containers..."
docker compose up -d --build app postgres

Write-Host ""
Write-Host "Instalacao iniciada."
Write-Host "Acesse: $AppBaseUrl/setup?token=$SetupToken"
Write-Host ""
Write-Host "Guarde este token ate finalizar o assistente:"
Write-Host $SetupToken
Write-Host ""
