# Полный проверочный цикл нового стенда; платные ресурсы удаляются и при ошибке.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.tools/venv/Scripts/python.exe'
$taskRun = Join-Path $taskRoot ('.local/selectel/runs/' + [DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss'))
if (-not $env:OS_PASSWORD) { throw 'Сначала загрузите окружение оператора через selectel-env.ps1.' }
$taskStateText = & (Join-Path $taskRoot '.tools/terraform.exe') "-chdir=$taskRoot/terraform-selectel" show -json
if ($LASTEXITCODE) { throw 'Не удалось проверить исходный state.' }
$taskState = ($taskStateText -join "`n") | ConvertFrom-Json
if (@($taskState.values.root_module.resources | Where-Object { $_.mode -eq 'managed' }).Count) {
    throw 'Проверочный цикл требует пустого state. Существующий стенд не изменён.'
}
$taskStarted = [DateTimeOffset]::UtcNow
New-Item -ItemType Directory -Path $taskRun -Force | Out-Null
$taskPassed = $false
$taskCleaned = $false
$taskFailure = $null
$taskPowerShell = (Get-Process -Id $PID).Path
function Invoke-ReproductionStep {
    param([string]$Name, [string]$Script, [string[]]$Parameters)
    & $taskPython (Join-Path $taskRoot 'scripts/run_logged.py') --log (Join-Path $taskRun ($Name + '.log')) $taskPython (Join-Path $taskRoot $Script) @Parameters
    if ($LASTEXITCODE) { throw "Проверка $Name завершилась ошибкой." }
}
Push-Location $taskRoot
try {
    & $taskPython (Join-Path $taskRoot 'scripts/run_logged.py') --log (Join-Path $taskRun 'deploy.log') $taskPowerShell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'selectel-deploy.ps1') -CreateResources
    if ($LASTEXITCODE) { throw 'Развёртывание не завершено; подробности в deploy.log.' }
    Invoke-ReproductionStep 'fencing' 'scripts/verify_selectel_fencing.py' @('--empty-storage')
    Invoke-ReproductionStep 'initialize' 'scripts/controller.py' @('--cloud','selectel','run','initialize.yml','-e','allow_experimental_storage=true','-e','initialize_storage=true','-e','fencing_verified=true')
    Invoke-ReproductionStep 'activate' 'scripts/controller.py' @('--cloud','selectel','run','activate.yml')
    Invoke-ReproductionStep 'verify-initial' 'scripts/controller.py' @('--cloud','selectel','run','verify.yml')
    Invoke-ReproductionStep 'repeat-site' 'scripts/controller.py' @('--cloud','selectel','run','site.yml','-e','allow_experimental_storage=true')
    Invoke-ReproductionStep 'activate-update' 'scripts/controller.py' @('--cloud','selectel','run','activate.yml')
    Invoke-ReproductionStep 'verify-repeat' 'scripts/controller.py' @('--cloud','selectel','run','verify.yml')
    Invoke-ReproductionStep 'failures' 'scripts/verify_selectel_failures.py' @()
    Invoke-ReproductionStep 'partition' 'scripts/verify_selectel_partition.py' @()
    $taskPassed = $true
} catch {
    @($_.ToString(), $_.ScriptStackTrace) | Set-Content -LiteralPath (Join-Path $taskRun 'failure.log') -Encoding UTF8
    $taskFailure = $_
} finally {
    try {
        foreach ($taskName in @('fencing-results.json','failure-results.json','partition-results.json')) {
            $taskFile = Join-Path $taskRoot ('.local/selectel/' + $taskName)
            if ((Test-Path -LiteralPath $taskFile) -and (Get-Item -LiteralPath $taskFile).LastWriteTimeUtc -ge $taskStarted.UtcDateTime) {
                Copy-Item -LiteralPath $taskFile -Destination $taskRun
            }
        }
        & $taskPython (Join-Path $taskRoot 'scripts/run_logged.py') --log (Join-Path $taskRun 'cleanup.log') $taskPowerShell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'selectel-cleanup.ps1')
        if ($LASTEXITCODE -eq 0) {
            Copy-Item -LiteralPath (Join-Path $taskRoot '.local/selectel/cleanup-result.json') -Destination $taskRun
            $taskCleaned = $true
        }
    } finally {
        @{checks_passed=$taskPassed; cleanup_success=$taskCleaned; time_utc=[DateTimeOffset]::UtcNow.ToString('o')} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'result.json') -Encoding UTF8
        Write-Host "Результаты цикла сохранены: $taskRun"
        Pop-Location
    }
}
if (-not $taskCleaned) { throw 'Удаление не подтверждено. Проверьте cleanup.log и state; ресурсы могут оставаться платными.' }
if ($taskFailure) { throw $taskFailure }
Write-Host 'Полный цикл успешно завершён: проверки прошли, ресурсы удалены.'
