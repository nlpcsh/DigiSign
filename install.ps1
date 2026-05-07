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
    if ([string]::IsNullOrEmpty($MyInvocation.MyCommand.Path)) {
        return (Get-Location).Path
    }
    return Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Find-PythonExecutable {
    param (
        [string]$VirtualEnvPath
    )

    $script:PythonArgs = @()

    if (-not $SkipVenv) {
        if (Test-Path "$VirtualEnvPath\Scripts\python.exe") {
            return "$VirtualEnvPath\Scripts\python.exe"
        }
    }

    $candidates = @('python', 'python3', 'py')
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command) {
            $pythonPath = $command.Path
            if ([string]::IsNullOrEmpty($pythonPath)) {
                $pythonPath = $command.Definition
            }
            if ([string]::IsNullOrEmpty($pythonPath)) {
                $pythonPath = $command.Source
            }
            if ([string]::IsNullOrEmpty($pythonPath)) {
                continue
            }

            if ($candidate -eq 'py') {
                try {
                    & $pythonPath -3 --version > $null 2>&1
                    if ($LASTEXITCODE -eq 0) {
                        $script:PythonArgs = @('-3')
                        return $pythonPath
                    }
                } catch {
                    continue
                }
            }
            return $pythonPath
        }
    }

    throw "Python executable not found. Install Python 3.8 or later and ensure it is on PATH."
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
    & $python @PythonArgs -m venv $VirtualEnvPath
}

function Install-Dependencies {
    param (
        [string]$PythonExe,
        [string]$RepoRoot
    )

    Write-Host "Upgrading pip..."
    & $PythonExe @PythonArgs -m pip install --upgrade pip

    Write-Host "Installing package dependencies from requirements.txt..."
    & $PythonExe @PythonArgs -m pip install -r (Join-Path $RepoRoot 'requirements.txt')
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
    $launchCmd = '"{0}" "{1}"' -f $pythonExe, (Join-Path $repoRoot 'main.py')
    Write-Host "Launch DigiSign from the desktop shortcut or by running: $launchCmd"
} catch {
    Write-Host "Installation failed: $_" -ForegroundColor Red
    exit 1
}
