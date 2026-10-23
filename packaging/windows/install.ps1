$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "A setup command failed (exit $LASTEXITCODE). Check the message above, then run Install Focus.cmd again."
    }
}

try {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'Focus needs 64-bit Windows 10 or Windows 11.'
    }
    $sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    $installRoot = Join-Path $env:LOCALAPPDATA 'FocusAssistant'
    $pythonRoot = Join-Path $installRoot 'Python'
    $pythonExe = Join-Path $pythonRoot 'python.exe'
    $venvRoot = Join-Path $installRoot 'BuildEnvironment'
    $buildPython = Join-Path $venvRoot 'Scripts\python.exe'
    $applicationRoot = Join-Path $installRoot 'App'
    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null

    # Do not overwrite a running app or share setup state between installers.
    $mutex = New-Object Threading.Mutex($false, 'Local\FocusAssistantSetup')
    $locked = $mutex.WaitOne(0)
    if (-not $locked) { throw 'Another Focus installer is already running.' }
    if (Get-Process -Name Focus -ErrorAction SilentlyContinue) {
        throw 'Close Focus before installing or updating it.'
    }

    if (-not (Test-Path $pythonExe)) {
        Write-Host '[1/4] Downloading Python from python.org...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $pythonInstaller = Join-Path $installRoot 'python-installer.exe'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.9/python-3.13.9-amd64.exe' -OutFile $pythonInstaller
        $signature = Get-AuthenticodeSignature -FilePath $pythonInstaller
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Python Software Foundation(?:,|$)') {
            Remove-Item -LiteralPath $pythonInstaller -Force
            throw 'The Python installer signature could not be verified. Installation was stopped.'
        }
        Write-Host 'Installing Python for your Windows account (no administrator access needed)...'
        $process = Start-Process -FilePath $pythonInstaller -ArgumentList @(
            '/quiet', 'InstallAllUsers=0', ('TargetDir="{0}"' -f $pythonRoot),
            'Include_pip=1', 'Include_launcher=0', 'Include_test=0',
            'Include_doc=0', 'Include_tcltk=0', 'AssociateFiles=0',
            'Shortcuts=0', 'PrependPath=0'
        ) -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010) -or -not (Test-Path $pythonExe)) {
            throw "Python installation failed (exit $($process.ExitCode))."
        }
        Remove-Item -LiteralPath $pythonInstaller -Force
    }
    Write-Host '[2/4] Preparing Focus...'
    if (-not (Test-Path $buildPython)) {
        Invoke-Checked -Program $pythonExe -Arguments @('-m', 'venv', $venvRoot)
    }
    Invoke-Checked -Program $buildPython -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', (Join-Path $sourceRoot 'requirements.txt'), 'pyinstaller>=6.16,<7')

    Write-Host '[3/4] Creating the Windows app. This can take a few minutes...'
    $workRoot = Join-Path $installRoot 'Build'
    New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
    Invoke-Checked -Program $buildPython -Arguments @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
        '--name', 'Focus', '--collect-all', 'keyring', '--collect-submodules', 'pynput',
        '--paths', $sourceRoot,
        '--distpath', $applicationRoot, '--workpath', (Join-Path $workRoot 'work'),
        '--specpath', $workRoot, (Join-Path $sourceRoot 'main.py')
    )
    $appExe = Join-Path $applicationRoot 'Focus\Focus.exe'
    if (-not (Test-Path $appExe)) { throw 'The Windows app was not created.' }

    Write-Host '[4/4] Adding your desktop shortcut...'
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $desktop 'Focus.lnk'))
    $shortcut.TargetPath = $appExe
    $shortcut.WorkingDirectory = Split-Path $appExe
    $shortcut.Description = 'Focus screenshot study assistant'
    $shortcut.Save()
    Write-Host 'Done! In Focus, open Settings and add your own OpenAI API key.'
    Start-Process -FilePath $appExe
} catch {
    Write-Host ("Installation stopped: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
}
