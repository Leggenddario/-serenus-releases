param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$PythonInstaller
)
$ErrorActionPreference = 'Stop'
try {
    $rootPath = [IO.Path]::GetFullPath($Root)
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
        $sig=Get-AuthenticodeSignature -FilePath $PythonInstaller
        if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Firma del programma Python non verificata' }
        $args = '/quiet InstallAllUsers=0 Include_pip=1 Include_launcher=0 PrependPath=0 Include_test=0 TargetDir="' + (Join-Path $rootPath 'python-runtime') + '"'
        $proc = Start-Process -FilePath $PythonInstaller -ArgumentList $args -Wait -PassThru
        if ($proc.ExitCode -ne 0) { throw "Installazione Python fallita (codice $($proc.ExitCode))" }
    }
    if (!(Test-Path $py)) { throw 'Python non trovato nella cartella prevista' }
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
    Write-Host 'Serenus installato correttamente.'
    exit 0
} catch {
    Write-Host "ERRORE: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
