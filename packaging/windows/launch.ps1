param([Parameter(ValueFromRemainingArguments = $true)][string[]] $IdeArguments)
. (Join-Path $PSScriptRoot 'common.ps1')
$state = Read-InstallState $PSScriptRoot
$active = Get-SafeChild $PSScriptRoot $state.current
$python = Get-SafeChild $active 'runtime/python.exe'
# The Start menu shortcut hides this parent console. A console interpreter also
# provides a reliable exit code, unlike PowerShell 5.1's asynchronous pythonw.
# Native argument forwarding preserves paths with spaces.
& $python -I -B -m openbexi_ide.app @IdeArguments
exit $LASTEXITCODE
