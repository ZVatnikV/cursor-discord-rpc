$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

python -m pip install -r requirements.txt -q
python -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name "CursorDiscordRPC" `
    --add-data "src/web;src/web" `
    --hidden-import webview `
    --hidden-import pypresence `
    --hidden-import pystray `
    --hidden-import PIL `
    --hidden-import psutil `
    run.py

Write-Host "Done -> dist\CursorDiscordRPC.exe"
