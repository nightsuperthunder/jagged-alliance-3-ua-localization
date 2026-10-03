@echo off
setlocal
chcp 65001 >nul
title Українська локалізація Jagged Alliance 3 - видалення

rem Видаляє лише теку мода з %AppData%\Jagged Alliance 3\Mods. Збереження й налаштування гри не чіпає.

set "DEST=%APPDATA%\Jagged Alliance 3\Mods\JA3UkrLoc"

echo.
echo   Українська локалізація Jagged Alliance 3 - видалення
echo   =====================================================
echo.

if not exist "%DEST%\" goto none

rmdir /s /q "%DEST%"
if exist "%DEST%\" goto fail
echo   Мод видалено. Гра знову буде англійською (після перезапуску).
echo.
goto end

:none
echo   Мод не встановлено - теки "%DEST%" немає.
echo.
goto end

:fail
echo   [X] Не вдалося видалити теку. Закрийте гру й спробуйте ще раз
echo       або видаліть теку вручну: "%DEST%"
echo.

:end
pause
endlocal
