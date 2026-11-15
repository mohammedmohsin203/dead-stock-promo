@echo off
rem Opens two terminals: the promo API (port 8000) and the GrocerGo store (port 3000).
cd /d "%~dp0"

if not exist "promo-engine\.venv\Scripts\activate.bat" (
  echo promo-engine\.venv is missing. See promo-engine\README.md, Setup.
  pause
  exit /b 1
)
if not exist "promo-engine\.env" copy "promo-engine\.env.example" "promo-engine\.env" >nul
if not exist "grocergo\.env.local" (
  >"grocergo\.env.local" echo NEXTAUTH_URL=http://localhost:3000
  >>"grocergo\.env.local" echo NEXTAUTH_SECRET=demo-%RANDOM%%RANDOM%%RANDOM%%RANDOM%
)

start "Promo API :8000" cmd /k "cd /d "%~dp0promo-engine" && call .venv\Scripts\activate.bat && python scripts\generate_data.py && uvicorn api.main:app --reload --port 8000"
start "GrocerGo :3000" cmd /k "cd /d "%~dp0grocergo" && npm run dev"

echo Store:  http://localhost:3000
echo Admin:  http://localhost:8000/admin
echo Docs:   http://localhost:8000/docs
