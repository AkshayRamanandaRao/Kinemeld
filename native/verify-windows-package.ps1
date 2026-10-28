# Verify the contents and execute the Windows desktop self-test from an extracted package.
[CmdletBinding()]
param([string]$Archive = (Join-Path $PSScriptRoot 'dist/MBDynStudio-Windows-local.zip'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$archivePath = (Resolve-Path -LiteralPath $Archive).Path
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
  $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  foreach ($entry in $zip.Entries) {
    $name = $entry.FullName.Replace('\','/')
    if ($name.StartsWith('/') -or $name.Contains(':') -or $name.Split('/') -contains '..' -or -not $seen.Add($name)) { throw "Unsafe or duplicate archive entry: $name" }
  }
  $manifestEntry = $zip.GetEntry('package-manifest.json')
  if (-not $manifestEntry) { throw 'Package manifest is missing.' }
  $reader = [IO.StreamReader]::new($manifestEntry.Open())
  try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
  if ($manifest.format -ne 'mbdyn-studio-windows-local/1') { throw 'Unsupported package format.' }
  foreach ($file in $manifest.files.PSObject.Properties) {
    $entry = $zip.GetEntry($file.Name)
    if (-not $entry) { throw "Missing entry: $($file.Name)" }
    $stream = $entry.Open()
    try { $hasher=[Security.Cryptography.SHA256]::Create(); try { $actual=[Convert]::ToHexString($hasher.ComputeHash($stream)).ToLowerInvariant() } finally { $hasher.Dispose() } } finally { $stream.Dispose() }
    if ($actual -ne $file.Value) { throw "Checksum mismatch: $($file.Name)" }
  }
  if (-not $manifest.solverConfigurationIncluded) { throw 'Real solver verification requires a package containing this machine''s solver configuration.' }
} finally { $zip.Dispose() }
$testRoot = Join-Path $project ('runs/package-qa-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
[IO.Compression.ZipFile]::ExtractToDirectory($archivePath, $testRoot)
$exe = Join-Path $testRoot 'native/MBDynStudio.exe'
$dataRoot = Join-Path $project ('runs/package-user-data-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $dataRoot | Out-Null
$oldWorkspace=$env:MBDYN_STUDIO_WORKSPACE
$oldData=$env:MBDYN_STUDIO_DATA_DIR
try {
  $env:MBDYN_STUDIO_WORKSPACE=$null
  $env:MBDYN_STUDIO_DATA_DIR=$dataRoot
  $process=Start-Process -FilePath $exe -ArgumentList '--smoke' -WorkingDirectory $testRoot -WindowStyle Hidden -PassThru
  if (-not $process.WaitForExit(120000)) { throw "Desktop package self-test timed out; owned process $($process.Id) may still be running." }
  if ($process.ExitCode -ne 0) { throw "Desktop package self-test failed with exit code $($process.ExitCode)." }
  $resultPath=Join-Path $dataRoot "runs/native-smoke-report-$($process.Id).json"
  $result=Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
  if (-not $result.ok -or $result.source -ne 'MBDyn' -or -not $result.hasCanvas -or $result.workspace -ne $testRoot) { throw 'Extracted desktop did not verify its own workspace, actual MBDyn and canvas.' }
  if (Test-Path -LiteralPath (Join-Path $testRoot 'runs')) { throw 'Extracted application wrote run data into its resource directory.' }
  $report=[ordered]@{ok=$true;archive=$archivePath;archiveSha256=(Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant();verifiedFiles=@($manifest.files.PSObject.Properties).Count;extractedWorkspace=$testRoot;userData=$dataRoot;runId=$result.runId;source=$result.source;hasCanvas=$result.hasCanvas;scope='Extracted Windows host with separate temporary data, embedded viewer, project round trip and configured local MBDyn. Does not verify native file dialogs or distribution dependencies on other machines.'}
  $reportPath=Join-Path $project 'runs/windows-package-verification.json'
  $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding utf8
  $report | ConvertTo-Json -Depth 5
} finally { $env:MBDYN_STUDIO_WORKSPACE=$oldWorkspace; $env:MBDYN_STUDIO_DATA_DIR=$oldData }
