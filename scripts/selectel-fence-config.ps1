# В этой сессии должно быть загружено окружение selectel-env.ps1.
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not $env:OS_PROJECT_ID -or -not $env:OS_REGION_NAME -or -not $env:OS_USER_DOMAIN_NAME) {
    throw 'Сначала загрузите selectel-env.ps1.'
}
$taskSecret = Read-Host 'Пароль отдельного пользователя otus-dz04-fence' -AsSecureString
$taskPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecret)
$taskPreviousEncoding = $OutputEncoding
try {
    # Windows PowerShell 5.1 иначе передаёт native stdin в ASCII.
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $taskConfig = @{
        username = 'otus-dz04-fence'
        password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer)
        domain_name = $env:OS_USER_DOMAIN_NAME
        project_id = $env:OS_PROJECT_ID
        region = $env:OS_REGION_NAME
    }
    $taskConfig | ConvertTo-Json -Compress | & (Join-Path $taskRoot '.tools/venv/Scripts/python.exe') (Join-Path $taskRoot 'scripts/selectel-secrets.py')
    if ($LASTEXITCODE) { throw 'Подготовка fencing не выполнена; секреты скрыты.' }
} finally {
    $OutputEncoding = $taskPreviousEncoding
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer)
    $taskSecret.Dispose()
    $taskConfig = $null
}
