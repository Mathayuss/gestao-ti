param(
  [switch]$Check,
  [switch]$NoPull,
  [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

function Fail($Message) {
  Write-Error $Message
  exit 1
}

function Get-EnvValue($Name, $Default) {
  if (-not (Test-Path ".env")) { return $Default }
  $line = Get-Content ".env" | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
  if (-not $line) { return $Default }
  return ($line -replace "^$Name=", "").Trim()
}

function Set-EnvValue($Name, $Value) {
  if (-not (Test-Path ".env")) { return }
  $lines = Get-Content ".env"
  $found = $false
  $updated = $lines | ForEach-Object {
    if ($_ -match "^$Name=") {
      $found = $true
      "$Name=$Value"
    } else {
      $_
    }
  }
  if (-not $found) {
    $updated += "$Name=$Value"
  }
  $Utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText((Join-Path $RootDir ".env"), ($updated -join "`n") + "`n", $Utf8NoBom)
}

function Test-Command($Name) {
  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-AppBackup() {
  $running = docker compose ps --status running --services 2>$null
  if ($running -notcontains "app") {
    Write-Host "Aviso: container app nao esta em execucao; backup pela aplicacao foi pulado."
    return
  }

  Write-Host "Gerando backup pre-atualizacao..."
  docker compose exec -T app python -c "from app import app, _write_backup_file; app.app_context().push(); result=_write_backup_file('manual', generated_by='update_script'); print(result.get('filename','backup gerado'))"
}

function Wait-Ready() {
  Write-Host "Aguardando aplicacao ficar pronta..."
  for ($i = 1; $i -le 30; $i++) {
    docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/ready', timeout=3).read()" *> $null
    if ($LASTEXITCODE -eq 0) {
      Write-Host "OK: aplicacao pronta."
      return
    }
    Start-Sleep -Seconds 2
  }
  Fail "Aplicacao nao ficou pronta dentro do tempo esperado. Verifique: docker compose logs app"
}

if (-not (Test-Command "docker")) {
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
if (-not (Test-Path ".env")) {
  Fail "Arquivo .env nao encontrado. Execute a instalacao antes de atualizar."
}

if ($Check) {
  Write-Host "OK: Docker, Docker Compose e .env disponiveis."
  Write-Host "OK: atualizador Windows pronto para executar."
  exit 0
}

if (-not $NoPull) {
  if (-not (Test-Command "git")) {
    Fail "Git nao encontrado. Instale o Git ou execute com -NoPull apos copiar a nova versao."
  }
  $dirty = git status --porcelain
  if ($dirty -and -not $AllowDirty) {
    Fail "Existem alteracoes locais. Salve/commite antes de atualizar, ou use -AllowDirty se souber o que esta fazendo."
  }
}

Write-Host ""
Write-Host "TI Control - atualizacao"
Write-Host ""

$previousVersion = Get-EnvValue "BUILD_VERSION" "1.3.5"
Write-Host "Versao atual declarada: $previousVersion"

Invoke-AppBackup

if (-not $NoPull) {
  Write-Host "Baixando ultima versao do repositorio..."
  git pull --ff-only
}

$newVersion = "1.3.5"
if (Test-Path "VERSION") {
  $newVersion = (Get-Content "VERSION" -Raw).Trim()
} elseif (Test-Command "git") {
  $newVersion = (git rev-parse --short HEAD).Trim()
}
Set-EnvValue "BUILD_VERSION" $newVersion

Write-Host "Recriando container da aplicacao..."
docker compose build app
docker compose up -d app postgres

Wait-Ready

Write-Host ""
Write-Host "Atualizacao concluida."
Write-Host "Versao aplicada: $newVersion"
Write-Host "URL local: http://localhost:$(Get-EnvValue 'APP_PORT' '5000')"
Write-Host ""
