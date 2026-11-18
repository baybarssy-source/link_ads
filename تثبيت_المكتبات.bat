@echo off
chcp 65001 >nul
rem يثبّت مكتبات «استوديو الإعلانات» (القائمة في «المكتبات_المطلوبة.txt»).
cd /d "%~dp0"
echo.
echo  تثبيت مكتبات استوديو الإعلانات...
echo  (يلزم اتّصال بالإنترنت. إن فشل التنزيل فشغّل VPN وأعد المحاولة.)
echo.
python --version
if errorlevel 1 (
  echo.
  echo  لم أجد Python. ثبّته أوّلًا من python.org ^(الإصدار 3.12^) وفعّل خيار Add python.exe to PATH.
  pause
  exit /b 1
)
python -m pip install -r "المكتبات_المطلوبة.txt"
echo.
if errorlevel 1 (
  echo  حدث خطأ أثناء التثبيت. اقرأ الرسالة أعلاه.
) else (
  echo  تمّ. المكتبات كلّها مثبّتة.
)
echo.
pause
