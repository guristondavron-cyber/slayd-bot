@echo off
chcp 65001 >nul
title Server uchun ZIP arxiv tayyorlash
cd /d "%~dp0"

echo ==========================================================
echo   SERVERGA YUKLASH UCHUN TAYYOR ZIP FAYL YASASH
echo ==========================================================
echo.

powershell -NoProfile -Command "$zipPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'slide_bot_deploy.zip'; if (Test-Path $zipPath) { Remove-Item $zipPath -Force }; $files = Get-ChildItem -Path (Get-Location) -File | Where-Object { $_.Name -notin @('.env', 'bot.log') }; Compress-Archive -Path $files.FullName -DestinationPath $zipPath -Force; Write-Host '[OK] Ish stolidagi slide_bot_deploy.zip muvaffaqiyatli yangilandi!' -ForegroundColor Green"

echo.
echo Tayyor ZIP fayl Ish stolingizda (Desktop) yaratildi:
echo -> slide_bot_deploy.zip
echo.
pause
