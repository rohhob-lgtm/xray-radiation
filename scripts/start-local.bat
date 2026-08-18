@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "BACKEND_DIR=%REPO_ROOT%\backend"
set "FRONTEND_DIR=%REPO_ROOT%\artifacts\xray-academy"
set "DB_FILE=%BACKEND_DIR%\xray_local.db"
set "DB_URL=sqlite:///%DB_FILE:\=/%"

for %%P in (5173 8000) do (
	for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
		taskkill /PID %%A /F >nul 2>&1
	)
)

echo Using repository: %REPO_ROOT%
echo Using database:   %DB_FILE%

start "xray-backend" cmd /k "cd /d "%BACKEND_DIR%" && set DATABASE_URL=%DB_URL% && set OLLAMA_BASE_URL=http://127.0.0.1:11434 && set OLLAMA_MODEL=qwen2.5-7b-fast6:latest && set DEVELOPMENT_MODE=true && set DISABLE_TRANSLATION_RATE_LIMIT=true && set DISABLE_HOURLY_QUOTA=true && set DISABLE_DAILY_QUOTA=true && set DISABLE_MONTHLY_QUOTA=true && set LOCAL_DEVELOPER_USER_IDS=dev-user-local && if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000) else (python -m uvicorn main:app --host 127.0.0.1 --port 8000)"

start "xray-frontend" cmd /k "cd /d "%FRONTEND_DIR%" && set FRONTEND_PORT=5173 && set PORT=5173 && set BASE_PATH=/ && .\node_modules\.bin\vite.cmd --config vite.config.ts --host 0.0.0.0 --strictPort"

echo Launcher started backend and frontend from this worktree.
