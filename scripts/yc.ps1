# Передаёт аргументы YC CLI, всегда запрещая автоматический запуск браузера.
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskYcConfig = if ($env:OTUS_YC_CONFIG) { $env:OTUS_YC_CONFIG } else { Join-Path $taskRoot '.local/yc-config.yaml' }
& (Join-Path $taskRoot '.tools/yc.exe') --no-browser --config $taskYcConfig @args
exit $LASTEXITCODE
