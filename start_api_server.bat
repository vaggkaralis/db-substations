@echo off
REM Start Flask API Server for DB Substations
REM This runs the server on http://localhost:5000

echo Starting Flask API Server...
echo.
echo Server will be available at: http://localhost:5000
echo API endpoints at: http://localhost:5000/api
echo.
echo To test, open in browser: http://localhost:5000/api/health
echo.
echo Press Ctrl+C to stop the server
echo.

.venv\Scripts\python.exe api_server.py

pause
