@echo off
title Flashcard Planet Stopper

cd /d C:\Flashcard-planet

echo Stopping Flashcard Planet...
echo.

echo [1/3] Stopping Discord bot window...
taskkill /FI "WINDOWTITLE eq Flashcard Bot*" /T /F

echo [2/3] Stopping FastAPI backend window...
taskkill /FI "WINDOWTITLE eq Flashcard API*" /T /F

echo [3/3] Stopping Docker database...
docker compose down

echo.
echo Flashcard Planet stopped.
pause