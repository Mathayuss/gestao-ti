param()

$ErrorActionPreference = "Stop"
$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

function Fail($Message) {
  Write-Error $Message
  exit 1
}

function Read-EnvValue($Name) {
  if (-not (Test-Path ".env")) {
    Fail "Arquivo .env nao encontrado."
  }

  $pattern = "^\s*" + [regex]::Escape($Name) + "="
  foreach ($line in Get-Content ".env") {
    if ($line -match $pattern) {
      $value = $line.Substring($line.IndexOf("=") + 1).Trim()
      if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
      }
      return $value
    }
  }

  Fail "Variavel $Name nao encontrada no .env."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Fail "Docker nao encontrado."
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
  Fail "Docker Compose nao esta disponivel."
}

$PostgresDb = Read-EnvValue "POSTGRES_DB"
$PostgresUser = Read-EnvValue "POSTGRES_USER"
$PostgresPassword = Read-EnvValue "POSTGRES_PASSWORD"

if ([string]::IsNullOrWhiteSpace($PostgresDb)) { Fail "POSTGRES_DB vazio." }
if ([string]::IsNullOrWhiteSpace($PostgresUser)) { Fail "POSTGRES_USER vazio." }
if ([string]::IsNullOrWhiteSpace($PostgresPassword)) { Fail "POSTGRES_PASSWORD vazio." }

$SqlUser = $PostgresUser.Replace('"', '""')
$SqlPassword = $PostgresPassword.Replace("'", "''")
$Sql = "ALTER USER `"$SqlUser`" WITH PASSWORD '$SqlPassword';"

Write-Host "Ajustando senha do usuario PostgreSQL '$PostgresUser' conforme o .env..."
Write-Host "Parando app para interromper tentativas com senha antiga..."
docker compose stop app *> $null

docker compose exec -T postgres psql -U $PostgresUser -d $PostgresDb -v ON_ERROR_STOP=1 -c $Sql
if ($LASTEXITCODE -ne 0) {
  Fail "Falha ao ajustar a senha no PostgreSQL."
}

Write-Host "Validando autenticacao TCP com a senha do .env..."
docker compose exec -T -e "PGPASSWORD=$PostgresPassword" postgres psql -h 127.0.0.1 -U $PostgresUser -d $PostgresDb -v ON_ERROR_STOP=1 -c "SELECT 1;"
if ($LASTEXITCODE -ne 0) {
  Fail "A senha foi ajustada, mas a validacao TCP falhou."
}

Write-Host "Recriando app com a configuracao atual..."
docker compose up -d --build --force-recreate app
if ($LASTEXITCODE -ne 0) {
  Fail "Falha ao recriar o app. Verifique se a porta APP_PORT do .env esta livre e rode: docker compose logs --tail=80 app"
}

Write-Host "Senha ajustada e app recriado. Para acompanhar:"
Write-Host "docker compose logs --tail=80 app"
