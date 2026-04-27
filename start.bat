@echo off
cd /d C:\Git\JRDB_data
set PATH=C:\Program Files\nodejs;%PATH%

echo Working directory: %CD%
node --version
if errorlevel 1 (
  echo ERROR: node not found
  pause
  exit /b 1
)

for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do (
  taskkill /F /PID %%a >nul 2>&1
)

echo Starting JRDB server...
start "JRDB Server" cmd /k "cd /d C:\Git\JRDB_data && set PATH=C:\Program Files\nodejs;%PATH% && npx ts-node src/server.ts"

echo Waiting for server to start...
timeout /t 5 /nobreak >nul

start http://localhost:3000
echo Done.
pause
