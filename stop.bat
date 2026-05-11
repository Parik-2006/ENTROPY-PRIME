@echo off
cd /d "%~dp0"
echo Stopping Entropy Prime dev services...
docker-compose -f docker-compose.dev.yml down --remove-orphans
echo Done. Close the Backend and Frontend windows manually if still open.
pause
