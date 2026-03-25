@echo off
setlocal

where python >nul 2>nul
if errorlevel 1 (
  echo Python が見つかりません。
  echo Python 3.11+ をインストールしてください。
  pause
  exit /b 1
)

python -m pip show PySide6 >nul 2>nul
if errorlevel 1 (
  echo PySide6 が見つかりません。
  echo python -m pip install -r requirements.txt
  pause
  exit /b 1
)

python "%~dp0warehouse_app.py"
