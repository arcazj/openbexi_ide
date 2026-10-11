param(
    [string]$Project = "",
    [string]$File = "",
    [ValidateSet("light", "dark")][string]$Theme = "light",
    [string]$SessionInfo = "",
    [Alias("User")][string]$SessionUser = $env:USERNAME,
    [ValidateSet("developer", "monitor")][string]$Role = "developer"
)
$ErrorActionPreference = "Stop"
$taskRepoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$taskPython = Join-Path $taskRepoRoot ".venv/Scripts/pythonw.exe"
if (!(Test-Path -LiteralPath $taskPython)) {
    throw "Run install.ps1 with CPython 3.13 first."
}
# Start-Process flattens ArgumentList on Windows. Quote each validated path with
# literal double quotes; no shell receives or evaluates the script arguments.
function Format-TaskPath([string]$Value) {
    if ($Value.Contains('"') -or $Value.Contains([char]0)) { throw "Invalid path." }
    $taskQuotedPath = [regex]::Replace($Value, '(\\+)$', '$1$1')
    return '"' + $taskQuotedPath + '"'
}
$taskArguments = @("-I", "-m", "openbexi_ide", "--theme", $Theme)
if ($Project) {
    $taskProjectPath = (Resolve-Path -LiteralPath $Project).Path
    if (!(Test-Path -LiteralPath $taskProjectPath -PathType Container)) { throw "Project must be a folder." }
    $taskArguments += @("--project", (Format-TaskPath $taskProjectPath))
}
if ($File) {
    if (!$Project) { throw "Supply -Project when opening a file." }
    $taskFilePath = (Resolve-Path -LiteralPath $File).Path
    $taskArguments += @("--file", (Format-TaskPath $taskFilePath))
}
if ($SessionInfo) {
    $taskSessionPath = (Resolve-Path -LiteralPath $SessionInfo).Path
    $taskArguments += @("--session-info", (Format-TaskPath $taskSessionPath),
                        "--user", (Format-TaskPath $SessionUser), "--role", $Role)
}
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList $taskArguments -WorkingDirectory $taskRepoRoot -WindowStyle Hidden -PassThru
Write-Output "OpenBEXI IDE desktop started (PID $($taskProcess.Id))."
