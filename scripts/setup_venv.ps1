# Создание venv и установка зависимостей PropRadar (Windows / PowerShell).
# Запуск из корня репозитория:  powershell -ExecutionPolicy Bypass -File .\scripts\setup_venv.ps1

$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python не найден в PATH. Установите Python 3.11+, затем повторите."
    exit 1
}

$versionLine = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$need = [version]'3.11'
$have = [version]$versionLine
if ($have -lt $need) {
    Write-Error "Требуется Python 3.11+, обнаружено: $versionLine"
    exit 1
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

if (-not (Test-Path ".\pyproject.toml")) {
    Write-Error "Не найден pyproject.toml. Запускайте скрипт из корня репозитория (через scripts/start)."
    exit 1
}

python -m venv .venv
& .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev]"

Write-Host "Устанавливаю браузеры Playwright (Chromium)..."
python -m playwright install chromium

Write-Host "Готово. Активация venv:  .\.venv\Scripts\Activate.ps1"
