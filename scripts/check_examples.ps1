param([string]$PythonExe = "python")
$ErrorActionPreference = "Stop"
$repoPath = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoPath "src"
    & $PythonExe -m bridgeqa.cli validate (Join-Path $repoPath "data/examples/samples.jsonl")
    if ($LASTEXITCODE -ne 0) { throw "Sample validation failed." }
    & $PythonExe -m bridgeqa.cli evaluate (Join-Path $repoPath "data/examples/samples.jsonl") (Join-Path $repoPath "data/examples/predictions.jsonl")
    if ($LASTEXITCODE -ne 0) { throw "Reference evaluation failed." }
} finally {
    $env:PYTHONPATH = $previousPythonPath
}
