@echo off
setlocal
chcp 65001 >nul
title Українська локалізація Jagged Alliance 3 - встановлення

rem Копіює теку мода поруч із цим файлом у %AppData%\Jagged Alliance 3\Mods.
rem Нічого не змінює у файлах гри; перезаписує лише власну теку мода.

set "MODNAME=JA3UkrLoc"
set "SRC=%~dp0%MODNAME%"
set "GAMEDATA=%APPDATA%\Jagged Alliance 3"
set "MODS=%GAMEDATA%\Mods"
set "DEST=%MODS%\%MODNAME%"

echo.
echo   Українська локалізація Jagged Alliance 3 - встановлення
echo   ========================================================
echo.

if not exist "%SRC%\metadata.lua" goto nosrc
if not exist "%GAMEDATA%\" goto nogame
goto gamecheck

:nogame
echo   [!] Не знайдено теку налаштувань гри:
echo       "%GAMEDATA%"
echo       Мабуть, гру ще не запускали на цьому комп'ютері. Тека буде створена,
echo       але якщо гра встановлена нестандартно - див. «Встановлення вручну» в README_UA.txt.
echo.

:gamecheck
tasklist /fi "imagename eq JA3.exe" 2>nul | find /i "JA3.exe" >nul
if errorlevel 1 goto copy
echo   [!] Гра зараз запущена. Мод підхопиться лише після перезапуску гри.
echo.

:copy
echo   Копіюю мод у:
echo   "%DEST%"
robocopy "%SRC%" "%DEST%" /MIR /R:2 /W:1 /NJH /NJS /NDL /NFL /NP >nul
if errorlevel 8 goto fail
if not exist "%DEST%\English.csv" goto fail

echo.
echo   Готово! Мод встановлено.
echo.
echo   Що далі:
echo     1. Запустіть гру.
echo     2. Головне меню - Mod Manager - увімкніть «Українська локалізація».
echo     3. Мова гри має бути English: Options - Gameplay - Language - English.
echo     4. Якщо текст лишився англійським - перезапустіть гру.
echo.
goto end

:nosrc
echo   [X] Поруч із цим файлом немає теки "%MODNAME%".
echo       Спершу розпакуйте ВЕСЬ архів у будь-яку теку, а потім запустіть install.bat звідти.
echo       Не запускайте його прямо з вікна архіву.
echo.
goto end

:fail
echo.
echo   [X] Не вдалося скопіювати файли. Встановіть мод вручну - див. README_UA.txt.
echo.

:end
pause
endlocal
