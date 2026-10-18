# Отдельная конфигурация и state Selectel. Credentials берутся только из OS_*.
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskTerraform = Join-Path $taskRoot '.tools/terraform.exe'
$taskPreviousConfig = $env:TF_CLI_CONFIG_FILE
try {
    $env:TF_CLI_CONFIG_FILE = Join-Path $taskRoot 'terraform-selectel.rc'
    & $taskTerraform "-chdir=$taskRoot/terraform-selectel" @args
    exit $LASTEXITCODE
} finally {
    $env:TF_CLI_CONFIG_FILE = $taskPreviousConfig
}
