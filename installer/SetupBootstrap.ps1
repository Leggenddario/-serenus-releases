param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$PythonInstaller
)
# SERENUS_WINDOWS_PS_MODULE_PATH_FIX_V1
# When Windows PowerShell 5.1 is launched by a process that also uses
# PowerShell 7, PSModulePath may contain incompatible PS7 module folders.
# Use only the standard Windows PowerShell module roots in this child process.
$winPsModuleRoots = @(
    (Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\Modules'),
    (Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules'),
    (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\Modules')
)
$env:PSModulePath = ($winPsModuleRoots -join [IO.Path]::PathSeparator)
$ErrorActionPreference = 'Stop'
$rootPath = [IO.Path]::GetFullPath($Root)
$logs = Join-Path $rootPath 'install-logs'
New-Item -Path $logs -ItemType Directory -Force | Out-Null
$bootstrapLog = Join-Path $logs 'bootstrap.log'
$marker = Join-Path $logs 'bootstrap-success.txt'
Remove-Item -LiteralPath $marker -ErrorAction SilentlyContinue
try { Start-Transcript -Path $bootstrapLog -Append -ErrorAction Stop | Out-Null } catch { Write-Warning $_.Exception.Message }
try {
    Write-Host ('Serenus bootstrap started: ' + (Get-Date -Format o))
    Write-Host ('Root: ' + $rootPath)
    Write-Host ('Python installer: ' + $PythonInstaller)
    Write-Host ('Python installer exists: ' + (Test-Path -LiteralPath $PythonInstaller))
    $py = Join-Path $rootPath 'python-runtime\python.exe'
    $launcher = Join-Path $rootPath 'launcher'
    $key = Join-Path $launcher 'release-public-key.txt'
    $config = Join-Path $launcher 'release-config.txt'
    if (!(Test-Path -LiteralPath $key)) { throw 'Chiave pubblica mancante: installazione bloccata' }
    if ((Get-Content -LiteralPath $key -Raw).Trim().Length -lt 40) { throw 'Chiave pubblica non valida: installazione bloccata' }
    $state = Join-Path $rootPath 'state\update-state.json'
    if (Test-Path $state) { throw 'Installazione Serenus gia presente. Usa Updater per aggiornare.' }
    if (!(Test-Path $py)) {
        Write-Host 'Installazione Python locale (senza modificare PATH di sistema)...'
        Import-Module Microsoft.PowerShell.Security -ErrorAction Stop
        $sig=Get-AuthenticodeSignature -FilePath $PythonInstaller
        if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Firma del programma Python non verificata' }
        $pythonLog = Join-Path $logs 'python-installer.log'
        $args = '/quiet InstallAllUsers=0 Include_pip=1 Include_launcher=0 PrependPath=0 Include_test=0 TargetDir="' + (Join-Path $rootPath 'python-runtime') + '" /log "' + $pythonLog + '"'
        Write-Host ('Launching official Python installer: ' + $args)
        $proc = Start-Process -FilePath $PythonInstaller -ArgumentList $args -Wait -PassThru
        if ($proc.ExitCode -ne 0) { throw "Installazione Python fallita (codice $($proc.ExitCode))" }
    }
    if (!(Test-Path -LiteralPath $py)) {
        $candidates = @(Get-ChildItem -LiteralPath $rootPath -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 12 -ExpandProperty FullName)
        Write-Host ('Python search under Serenus root: ' + ($candidates -join '; '))
        throw ('Python non trovato nella cartella prevista: ' + $py + '. Controllare python-installer.log')
    }
    & $py --version
    if ($LASTEXITCODE -ne 0) { throw 'Il runtime Python installato non si avvia' }
    $venvPython = Join-Path $launcher '.venv\Scripts\python.exe'
    if (!(Test-Path $venvPython)) {
        & $py -m venv (Join-Path $launcher '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Impossibile creare ambiente Updater' }
    }
    & $venvPython -m pip install 'cryptography>=42,<48' --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'Installazione libreria firme digitali non riuscita' }
    # The updater downloads only a valid signed stable release and runs a health check.
    Push-Location $launcher
    try {
        & $venvPython -m updater.cli apply --root $rootPath --repo 'Leggenddario/-serenus-releases' --public-key $key
        if ($LASTEXITCODE -ne 0) { throw 'Download, verifica o attivazione Serenus falliti' }
    } finally { Pop-Location }
    Set-Content -LiteralPath $marker -Encoding ASCII -Value ('OK ' + (Get-Date -Format o))
    Write-Host 'Serenus installato correttamente.'
    exit 0
} catch {
    Write-Host ('ERRORE: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('Bootstrap log: ' + $bootstrapLog)
    exit 1
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}

