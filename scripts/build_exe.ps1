# Build a single-file EXE with PyInstaller
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$python = (Get-Command python).Source
Write-Host "Using $python"

python -m pip install -r requirements.txt --upgrade
python -m pip install pyinstaller

$icon = "assets\icon.ico"
$iconArg = @()
if (Test-Path $icon) {
    $iconArg = @("--icon", $icon)
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "CursorDiscordRPC" `
    --add-data "assets;assets" `
    @iconArg `
    --hidden-import customtkinter `
    --hidden-import pypresence `
    --hidden-import pystray `
    --hidden-import PIL `
    --hidden-import PIL._tkinter_finder `
    --collect-all customtkinter `
    run.py

Write-Host ""
Write-Host "Done -> dist\CursorDiscordRPC.exe"
