Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$workDir = Join-Path $scriptDir "build"
$appDir = Join-Path $scriptDir "Chronos"
$specPath = Join-Path $scriptDir "Chronos.spec"
$pyInstallerConfigDir = Join-Path $scriptDir ".pyinstaller"

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDir,
        [Parameter(Mandatory = $true)][string]$DestinationDir
    )

    if (-not (Test-Path $SourceDir)) {
        throw "No existe la carpeta requerida: $SourceDir"
    }

    New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
    Copy-Item -Path (Join-Path $SourceDir "*") -Destination $DestinationDir -Recurse -Force
}

function Copy-FileSafe {
    param(
        [Parameter(Mandatory = $true)][string]$SourceFile,
        [Parameter(Mandatory = $true)][string]$DestinationFile
    )

    if (-not (Test-Path $SourceFile)) {
        throw "No existe el archivo requerido: $SourceFile"
    }

    $destinationParent = Split-Path -Parent $DestinationFile
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    Copy-Item -Path $SourceFile -Destination $DestinationFile -Force
}

if (Test-Path $appDir) {
    Write-Output "[1/6] Limpiando carpeta previa del ejecutable..."
    Remove-Item -Path $appDir -Recurse -Force
}

if (Test-Path $workDir) {
    Write-Output "[1/6] Limpiando carpeta temporal de compilacion..."
    Remove-Item -Path $workDir -Recurse -Force
}

$env:PYINSTALLER_CONFIG_DIR = $pyInstallerConfigDir
New-Item -ItemType Directory -Path $pyInstallerConfigDir -Force | Out-Null

Write-Output "[2/6] Ejecutando PyInstaller..."
python -m PyInstaller --noconfirm --distpath $scriptDir --workpath $workDir $specPath

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller falló."
}

Write-Output "[3/6] Copiando frontend..."
Copy-DirectoryContents -SourceDir (Join-Path $projectRoot "frontend") -DestinationDir (Join-Path $appDir "frontend")
Write-Output "[4/6] Copiando datos de planillas..."
Copy-DirectoryContents -SourceDir (Join-Path $projectRoot "planillas") -DestinationDir (Join-Path $appDir "planillas")
Write-Output "[5/6] Copiando plantilla y recursos auxiliares..."
Copy-FileSafe -SourceFile (Join-Path $projectRoot "backend\\formato_template.xlsm") -DestinationFile (Join-Path $appDir "backend\\formato_template.xlsm")

$databaseJson = Join-Path $projectRoot "database.json"
if (Test-Path $databaseJson) {
    Copy-FileSafe -SourceFile $databaseJson -DestinationFile (Join-Path $appDir "database.json")
}

$logoJpeg = Join-Path $projectRoot "slm logo.jpeg"
if (Test-Path $logoJpeg) {
    Copy-FileSafe -SourceFile $logoJpeg -DestinationFile (Join-Path $appDir "slm logo.jpeg")
}

New-Item -ItemType Directory -Path (Join-Path $appDir "export_horarios") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $appDir "acciones de empleado") -Force | Out-Null

Write-Output "[6/6] Build finalizado."
Write-Output ""
Write-Output "Empaquetado completado."
Write-Output ("EXE: " + (Join-Path $appDir "Chronos.exe"))
