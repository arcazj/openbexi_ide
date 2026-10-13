Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-SafeChild([string] $Base, [string] $Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)' -or $Relative -match ':') {
        throw "Unsafe relative path: $Relative"
    }
    if ($Base.StartsWith('\\?\')) { $Base = $Base.Substring(4) }
    if ($Base.StartsWith('\\')) { throw 'Choose a local drive for the private Python installation' }
    $basePath = [IO.Path]::GetFullPath($Base).TrimEnd('\')
    $path = [IO.Path]::GetFullPath([IO.Path]::Combine($basePath, $Relative))
    if (-not $path.StartsWith($basePath + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Path escapes installation: $path" }
    $check = $path
    while ($check -and $check.Length -ge $basePath.Length) {
        if (Test-Path -LiteralPath ('\\?\' + $check)) {
            if ((Get-Item -LiteralPath ('\\?\' + $check) -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing installation reparse point: $check"
            }
        }
        $check = [IO.Path]::GetDirectoryName($check)
    }
    # PowerShell 5.1 otherwise truncates valid PySide6 paths at MAX_PATH.
    return '\\?\' + $path
}

function Read-InstallState([string] $Root) {
    $path = Get-SafeChild $Root '.openbexi-install.json'
    if (-not (Test-Path -LiteralPath $path)) { throw "Not an owned OpenBEXI installation: $Root" }
    $state = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if ($state.product -ne 'OpenBEXI IDE' -or $state.format -ne 1) { throw 'Unrecognized installation owner marker' }
    return $state
}

function Assert-Payload([string] $Payload, $Manifest) {
    if ($Manifest.product -ne 'OpenBEXI IDE' -or $Manifest.format -ne 1 -or $Manifest.payload_id -notmatch '^[a-f0-9]{64}$') {
        throw 'Invalid package manifest'
    }
    foreach ($file in $Manifest.files.PSObject.Properties) {
        $path = Get-SafeChild $Payload $file.Name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value) {
            throw "Package verification failed: $($file.Name)"
        }
    }
}

function Write-State([string] $Root, $State) {
    $temporary = Get-SafeChild $Root ('.state-' + [Guid]::NewGuid().ToString('N') + '.json')
    $destination = Get-SafeChild $Root '.openbexi-install.json'
    $State | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $destination -Force
}
