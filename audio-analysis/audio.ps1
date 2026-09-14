param([Parameter(ValueFromRemainingArguments=$true)][string[]]$AudioArgs)
$ErrorActionPreference='Stop'
$previousEncoding=[Console]::OutputEncoding
try {
    [Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
    & (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'analyze.py') @AudioArgs
    $audioExit=$LASTEXITCODE
} finally { [Console]::OutputEncoding=$previousEncoding }
exit $audioExit
