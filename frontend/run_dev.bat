@echo off
cd /d "%~dp0"
echo Starting Vite dev server...
node node_modules\vite\bin\vite.js --host --port 5173
pause
