@echo off
chcp 65001 >nul
rem استوديو إعلانات فيسبوك: ينشئ صفحة وسيطة مجانية تحوّل من الإعلان إلى Google Play.
cd /d "%~dp0"
start "" pythonw -X utf8 ad_studio.py
if errorlevel 1 python -X utf8 ad_studio.py
