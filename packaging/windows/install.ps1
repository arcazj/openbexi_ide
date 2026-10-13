param(
    [string] $Root = (Join-Path $env:LOCALAPPDATA 'OpenBEXI\IDE'),
    [switch] $NoShortcuts,
    [string] $ShortcutDirectory = ([Environment]::GetFolderPath('Programs'))
)
. (Join-Path $PSScriptRoot 'common.ps1')
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
if ($Root -eq [IO.Path]::GetPathRoot($Root).TrimEnd('\')) { throw 'A drive root is not an installation directory' }
$manifestPath = Join-Path $PSScriptRoot 'package.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
Assert-Payload (Join-Path $PSScriptRoot 'payload') $manifest
if ($manifest.version -notmatch '^[0-9A-Za-z.+-]+$') { throw 'Invalid version string' }
if (Test-Path -LiteralPath $Root) {
    $state = Read-InstallState $Root
} else {
    New-Item -ItemType Directory -Path $Root | Out-Null
    $state = [pscustomobject]@{ product = 'OpenBEXI IDE'; format = 1; current = ''; versions = @(); tools = [pscustomobject]@{}; shortcuts = @() }
    Write-State $Root $state
}
# Updating a tool somebody edited would lose data, so require an explicit resolution.
foreach ($tool in $state.tools.PSObject.Properties) {
    $path = Get-SafeChild $Root $tool.Name
    if ((Test-Path -LiteralPath $path) -and (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tool.Value) {
        throw "Installation tool was modified; preserved without overwriting: $path"
    }
}
if (-not $NoShortcuts) {
    $shortcutPath = [IO.Path]::GetFullPath([IO.Path]::Combine($ShortcutDirectory, 'OpenBEXI IDE.lnk'))
    if (Test-Path -LiteralPath $shortcutPath) {
        $owned = @($state.shortcuts | Where-Object path -eq $shortcutPath)
        if ($owned.Count -ne 1) { throw "Unowned shortcut exists: $shortcutPath" }
        if ((Get-FileHash -LiteralPath $shortcutPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $owned[0].sha256) {
            throw "Shortcut was modified; preserved without overwriting: $shortcutPath"
        }
    }
}
$versionDirectory = 'versions/' + $manifest.version + '-' + $manifest.payload_id.Substring(0, 16)
$destination = Get-SafeChild $Root $versionDirectory
if (Test-Path -LiteralPath $destination) {
    Assert-Payload $destination $manifest
} else {
    $staging = Get-SafeChild $Root ('.staging-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $staging | Out-Null
    foreach ($file in $manifest.files.PSObject.Properties) {
        $source = Get-SafeChild (Join-Path $PSScriptRoot 'payload') $file.Name
        $target = Get-SafeChild $staging $file.Name
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target
    }
    Copy-Item -LiteralPath $manifestPath -Destination (Get-SafeChild $staging 'package.json')
    Assert-Payload $staging $manifest
    New-Item -ItemType Directory -Path (Get-SafeChild $Root 'versions') -Force | Out-Null
    # Both absolute source and destination were validated inside the owned root.
    Move-Item -LiteralPath $staging -Destination $destination
}
$tools = @{}
foreach ($name in @('common.ps1', 'launch.ps1', 'uninstall.ps1')) {
    $target = Get-SafeChild $Root $name
    if ((Test-Path -LiteralPath $target) -and -not (@($state.tools.PSObject.Properties | ForEach-Object { $_.Name }) -contains $name)) {
        throw "Unowned file blocks installation: $target"
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $target -Force
    $tools[$name] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
}
$state.tools = [pscustomobject]$tools
$state.current = $versionDirectory
if (-not (@($state.versions | ForEach-Object { $_.directory }) -contains $versionDirectory)) {
    $state.versions = @($state.versions) + [pscustomobject]@{
        directory = $versionDirectory; manifest_sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
if (-not $NoShortcuts) {
    New-Item -ItemType Directory -Path $ShortcutDirectory -Force | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $PSHOME 'powershell.exe'
    $shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $Root 'launch.ps1') + '"'
    $shortcut.WorkingDirectory = [Environment]::GetFolderPath('MyDocuments')
    $shortcut.Description = 'OpenBEXI IDE'
    $shortcut.Save()
    $state.shortcuts = @([pscustomobject]@{path = $shortcutPath; sha256 = (Get-FileHash -LiteralPath $shortcutPath -Algorithm SHA256).Hash.ToLowerInvariant()})
}
Write-State $Root $state
[pscustomobject]@{ installed = $true; version = $manifest.version; root = $Root; active = $destination; python = (Get-SafeChild $destination 'runtime/python.exe') } | ConvertTo-Json
