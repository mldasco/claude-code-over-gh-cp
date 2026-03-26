param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

if (Test-Path "venv\Scripts\python.exe") {
    & "venv\Scripts\python.exe" "scripts\run.py" @Args
} else {
    & python "scripts\run.py" @Args
}

exit $LASTEXITCODE
