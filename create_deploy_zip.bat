@echo off
chcp 65001 >nul
title Server uchun ZIP arxiv tayyorlash
cd /d "%~dp0"

echo ==========================================================
echo   SERVERGA YUKLASH UCHUN TAYYOR ZIP FAYL YASASH
echo ==========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" pack_deploy.py
) else (
    python pack_deploy.py
)

echo.
echo Tayyor ZIP fayl Ish stolingizda (Desktop) yaratildi:
echo -> slide_bot_deploy.zip
echo -> slayd_bot_fayllari (papka)
echo.
pause
