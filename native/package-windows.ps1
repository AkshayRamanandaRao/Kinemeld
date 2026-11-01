# Build a Windows application folder as a ZIP; it uses the recipient's Python and solver.
[CmdletBinding()]
param(
  [switch]$IncludeLocalSolverConfiguration,
  [string]$ExecutablePath,
  [string]$PrivateRuntimeDirectory,
  [string]$PrivateRuntimeArtifacts
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $ExecutablePath) { $ExecutablePath = Join-Path $PSScriptRoot 'MBDynStudio.exe' }
$exe = (Resolve-Path -LiteralPath $ExecutablePath).Path
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Desktop executable not found: $ExecutablePath" }
& python -I (Join-Path $project 'scripts/check_asset_notices.py') --root $project
if ($LASTEXITCODE -ne 0) { throw 'Asset notice verification failed; no package was created.' }
& python -I (Join-Path $project 'scripts/collect_rust_notices.py') --check --source-root $project --target x86_64-pc-windows-msvc
if ($LASTEXITCODE -ne 0) { throw 'Rust notice verification failed; no package was created.' }
$dist = Join-Path $PSScriptRoot 'dist'
if (-not (Test-Path -LiteralPath $dist)) { New-Item -ItemType Directory -Path $dist | Out-Null }
$dist = (Resolve-Path -LiteralPath $dist).Path
if ((Get-Item -LiteralPath $dist -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Distribution directory must not be a symlink or junction.' }
if ([IO.Path]::GetDirectoryName($dist) -ne (Resolve-Path -LiteralPath $PSScriptRoot).Path) { throw 'Distribution directory resolves outside native/.' }
$includeRuntime = -not [string]::IsNullOrWhiteSpace($PrivateRuntimeDirectory)
if ($includeRuntime -ne (-not [string]::IsNullOrWhiteSpace($PrivateRuntimeArtifacts))) { throw 'Specify both -PrivateRuntimeDirectory and -PrivateRuntimeArtifacts, or neither.' }
$runtime = $null
$provenance = $null
if ($includeRuntime) {
  $runtimePath = (Resolve-Path -LiteralPath $PrivateRuntimeDirectory).Path
  $artifactPath = (Resolve-Path -LiteralPath $PrivateRuntimeArtifacts).Path
  $verifier = Join-Path $PSScriptRoot 'runtime-lock/verify_runtime.py'
  $metadata = & python -I $verifier --runtime $runtimePath --artifacts $artifactPath
  if ($LASTEXITCODE -ne 0) { throw 'Private runtime verification failed; no package was created.' }
  $runtime = $metadata | ConvertFrom-Json -AsHashtable
  if ($runtime.format -ne 'mbdyn-python-runtime/1' -or $runtime.redistributionStatus -ne 'not-established') { throw 'Unexpected runtime verification result.' }
  $runtimeTools = Join-Path $PSScriptRoot 'runtime-lock'
  $audit = & python -I -c 'import sys; sys.path.insert(0,sys.argv.pop(1)); import audit_provenance; audit_provenance.main()' $runtimeTools --runtime $runtimePath --artifacts $artifactPath
  if ($LASTEXITCODE -ne 0) { throw 'Runtime payload comparison failed; no package was created.' }
  $provenance = $audit | ConvertFrom-Json -AsHashtable
  if (-not $provenance.ok -or $provenance.wheelCount -ne $runtime.wheelCount) { throw 'Unexpected runtime payload comparison result.' }
}
$output = Join-Path $dist $(if ($includeRuntime) { 'MBDynStudio-Windows-private-runtime-test.zip' } else { 'MBDynStudio-Windows-local.zip' })
$temporary = Join-Path $dist ('.pack-' + [Guid]::NewGuid().ToString('N') + '.zip')
if (Test-Path -LiteralPath $output) {
  $old = Get-Item -LiteralPath $output -Force
  if ($old.PSIsContainer -or ($old.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $old.DirectoryName -ne $dist) { throw 'Existing archive is not a normal file in the distribution directory.' }
  Remove-Item -LiteralPath $old.FullName
}
$entries = [ordered]@{}
function Add-SourceFile([string]$source, [string]$relative) {
  $file = Get-Item -LiteralPath $source -Force
  if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Refusing linked or non-file package entry: $source" }
  $name = $relative.Replace('\','/')
  if ($name.StartsWith('/') -or $name.Split('/') -contains '..' -or $entries.Contains($name)) { throw "Unsafe or duplicate package entry: $name" }
  $entries[$name] = $file.FullName
}
foreach ($directory in @('backend','frontend','examples','docs','notices')) {
  $folder = Join-Path $project $directory
  Get-ChildItem -LiteralPath $folder -File -Recurse -Force | ForEach-Object {
    $relative = [IO.Path]::GetRelativePath($project, $_.FullName).Replace('\','/')
    $segments = $relative.Split('/')
    if (($segments -contains '__pycache__') -or ($segments -contains 'vendor' -and $directory -eq 'backend') -or $relative.EndsWith('.pyc') -or $relative.EndsWith('.log') -or $relative.EndsWith('.stl') -or $relative.StartsWith('backend/evidence/')) { return }
    if ($relative -eq 'backend/agent.json' -or ($relative -eq 'backend/solver.json' -and -not $IncludeLocalSolverConfiguration)) { return }
    Add-SourceFile $_.FullName $relative
  }
}
foreach ($name in @('LICENSE','THIRD_PARTY_NOTICES.md','README.md','Start MBDyn Studio Desktop.cmd')) { Add-SourceFile (Join-Path $project $name) $name }
Add-SourceFile (Join-Path $PSScriptRoot 'README.md') 'native/README.md'
foreach ($name in @('README.md','windows-cp312.json','requirements-windows-cp312.txt','resolve.py','verify_runtime.py','draft_manifest.py','prepare_runtime.py','smoke_runtime.py','audit_provenance.py')) { Add-SourceFile (Join-Path $PSScriptRoot ('runtime-lock/' + $name)) ('native/runtime-lock/' + $name) }
Add-SourceFile $exe 'native/MBDynStudio.exe'
if ($includeRuntime) {
  foreach ($name in $runtime.files) { Add-SourceFile (Join-Path $runtime.root $name) ("runtime/python/" + $name) }
  Add-SourceFile (Join-Path $PSScriptRoot 'runtime-lock/windows-cp312.json') 'runtime/windows-cp312.json'
}
if ($IncludeLocalSolverConfiguration -and -not $entries.Contains('backend/solver.json')) { throw 'Local solver configuration requested but backend/solver.json is missing.' }
try {
  $archive = [IO.Compression.ZipFile]::Open($temporary, [IO.Compression.ZipArchiveMode]::Create)
  try {
    $hashes = [ordered]@{}
    foreach ($name in $entries.Keys) {
      $source = $entries[$name]
      $hashes[$name] = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
      [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $source, $name, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
    if ($includeRuntime) {
      foreach ($name in $runtime.files) {
        if ($hashes["runtime/python/$name"] -ne $runtime.hashes[$name]) { throw "Verified runtime file changed before packaging: $name" }
      }
    }
    $manifest = [ordered]@{ format='mbdyn-studio-windows-local/1'; solverConfigurationIncluded=[bool]$IncludeLocalSolverConfiguration; privateRuntimeIncluded=[bool]$includeRuntime; runtimeRedistributionStatus= $(if ($includeRuntime) { 'not-established' } else { 'not-included' }); runtimePayloadComparison=$(if($includeRuntime){[ordered]@{matchedFiles=$provenance.matchedFiles;unprovenFiles=$provenance.unprovenFiles.Count;scope='Locked archive payload byte matches; generated metadata and notices remain unproven.'}}else{$null}); requirements=@('Windows x64','Microsoft WebView2 Runtime',$(if ($includeRuntime) { 'app-private Python runtime requires separate clean-machine and license qualification' } else { 'Python 3.10+ with cadquery-ocp for STEP' }),'configured MBDyn; local configuration may reference this machine only','Ollama optional for AI'); files=$hashes }
    $entry = $archive.CreateEntry('package-manifest.json')
    $writer = [IO.StreamWriter]::new($entry.Open(), [Text.UTF8Encoding]::new($false))
    try { $writer.Write(($manifest | ConvertTo-Json -Depth 6)) } finally { $writer.Dispose() }
  } finally { $archive.Dispose() }
  $verify = [IO.Compression.ZipFile]::OpenRead($temporary)
  try {
    foreach ($name in $entries.Keys) {
      $entry = $verify.GetEntry($name)
      if (-not $entry) { throw "Package entry is missing: $name" }
      $stream = $entry.Open()
      try { $hasher = [Security.Cryptography.SHA256]::Create(); try { $actual = [Convert]::ToHexString($hasher.ComputeHash($stream)).ToLowerInvariant() } finally { $hasher.Dispose() } } finally { $stream.Dispose() }
      if ($actual -ne $hashes[$name]) { throw "Source changed during packaging: $name" }
    }
  } finally { $verify.Dispose() }
  Move-Item -LiteralPath $temporary -Destination $output
  Write-Output "Package: $output"
  Write-Output "Entries: $($entries.Count); local solver configuration included: $([bool]$IncludeLocalSolverConfiguration); private runtime included: $([bool]$includeRuntime)"
  Get-FileHash -LiteralPath $output -Algorithm SHA256 | Format-List
} finally {
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
}
