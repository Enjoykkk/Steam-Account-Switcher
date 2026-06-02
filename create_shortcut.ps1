# Creates "Steam Switcher" shortcut on the Desktop.
# Run once:  powershell -ExecutionPolicy Bypass -File E:\proj1\create_shortcut.ps1

$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MainScript = Join-Path $ProjectDir 'main.py'

if (-not (Test-Path $MainScript)) {
    Write-Host "main.py not found in $ProjectDir" -ForegroundColor Red
    exit 1
}

$Pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $Pythonw) {
    $Pythonw = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
}
if (-not $Pythonw) {
    Write-Host "pythonw.exe / python.exe not found in PATH" -ForegroundColor Red
    exit 1
}

$DesktopPath = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath 'Steam Switcher.lnk'

$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Pythonw
$Shortcut.Arguments = '"' + $MainScript + '"'
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description = 'Steam Account Switcher'

# Use icon.ico from the project if present; otherwise use the default Python icon
$IconPath = Join-Path $ProjectDir 'icon.ico'
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = $IconPath
} else {
    $Shortcut.IconLocation = $Pythonw + ',0'
}
$Shortcut.Save()

Write-Host "Shortcut created: $ShortcutPath" -ForegroundColor Green
Write-Host "Target: $Pythonw `"$MainScript`""
