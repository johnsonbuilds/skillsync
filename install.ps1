# SkillSync installer for native Windows (PowerShell 5.1+ / PowerShell 7+).
#
# Usage (in PowerShell):
#   irm https://raw.githubusercontent.com/johnsonbuilds/skillsync/main/install.ps1 | iex
#   (Windows PowerShell 5.1:  iwr <url> -UseBasicParsing | iex)
# Or download the file and run:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# What it does:
#   1. finds a Python >= 3.12 (python / py launcher / python3; ignores the
#      Microsoft Store "python" stub)
#   2. creates ~\.local\share\skillsync\venv
#   3. pip installs skillsync (from GitHub by default)
#   4. exposes a `skillsync` shim in ~\.local\bin and adds it to the user PATH
#
# Override the source repository with:
#   $env:SKILLSYNC_REPO = 'C:\path\to\checkout'; irm <url> | iex

$ErrorActionPreference = 'Stop'

function Install-SkillSync {
    $InstallDir = Join-Path $env:USERPROFILE '.local\share\skillsync'
    $VenvDir    = Join-Path $InstallDir 'venv'
    $BinDir     = Join-Path $env:USERPROFILE '.local\bin'

    Write-Host 'Installing SkillSync...'

    # 1. Find Python >= 3.12 -----------------------------------------------
    #    Try python, then the py launcher, then python3. Skip the Microsoft
    #    Store alias stubs (WindowsApps\python[3].exe opens the store instead
    #    of running); real Store installs live in a package subdirectory and
    #    are kept. Candidates older than 3.12 are skipped, not fatal.
    $pyExe = $null
    $pyPre = @()
    foreach ($spec in @(@('python'), @('py', '-3'), @('python3'))) {
        $cmd = Get-Command $spec[0] -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($cmd.Source -match '\\WindowsApps\\python3?\.exe$') { continue }
        $pyArgs = @($spec) + @('-c', "import sys; print('%d.%d' % sys.version_info[:2])")
        $ver = (& $pyArgs[0] $pyArgs[1..($pyArgs.Count - 1)] 2>$null)
        if (-not $ver) { continue }
        $ver = "$ver".Trim()
        if ($ver -notmatch '^\d+\.\d+$') { continue }
        if ([version]$ver -lt [version]'3.12') { continue }
        $pyExe = $spec[0]
        if ($spec.Count -gt 1) { $pyPre = @($spec[1..($spec.Count - 1)]) }
        break
    }

    if (-not $pyExe) {
        $msg = ("Error: no Python >= 3.12 found (searched python, py -3, python3).`n" +
                "Install Python 3.12+ first and re-run this installer, e.g.:`n" +
                "    winget install --id Python.Python.3.12`n" +
                "or from https://www.python.org/downloads/ (tick 'Add python.exe to PATH').")
        throw $msg
    }

    # git is needed to fetch from GitHub (unless SKILLSYNC_REPO is a local path).
    $RepoUrl = if ($env:SKILLSYNC_REPO) { $env:SKILLSYNC_REPO } else { 'https://github.com/johnsonbuilds/skillsync.git' }
    $needsGit = ($RepoUrl -match '\.git$') -or ($RepoUrl -like 'http*') -or ($RepoUrl -like 'git+*')
    if ($needsGit -and -not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw ("Error: git not found. Install it first and re-run this installer:`n" +
               "    winget install --id Git.Git   (or https://git-scm.com)")
    }

    # 2. Create the venv -----------------------------------------------------
    if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
    & $pyExe @pyPre -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        throw "Error: could not create the virtual environment at $VenvDir."
    }

    # 3. Install skillsync into it ------------------------------------------
    #    REPO_URL may be a git URL or a local checkout path.
    $src = if ($needsGit) { "git+$RepoUrl" } else { $RepoUrl }
    $pip = Join-Path $VenvDir 'Scripts\pip.exe'
    & $pip install --upgrade $src
    if ($LASTEXITCODE -ne 0) {
        throw "Error: pip install failed (see output above)."
    }

    # 4. Expose the entry point ----------------------------------------------
    $exe = Join-Path $VenvDir 'Scripts\skillsync.exe'
    if (-not (Test-Path $exe)) {
        throw "Error: pip finished but $exe was not created."
    }
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    # cmd shim: resolves in both cmd.exe and PowerShell (PATHEXT); expanding
    # %USERPROFILE% at runtime keeps the shim pure ASCII.
    $shim = Join-Path $BinDir 'skillsync.cmd'
    $shimContent = "@echo off`r`n`"%USERPROFILE%\.local\share\skillsync\venv\Scripts\skillsync.exe`" %*`r`n"
    Set-Content -Path $shim -Value $shimContent -Encoding ASCII

    # Add the shim directory to the user PATH (and this session).
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $have = @(($userPath -split ';') | ForEach-Object { $_.TrimEnd('\') }) -contains $BinDir.TrimEnd('\')
    if (-not $have) {
        $newPath = if ($userPath) { "$userPath;$BinDir" } else { $BinDir }
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
        Write-Host "Added $BinDir to your user PATH."
    }
    if (@($env:Path -split ';') -notcontains $BinDir) { $env:Path = "$env:Path;$BinDir" }

    Write-Host ''
    Write-Host 'SkillSync installed.'
    Write-Host 'Run:  skillsync init'
    Write-Host 'Note: open a NEW terminal window so the updated PATH takes effect.'
}

try {
    Install-SkillSync
}
catch {
    Write-Host ''
    Write-Host $_.Exception.Message -ForegroundColor Red
    # When piped into iex there is no script file; exiting would close the
    # caller's interactive session, so only exit for real file invocations.
    if ($MyInvocation.MyCommand.Path) { exit 1 }
}
