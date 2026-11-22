# One-shot helper for Windows PowerShell.
# Usage: .\run.ps1 catalog | .\run.ps1 crawl | .\run.ps1 status
param(
    [Parameter(Position = 0)]
    [ValidateSet("catalog", "crawl", "status", "verify", "report")]
    [string]$Command = "status"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

switch ($Command) {
    "report" { python "$here\tools\report.py" }
    default  { python "$here\tools\skillget.py" $Command }
}
