param(
    [string]$Python = "python.exe",
    [string]$Wheelhouse = "",
    [string]$IdeWheel = "",
    [string]$IdeWheelSha256 = ""
)
$ErrorActionPreference = "Stop"
$taskRepoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$taskEnvironment = Join-Path $taskRepoRoot ".venv"
$taskInterpreter = Join-Path $taskEnvironment "Scripts/python.exe"

if ([bool]$IdeWheel -ne [bool]$IdeWheelSha256) {
    throw "Supply both -IdeWheel and its -IdeWheelSha256 from the release manifest."
}
if ($IdeWheel) {
    $taskWheelPath = (Resolve-Path -LiteralPath $IdeWheel).Path
    if ($IdeWheelSha256 -notmatch '^[0-9a-fA-F]{64}$' -or
        [IO.Path]::GetExtension($taskWheelPath) -ine ".whl" -or
        (Get-FileHash -LiteralPath $taskWheelPath -Algorithm SHA256).Hash -ine $IdeWheelSha256) {
        throw "The supplied IDE wheel does not match the expected SHA-256."
    }
}
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
} else {
    & $taskInterpreter -I -m pip install --require-hashes --only-binary=:all: -r (Join-Path $PSScriptRoot "requirements-windows-installer.lock")
    if ($LASTEXITCODE -ne 0) { throw "Windows installer bootstrap failed." }
}
$taskLocks = @("requirements-windows-cp313.lock")
if (!$IdeWheel) { $taskLocks += "build-requirements.lock" }
foreach ($taskLock in $taskLocks) {
    & $taskInterpreter -I -m pip install @taskPipOptions --require-hashes --only-binary=:all: -r (Join-Path $PSScriptRoot $taskLock)
    if ($LASTEXITCODE -ne 0) { throw "Desktop dependency installation failed: $taskLock" }
}
if ($IdeWheel) {
    & $taskInterpreter -I -m pip install --no-index --no-deps $taskWheelPath
} else {
    & $taskInterpreter -I -m pip install --no-build-isolation --no-deps $PSScriptRoot
}
if ($LASTEXITCODE -ne 0) { throw "Desktop package installation failed." }
Write-Output "Desktop IDE installed. Start it with .\start.ps1"
