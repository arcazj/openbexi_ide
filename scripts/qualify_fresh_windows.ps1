param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][switch]$FreshWindows,
    [string]$ExpectedVersion='1.0.0',
    [string]$Output=(Join-Path $env:TEMP ('openbexi-fresh-' + [Guid]::NewGuid().ToString('N').Substring(0,8)))
)
$ErrorActionPreference='Stop'
if (-not $FreshWindows) { throw 'Run only on a freshly provisioned Windows environment and supply -FreshWindows.' }
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
$archivePath=(Resolve-Path -LiteralPath $Archive).Path
if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedSha256.ToLowerInvariant()) {
    throw 'Release archive SHA-256 differs.'
}
$machineGuid=(Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid).MachineGuid
$hasher=[System.Security.Cryptography.SHA256]::Create()
$machineHash=([BitConverter]::ToString($hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($machineGuid)))).Replace('-','').ToLowerInvariant()
if ($machineHash -eq '4f29a0c0a392718284f1e225cad11df8d814fb9d9eee17c391cfcf0ef2261174') {
    throw 'This is the existing development machine; it cannot qualify the fresh-Windows gate.'
}
if (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'OpenBEXI\IDE')) {
    throw 'An OpenBEXI IDE installation already exists in this user profile.'
}
if (Test-Path -LiteralPath $Output) { throw 'Use a new output directory so previous evidence is retained.' }
$root=(New-Item -ItemType Directory -Path $Output).FullName
$bundle=(New-Item -ItemType Directory -Path (Join-Path $root 'bundle')).FullName
$source=(New-Item -ItemType Directory -Path (Join-Path $root 'source')).FullName
$tar=Join-Path $env:SYSTEMROOT 'System32\tar.exe'
& $tar -xf $archivePath -C $bundle
if ($LASTEXITCODE -ne 0) { throw 'Release extraction failed.' }
$manifest=Get-Content -LiteralPath (Join-Path $bundle 'package.json') -Raw | ConvertFrom-Json
if ($manifest.version -ne $ExpectedVersion) { throw ('Expected IDE '+$ExpectedVersion+' artifact.') }
foreach ($entry in $manifest.files.PSObject.Properties) {
    $file=Join-Path (Join-Path $bundle 'payload') $entry.Name
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw ('Payload hash differs: '+$entry.Name)
    }
}
& $tar -xf (Join-Path $bundle 'payload\source\openbexi-ide-source.zip') -C $source
if ($LASTEXITCODE -ne 0) { throw 'Bundled source extraction failed.' }
$python=Join-Path $bundle 'payload\runtime\python.exe'
$lifecycle=Join-Path $root 'installed-workflow'
& $python -I -B (Join-Path $source 'scripts\distribution_qualify.py') --bundle $bundle --output $lifecycle --shared-debug --console-menu
if ($LASTEXITCODE -ne 0) { throw 'Fresh installed workflow failed; retained logs are in the output directory.' }
$result=Get-Content -LiteralPath (Join-Path $lifecycle 'result.json') -Raw | ConvertFrom-Json
if (-not $result.passed -or $result.version -ne $ExpectedVersion) { throw 'Installed report failed or used a different version.' }
$os=Get-CimInstance Win32_OperatingSystem
$report=@{
    passed=$true; version=$ExpectedVersion; scope='Fresh Windows x64 installation, bundled runtime, Run/Debug, console menu, shared debugger and removal'
    fresh_environment_operator_attested=$true; machine_identity_sha256=$machineHash
    windows_caption=$os.Caption; windows_version=$os.Version; windows_install_date=$os.InstallDate.ToString('o')
    artifact_sha256=$ExpectedSha256.ToLowerInvariant(); payload_files_verified=@($manifest.files.PSObject.Properties).Count
    lifecycle=@{path=(Join-Path $lifecycle 'result.json');sha256=(Get-FileHash -LiteralPath (Join-Path $lifecycle 'result.json') -Algorithm SHA256).Hash.ToLowerInvariant()}
    harness_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
[System.IO.File]::WriteAllText((Join-Path $root 'fresh-windows.json'),($report | ConvertTo-Json -Depth 8),[System.Text.UTF8Encoding]::new($false))
Write-Output ('Fresh Windows qualification passed. Evidence: '+$root)
