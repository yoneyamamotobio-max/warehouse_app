@echo off
setlocal

set CSC=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe

if not exist "%CSC%" (
  echo C# compiler not found: %CSC%
  exit /b 1
)

if not exist "bin" mkdir bin

"%CSC%" /nologo /target:winexe /out:bin\InventoryDesktopApp.exe /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Runtime.Serialization.dll Program.cs

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo Build succeeded: bin\InventoryDesktopApp.exe
