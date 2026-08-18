@echo off
setlocal

for %%P in (5173 8000) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
    taskkill /PID %%A /F >nul 2>&1
  )
)

echo Stopped listeners on ports 5173 and 8000 (if present).
