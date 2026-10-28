$ErrorActionPreference='Stop'
$project=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$fixture=Join-Path $project ('runs/runtime-package-fixture-'+[Guid]::NewGuid().ToString('N'))
$runtime=Join-Path $fixture 'runtime';$artifacts=Join-Path $fixture 'artifacts'
New-Item -ItemType Directory -Path $runtime,$artifacts -Force | Out-Null
$existing=Join-Path $project 'native/dist/MBDynStudio-Windows-local.zip'
$before=if(Test-Path -LiteralPath $existing){(Get-FileHash -LiteralPath $existing -Algorithm SHA256).Hash}else{$null}
try {
  $output=& pwsh -NoProfile -File (Join-Path $project 'native/package-windows.ps1') -PrivateRuntimeDirectory $runtime -PrivateRuntimeArtifacts $artifacts 2>&1
  if($LASTEXITCODE -eq 0){throw 'An unverified runtime must not be packaged.'}
  if(($output | Out-String) -notmatch 'runtime-manifest.json'){throw 'The failure should identify the missing runtime inventory.'}
  $after=if(Test-Path -LiteralPath $existing){(Get-FileHash -LiteralPath $existing -Algorithm SHA256).Hash}else{$null}
  if($before -ne $after){throw 'The existing local archive changed after a rejected runtime.'}
  Write-Output 'Unverified private runtime was rejected and the existing archive was preserved.'
} finally {
  $resolved=(Resolve-Path -LiteralPath $fixture).Path;$runs=(Resolve-Path -LiteralPath (Join-Path $project 'runs')).Path
  if(-not $resolved.StartsWith($runs+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Refusing to remove a fixture outside runs.'}
  Remove-Item -LiteralPath $resolved -Recurse -Force
}
