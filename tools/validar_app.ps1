param(
    [ValidateSet("all", "root")]
    [string]$Profile = "all",
    [switch]$KeepTemp
)

$args = @("$PSScriptRoot\validate_app.py", "--profile", $Profile)

if ($KeepTemp) {
    $args += "--keep-temp"
}

python @args
exit $LASTEXITCODE
