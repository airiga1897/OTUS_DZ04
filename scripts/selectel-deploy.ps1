# Создание только явно запрошенного стенда Selectel; инициализация GFS2 отдельная.
param([switch]$CreateResources)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.tools/venv/Scripts/python.exe'
$taskDiscovery = Get-Content -LiteralPath (Join-Path $taskRoot '.local/selectel/discovery.json') -Raw | ConvertFrom-Json
if ($env:OS_PROJECT_ID -ne $taskDiscovery.project_id -or $env:OS_REGION_NAME -ne $taskDiscovery.region -or -not $env:OS_PASSWORD) {
    throw 'Загрузите selectel-env.ps1 для проверенного проекта и региона.'
}
if (-not (Test-Path -LiteralPath (Join-Path $taskRoot '.local/selectel/secrets.yml'))) {
    throw 'Сначала выполните selectel-fence-config.ps1 с отдельным пользователем fencing.'
}
function Invoke-TaskStep {
    param([string]$Script, [string[]]$Parameters)
    & $taskPython (Join-Path $taskRoot $Script) @Parameters
    if ($LASTEXITCODE) { throw "Шаг $Script завершился ошибкой. Проверьте состояние ресурсов; автоматического удаления нет." }
}
Invoke-TaskStep 'scripts/selectel_admin_access.py' @()
Invoke-TaskStep 'scripts/selectel_preflight.py' @()
if ($CreateResources) {
    Invoke-TaskStep 'scripts/selectel_provision.py' @('--apply')
} else {
    Invoke-TaskStep 'scripts/selectel_provision.py' @()
    Write-Host 'План проверен. Для создания используйте -CreateResources.'
    return
}
Invoke-TaskStep 'scripts/controller.py' @('--cloud', 'selectel', 'prepare')
Invoke-TaskStep 'scripts/controller.py' @('--cloud', 'selectel', 'run', 'site.yml', '--syntax-check')
Invoke-TaskStep 'scripts/controller.py' @('--cloud', 'selectel', 'run', 'site.yml', '-e', 'allow_experimental_storage=true')
Write-Host 'Пакеты и конфигурации установлены. Диски не форматировались; далее нужна проверка fencing перед initialize.yml.'
