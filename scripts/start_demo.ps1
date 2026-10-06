param([string]$PythonExe = "python", [int]$Port = 8768)
$ErrorActionPreference = "Stop"
$repoPath = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoPath "src"
    & $PythonExe -S -m bridgeqa.cli serve --output (Join-Path $repoPath "artifacts/midterm") --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Demo exited with code $LASTEXITCODE." }
} finally { $env:PYTHONPATH = $previousPythonPath }
