@echo off
setlocal

set APP=%~dp0bin\InventoryDesktopApp.exe

if not exist "%APP%" (
  echo InventoryDesktopApp.exe が見つかりません。
  echo 先に build.bat を実行してください。
  pause
  exit /b 1
)

start "" "%APP%"
