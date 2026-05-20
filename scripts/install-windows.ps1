param(
  [switch]$Force,
  [switch]$Check
)

$ErrorActionPreference = "Stop"
$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

function Fail($Message) {
  Write-Error $Message
  exit 1
}

function New-RandomHex([int]$Bytes) {
  $buffer = New-Object byte[] $Bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
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

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Fail "Docker nao encontrado. Instale o Docker Desktop antes de continuar."
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
  Fail "Docker Compose nao esta disponivel. Atualize o Docker Desktop."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Fail "Docker nao esta rodando. Abra o Docker Desktop e tente novamente."
}

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
$DatabaseUrl = "postgresql+psycopg://$($PostgresUser):$($PostgresPassword)@postgres:5432/$($PostgresDb)"

$EnvContent = @"
SECRET_KEY=$SecretKey
DATABASE_URL=$DatabaseUrl
APP_BASE_URL=$AppBaseUrl
APP_PORT=$AppPort
FLASK_DEBUG=0
SESSION_SECURE=0
SHOW_DEMO_CREDENTIALS=0
AUTO_SEED_DEMO=0
SERVICE_NAME=ti-control-sre
BUILD_VERSION=local
ENVIRONMENT=local
SETUP_TOKEN=$SetupToken
WEB_CONCURRENCY=2
WEB_THREADS=4
GUNICORN_TIMEOUT=60
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
