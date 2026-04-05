$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$bugreports = Get-ChildItem -Path $repoRoot -Filter 'bugreport-*.txt' -File -ErrorAction SilentlyContinue
foreach ($file in $bugreports) {
    Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
}

git add -A

$status = git status --porcelain
if (-not $status) {
    Write-Output 'No changes to commit.'
    exit 0
}

git commit -m "Android: copy SQLite sidecars, inspect DB; header icon fallback; tests; remove bugreport logs"
git push