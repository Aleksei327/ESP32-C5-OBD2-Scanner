@echo off
rem Etch print window without KiCad (reads the saved board file). Optional argument: path to a .kicad_pcb
start "" "C:\Program Files\KiCad\10.0\bin\pythonw.exe" "%~dp0etch_window.py" %*
