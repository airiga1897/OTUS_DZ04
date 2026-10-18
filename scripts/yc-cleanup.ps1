# Удаление только ресурсов ДЗ04 из собственного state Yandex Cloud.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.tools/venv/Scripts/python.exe'
$taskPlan = Join-Path $taskRoot '.local/yc-destroy.tfplan'
& $taskPython (Join-Path $taskRoot 'scripts/tf.py') plan -destroy "-out=$taskPlan" -no-color
if ($LASTEXITCODE) { throw 'Destroy-план YC не создан; ресурсы не удалялись.' }
$taskPlanText = & $taskPython (Join-Path $taskRoot 'scripts/tf.py') show -json $taskPlan
if ($LASTEXITCODE) { throw 'Не удалось проверить destroy-план YC.' }
$taskPlanData = ($taskPlanText -join "`n") | ConvertFrom-Json
$taskChanges = $taskPlanData.resource_changes
foreach ($taskResource in @($taskChanges | Where-Object { $_.mode -eq 'managed' })) {
    if ($taskResource.type -notlike 'yandex_*' -or
        (@($taskResource.change.actions) -join ',') -notin @('delete','no-op')) {
        throw 'Неожиданные действия в плане; удаление остановлено.'
    }
    $taskBefore = $taskResource.change.before
    if (($taskBefore.folder_id -and $taskBefore.folder_id -ne $taskPlanData.variables.folder_id.value) -or
        ($taskBefore.name -and -not $taskBefore.name.StartsWith($taskPlanData.variables.name_prefix.value))) {
        throw 'Ресурс другого каталога или проекта; удаление остановлено.'
    }
}
& $taskPython (Join-Path $taskRoot 'scripts/tf.py') apply -no-color $taskPlan
if ($LASTEXITCODE) { throw 'Удаление YC не завершено. State сохранён; требуется проверка.' }
$taskStateText = & $taskPython (Join-Path $taskRoot 'scripts/tf.py') show -json
if ($LASTEXITCODE) { throw 'Не удалось проверить state YC.' }
$taskState = ($taskStateText -join "`n") | ConvertFrom-Json
if (@($taskState.values.root_module.resources | Where-Object { $_.mode -eq 'managed' }).Count) {
    throw 'В state YC остались ресурсы.'
}
@{success=$true; managed_remaining=0; time_utc=[DateTimeOffset]::UtcNow.ToString('o')} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot '.local/yc-cleanup-result.json') -Encoding UTF8
Write-Host 'Ресурсы ДЗ04 в Yandex Cloud удалены; state пуст.'
