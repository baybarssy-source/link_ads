@echo off
rem Commit tool launcher. ASCII only: cmd misreads Arabic inside .bat files.
rem The tool lives in one folder; this passes the project folder to it through an ASCII-path stub.
set "STUB=%LOCALAPPDATA%\Programs\git-commit-tool\launch.py"
if not exist "%STUB%" (
    python -c "import ctypes;ctypes.windll.user32.MessageBoxW(0,'\u0644\u0645 \u0623\u062c\u062f \u0623\u062f\u0627\u0629 \u0627\u0644\u0627\u0644\u062a\u0632\u0627\u0645 \u0641\u064a \u0647\u0630\u0627 \u0627\u0644\u062c\u0647\u0627\u0632. \u0634\u063a\u0651\u0644 \u00ab\u062a\u0634\u063a\u064a\u0644 \u0623\u062f\u0627\u0629 \u0627\u0644\u0627\u0644\u062a\u0632\u0627\u0645.bat\u00bb \u0645\u0646 \u0645\u062c\u0644\u0651\u062f\u0647\u0627 \u0645\u0631\u0651\u0629 \u0648\u0627\u062d\u062f\u0629\u060c \u062b\u0645 \u0623\u0639\u062f \u0627\u0644\u0645\u062d\u0627\u0648\u0644\u0629.','\u0623\u062f\u0627\u0629 \u0627\u0644\u0627\u0644\u062a\u0632\u0627\u0645',16)"
    exit /b 1
)
start "" pythonw -X utf8 "%STUB%" "%~dp0."
