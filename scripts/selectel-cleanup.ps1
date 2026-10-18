# Удаляет только ресурсы отдельного state Selectel после проверок.
param([switch]$WaitForChecks)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskLocal = Join-Path $taskRoot '.local/selectel'
$taskDiscovery = Get-Content -LiteralPath (Join-Path $taskLocal 'discovery.json') -Raw | ConvertFrom-Json
if ($env:OS_PROJECT_ID -ne $taskDiscovery.project_id -or $env:OS_REGION_NAME -ne $taskDiscovery.region -or -not $env:OS_PASSWORD) {
    throw 'Нужна авторизация оператора для проверенного проекта Selectel: загрузите selectel-env.ps1.'
}
$taskTerraform = Join-Path $taskRoot '.tools/terraform.exe'
$taskConfig = $env:TF_CLI_CONFIG_FILE
$taskStarted = [DateTimeOffset]::UtcNow
try {
    $env:TF_CLI_CONFIG_FILE = Join-Path $taskRoot 'terraform-selectel.rc'
    if ($WaitForChecks) {
        Write-Host 'Жду завершения проверок. После маркера автоматически удалю ресурсы state Selectel.'
        $taskMarkerPath = Join-Path $taskLocal 'checks-finished.json'
        while ($true) {
            if (Test-Path -LiteralPath $taskMarkerPath) {
                $taskMarker = Get-Content -LiteralPath $taskMarkerPath -Raw | ConvertFrom-Json
                if ($taskMarker.project_id -eq $taskDiscovery.project_id -and $taskMarker.cleanup_ready -eq $true -and
                    [DateTimeOffset]::Parse($taskMarker.time_utc) -ge $taskStarted) { break }
            }
            if (([DateTimeOffset]::UtcNow - $taskStarted).TotalHours -gt 2) {
                throw 'За два часа маркер не получен. Ресурсы НЕ удалены; требуется проверка и ручной повтор очистки.'
            }
            Start-Sleep -Seconds 15
        }
    }
    $taskDestroyPlan = Join-Path $taskLocal 'destroy.tfplan'
    & $taskTerraform "-chdir=$taskRoot/terraform-selectel" plan -destroy "-out=$taskDestroyPlan" -no-color
    if ($LASTEXITCODE) { throw 'Destroy plan не сформирован; ничего не удалено.' }
    $taskPlanText = & $taskTerraform "-chdir=$taskRoot/terraform-selectel" show -json $taskDestroyPlan
    if ($LASTEXITCODE) { throw 'Не удалось прочитать destroy plan.' }
    $taskPlan = ($taskPlanText -join "`n") | ConvertFrom-Json
    $taskManaged = @($taskPlan.resource_changes | Where-Object { $_.mode -eq 'managed' })
    foreach ($taskResource in $taskManaged) {
        if ($taskResource.type -notlike 'openstack_*' -or
            (@($taskResource.change.actions) -join ',') -notin @('delete', 'no-op')) {
            throw 'Неожиданные действия в destroy plan; удаление остановлено.'
        }
        $taskTenant = $taskResource.change.before.tenant_id
        if ($taskTenant -and $taskTenant -ne $taskDiscovery.project_id) {
            throw 'Ресурс принадлежит другому проекту; удаление остановлено.'
        }
    }
    & $taskTerraform "-chdir=$taskRoot/terraform-selectel" apply -no-color $taskDestroyPlan
    if ($LASTEXITCODE) { throw 'Удаление выполнено частично. Сохраните state и повторите очистку после проверки.' }
    $taskStateText = & $taskTerraform "-chdir=$taskRoot/terraform-selectel" show -json
    if ($LASTEXITCODE) { throw 'Не удалось проверить state после удаления.' }
    $taskState = ($taskStateText -join "`n") | ConvertFrom-Json
    $taskRemaining = @($taskState.values.root_module.resources | Where-Object { $_.mode -eq 'managed' })
    if ($taskRemaining.Count -gt 0) { throw 'В state остались управляемые ресурсы.' }
    @{project_id=$taskDiscovery.project_id; time_utc=[DateTimeOffset]::UtcNow.ToString('o'); managed_remaining=0; success=$true} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskLocal 'cleanup-result.json') -Encoding UTF8
    Write-Host 'Ресурсы state Selectel удалены. Исходники, отчёты, проект и сервисные пользователи сохранены.'
} finally {
    $env:TF_CLI_CONFIG_FILE = $taskConfig
}
