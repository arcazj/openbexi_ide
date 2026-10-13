param([string] $Root = $PSScriptRoot)
. (Join-Path $PSScriptRoot 'common.ps1')
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
$state = Read-InstallState $Root
# Refuse before deleting any files if an owned interpreter is still running.
# Partial deletion would otherwise leave an active IDE with missing libraries.
foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'")) {
    $executable = $process.ExecutablePath
    if (-not $executable) { continue }
    if ($executable.StartsWith('\\?\')) { $executable = $executable.Substring(4) }
    if ($executable.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Close the application using this installation before uninstalling (PID $($process.ProcessId)). No files removed."
    }
}
$preserved = [Collections.Generic.List[string]]::new()
$removed = 0
foreach ($version in $state.versions) {
    $directory = Get-SafeChild $Root $version.directory
    $manifestPath = Get-SafeChild $directory 'package.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) { continue }
    if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $version.manifest_sha256) {
        $preserved.Add($directory)
        continue
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($file in $manifest.files.PSObject.Properties) {
        $path = Get-SafeChild $directory $file.Name
        if (-not (Test-Path -LiteralPath $path)) { continue }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $file.Value) {
            try { Remove-Item -LiteralPath $path -Force; $removed++ } catch { $preserved.Add($path) }
        } else { $preserved.Add($path) }
    }
    # Enumerate only verified owned payload directories; never recursively delete.
    $directories = @($manifest.files.PSObject.Properties | ForEach-Object {
        $path = [IO.Path]::GetDirectoryName((Get-SafeChild $directory $_.Name))
        while ($path.Length -gt $directory.Length) { $path; $path = [IO.Path]::GetDirectoryName($path) }
    } | Sort-Object -Unique | Sort-Object Length -Descending)
    foreach ($path in $directories) {
        if ((Test-Path -LiteralPath $path) -and @(Get-ChildItem -LiteralPath $path -Force).Count -eq 0) { Remove-Item -LiteralPath $path }
    }
    if (@(Get-ChildItem -LiteralPath $directory -Force | Where-Object Name -ne 'package.json').Count -eq 0) {
        Remove-Item -LiteralPath $manifestPath
        Remove-Item -LiteralPath $directory
    } else { $preserved.Add($directory) }
}
foreach ($shortcut in $state.shortcuts) {
    if (Test-Path -LiteralPath $shortcut.path) {
        if ((Get-FileHash -LiteralPath $shortcut.path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $shortcut.sha256) {
            Remove-Item -LiteralPath $shortcut.path
        } else { $preserved.Add($shortcut.path) }
    }
}
foreach ($tool in $state.tools.PSObject.Properties) {
    $path = Get-SafeChild $Root $tool.Name
    if ((Test-Path -LiteralPath $path) -and (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tool.Value) {
        $preserved.Add($path)
    }
}
$knownRootNames = @('.openbexi-install.json', 'versions') + @($state.tools.PSObject.Properties | ForEach-Object { $_.Name })
foreach ($child in @(Get-ChildItem -LiteralPath $Root -Force)) {
    if ($knownRootNames -notcontains $child.Name) { $preserved.Add($child.FullName) }
}
$versionsRoot = Get-SafeChild $Root 'versions'
if (Test-Path -LiteralPath $versionsRoot) {
    $knownVersions = @($state.versions | ForEach-Object { [IO.Path]::GetFileName($_.directory.Replace('/', '\')) })
    foreach ($child in @(Get-ChildItem -LiteralPath $versionsRoot -Force)) {
        if ($knownVersions -notcontains $child.Name) { $preserved.Add($child.FullName) }
    }
}
if ($preserved.Count -eq 0) {
    foreach ($tool in $state.tools.PSObject.Properties) {
        $path = Get-SafeChild $Root $tool.Name
        if ((Test-Path -LiteralPath $path) -and (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $tool.Value) { Remove-Item -LiteralPath $path }
    }
    Remove-Item -LiteralPath (Get-SafeChild $Root '.openbexi-install.json')
    $versions = Get-SafeChild $Root 'versions'
    if ((Test-Path -LiteralPath $versions) -and @(Get-ChildItem -LiteralPath $versions -Force).Count -eq 0) { Remove-Item -LiteralPath $versions }
    if (@(Get-ChildItem -LiteralPath $Root -Force).Count -eq 0) { Remove-Item -LiteralPath $Root }
} else {
    $state.current = ''
    Write-State $Root $state
}
[pscustomobject]@{ uninstalled = $true; removed_files = $removed; preserved = @($preserved | Sort-Object -Unique); projects_and_preferences = 'untouched' } | ConvertTo-Json -Depth 5
