@echo off
title Flashcard Planet Launcher

cd /d C:\Flashcard-planet

echo Starting Flashcard Planet...
echo.

echo [1/3] Starting Docker database...
start "Flashcard DB" cmd /k "cd /d C:\Flashcard-planet && docker compose up -d"

timeout /t 5 >nul

echo [2/3] Starting FastAPI backend...
start "Flashcard API" cmd /k "cd /d C:\Flashcard-planet && call .venv\Scripts\activate.bat && python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000"

timeout /t 3 >nul

echo.
echo Flashcard Planet startup commands launched.
echo Note: Discord bot is archived (archive/discord-bot-2026/). Alert delivery uses webhook only.
pause