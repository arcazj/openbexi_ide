param(
    [string]$Python = "python.exe",
    [string]$Wheelhouse = ""
)
$ErrorActionPreference = "Stop"
$taskRepoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$taskEnvironment = Join-Path $taskRepoRoot ".venv"
$taskInterpreter = Join-Path $taskEnvironment "Scripts/python.exe"

$taskVersion = & $Python -I -c "import sys;print('.'.join(map(str,sys.version_info[:2])))"
if ($LASTEXITCODE -ne 0 -or $taskVersion.Trim() -ne "3.13") {
    throw "Pass -Python with the path to a CPython 3.13 interpreter."
}
if (!(Test-Path -LiteralPath $taskInterpreter)) {
    & $Python -I -m venv $taskEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Could not create the desktop virtual environment." }
}
$taskPipOptions = @()
if ($Wheelhouse) {
    $taskWheelDirectory = (Resolve-Path -LiteralPath $Wheelhouse).Path
    $taskPipOptions = @("--no-index", "--find-links", $taskWheelDirectory)
}
foreach ($taskLock in @("requirements-windows-cp313.lock", "build-requirements.lock")) {
    & $taskInterpreter -I -m pip install @taskPipOptions --require-hashes --only-binary=:all: -r (Join-Path $PSScriptRoot $taskLock)
    if ($LASTEXITCODE -ne 0) { throw "Desktop dependency installation failed: $taskLock" }
}
& $taskInterpreter -I -m pip install --no-build-isolation --no-deps $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw "Desktop package installation failed." }
Write-Output "Desktop IDE installed. Start it with .\start.ps1"
