# --------------------------------------------
# ComfyVN Import Sanity Checker
# Scans Python files for invalid or circular imports
# --------------------------------------------

$Root = Split-Path $MyInvocation.MyCommand.Path -Parent
$TargetRoot = Join-Path $Root ".."

Write-Host "🔍 Scanning ComfyVN source tree for invalid imports..." -ForegroundColor Cyan

# 1️⃣ Find all Python import lines
$imports = Get-ChildItem -Recurse "$TargetRoot\comfyvn" -Include *.py |
    Select-String -Pattern "^(from|import)\s+comfyvn" |
    Select-Object Path, LineNumber, Line

# 2️⃣ Detect circular imports referencing wrong modules (e.g. main_window under widgets)
$badImports = $imports | Where-Object {
    $_.Line -match "gui\.widgets\.main_window" -or
    $_.Line -match "modules\." -or
    $_.Line -match "gui\.components\."
}

if ($badImports) {
    Write-Host "`n⚠️ Found invalid or outdated imports:" -ForegroundColor Yellow
    $badImports | ForEach-Object {
        Write-Host "  $($_.Path):$($_.LineNumber) -> $($_.Line.Trim())" -ForegroundColor DarkYellow
    }
} else {
    Write-Host "✅ No outdated imports found." -ForegroundColor Green
}

# 3️⃣ Test-import every top-level module to detect broken dependencies
Write-Host "`n🧠 Verifying top-level module imports..."
$modules = Get-ChildItem "$TargetRoot" -Directory
foreach ($mod in $modules) {
    $modName = $mod.Name
    Write-Host "  → Testing comfyvn.$modName ..." -NoNewline
    try {
        & "$TargetRoot\.venv\Scripts\python.exe" -c "import comfyvn.$modName" 2>$null
        Write-Host " OK" -ForegroundColor Green
    } catch {
        Write-Host " FAILED" -ForegroundColor Red
    }
}

Write-Host "`n🧹 Scan complete."
