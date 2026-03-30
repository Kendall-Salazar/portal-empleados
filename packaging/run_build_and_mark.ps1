param(
    [Parameter(Mandatory = $true)][string]$StatusFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    & (Join-Path $PSScriptRoot "build.ps1")
    Set-Content -Path $StatusFile -Value "success" -Encoding UTF8
}
catch {
    $message = "error`n" + ($_ | Out-String)
    Set-Content -Path $StatusFile -Value $message -Encoding UTF8
    throw
}
