@echo off
setlocal

pyinstaller --onefile --windowed --name "PDF Manual Optimizer" app/main.py

endlocal
