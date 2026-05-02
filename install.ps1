<#
.SYNOPSIS
    Installs DigiSign dependencies and creates a Windows desktop shortcut.

.DESCRIPTION
    Creates a local Python virtual environment in .venv, installs packages from requirements.txt,
    and creates a desktop shortcut that launches DigiSign using the virtual environment.

.NOTES
    Run this script from the project root directory.
    Example: powershell -ExecutionPolicy Bypass -File .\install.ps1
#>

param (
    [switch]$Force,
    [switch]$SkipVenv
)

$ErrorActionPreference = 'Stop'

function Get-RepositoryRoot {
    return Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Find-PythonExecutable {
    param (
        [string]$VirtualEnvPath
    )

    if (-not $SkipVenv -and Test-Path "$VirtualEnvPath\Scripts\python.exe") {
        return "$VirtualEnvPath\Scripts\python.exe"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Path
    }

    throw "Python executable not found. Install Python 3.10+ and ensure it is on PATH."
}

function Create-VirtualEnvironment {
    param (
        [string]$RepoRoot,
        [string]$VirtualEnvPath
    )

    if (Test-Path $VirtualEnvPath) {
        if (-not $Force) {
            Write-Host "Virtual environment already exists at $VirtualEnvPath. Use -Force to recreate it." -ForegroundColor Yellow
            return
        }
        Remove-Item -Recurse -Force $VirtualEnvPath
    }

    $python = Find-PythonExecutable -VirtualEnvPath $VirtualEnvPath
    Write-Host "Creating virtual environment at $VirtualEnvPath..."
    & $python -m venv $VirtualEnvPath
}

function Install-Dependencies {
    param (
        [string]$PythonExe,
        [string]$RepoRoot
    )

    Write-Host "Upgrading pip..."
    & $PythonExe -m pip install --upgrade pip

    Write-Host "Installing package dependencies from requirements.txt..."
    & $PythonExe -m pip install -r (Join-Path $RepoRoot 'requirements.txt')
}

function Create-DesktopShortcut {
    param (
        [string]$RepoRoot,
        [string]$PythonExe
    )

    $desktopPath = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktopPath 'DigiSign.lnk'
    $wshShell = New-Object -ComObject WScript.Shell
    $shortcut = $wshShell.CreateShortcut($shortcutPath)

    $shortcut.TargetPath = $PythonExe
    $shortcut.Arguments = '"' + (Join-Path $RepoRoot 'main.py') + '"'
    $shortcut.WorkingDirectory = $RepoRoot
    $shortcut.WindowStyle = 1
    $shortcut.Description = 'Launch DigiSign PDF Signer'
    $shortcut.IconLocation = "$PythonExe,0"
    $shortcut.Save()

    Write-Host "Desktop shortcut created at: $shortcutPath" -ForegroundColor Green
}

try {
    $repoRoot = Get-RepositoryRoot
    Set-Location $repoRoot

    $venvPath = Join-Path $repoRoot '.venv'
    $pythonExe = Find-PythonExecutable -VirtualEnvPath $venvPath

    if (-not $SkipVenv) {
        Create-VirtualEnvironment -RepoRoot $repoRoot -VirtualEnvPath $venvPath
        $pythonExe = Find-PythonExecutable -VirtualEnvPath $venvPath
    }

    Install-Dependencies -PythonExe $pythonExe -RepoRoot $repoRoot
    Create-DesktopShortcut -RepoRoot $repoRoot -PythonExe $pythonExe

    Write-Host "DigiSign installation complete." -ForegroundColor Green
    Write-Host "Launch DigiSign from the desktop shortcut or by running: $pythonExe `"$repoRoot\main.py`""
} catch {
    Write-Host "Installation failed: $_" -ForegroundColor Red
    exit 1
}
