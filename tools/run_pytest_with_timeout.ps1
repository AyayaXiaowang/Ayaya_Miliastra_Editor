param(
  [int] $TimeoutSeconds
  ,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]] $PytestArgs
)

$ErrorActionPreference = "Stop"

$DEFAULT_TIMEOUT_SECONDS = 60
if (-not $TimeoutSeconds) {
  $TimeoutSeconds = $DEFAULT_TIMEOUT_SECONDS
}

$pythonArgs = @("-X", "utf8", "-m", "pytest") + $PytestArgs
$p = Start-Process -FilePath "python" -ArgumentList $pythonArgs -PassThru -NoNewWindow

Wait-Process -Id $p.Id -Timeout $TimeoutSeconds
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) {
  Stop-Process -Id $p.Id -Force
  throw "pytest timeout (${TimeoutSeconds}s)"
}

exit $p.ExitCode

