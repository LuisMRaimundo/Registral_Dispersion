#Requires -Version 5.1
# Registral_Dispersion - Windows one-click installer

$ErrorActionPreference = 'Stop'
$InstallerRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$ProjectRoot = (Resolve-Path (Join-Path $InstallerRoot '..\..')).Path

. (Join-Path $InstallerRoot 'config.ps1')
. (Join-Path $InstallerRoot 'lib\InstallerHelpers.ps1')

$cfg = $script:RegistralConfig
$VenvDir = Join-Path $ProjectRoot $cfg.VenvFolder
$script:InstallLogPath = Join-Path $ProjectRoot 'install.log'

Set-Location $ProjectRoot

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  $($cfg.AppName) - Installer" -ForegroundColor Cyan
Write-Host "  $($cfg.GitHubRepoUrl)" -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  Project: $ProjectRoot"
Write-Host ''

try {
    Write-InstallLog 'Checking for Python 3.10-3.12...'
    $py = Find-ExistingPython
    if (-not $py) {
        $py = Install-PythonIfNeeded
    }
    if (-not $py) {
        throw 'Python 3.10 or newer is required and was not found.'
    }
    Write-InstallLog "Using Python: $($py.Exe)$(if ($py.Arg) { ' ' + $py.Arg })"

    $null = Initialize-ProjectVenv -Py $py -ProjectRoot $ProjectRoot -VenvDir $VenvDir
    Copy-LauncherScripts -ProjectRoot $ProjectRoot -InstallerRoot $InstallerRoot

    Write-Host ''
    Write-Host 'SUCCESS - Installation complete.' -ForegroundColor Green
    Write-Host "  Log: $script:InstallLogPath"
    Write-Host ''
    Write-Host 'To open the analysis interface, double-click:'
    Write-Host "  $($cfg.LaunchBat)"
    Write-Host ''
    Write-Host 'For a one-number global summary from the command line:'
    Write-Host "  $($cfg.SummarizeBat) --score path\to\score.musicxml"
    Write-Host ''

    $run = Read-Host 'Launch the interface now? [Y/n]'
    if ($run -and $run.Trim().ToLower() -eq 'n') {
        exit 0
    }
    $launch = Join-Path $ProjectRoot $cfg.LaunchBat
    if (Test-Path $launch) {
        Start-Process -FilePath $launch -WorkingDirectory $ProjectRoot
    }
}
catch {
    Write-InstallLog $_.Exception.Message 'ERROR'
    if ($_.ScriptStackTrace) { Write-InstallLog $_.ScriptStackTrace 'ERROR' }
    Write-Host ''
    Write-Host 'INSTALLATION FAILED.' -ForegroundColor Red
    Write-Host $_.Exception.Message
    Write-Host "Log: $script:InstallLogPath"
    exit 1
}
