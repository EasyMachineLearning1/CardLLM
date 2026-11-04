@echo off
rem ============================================================
rem  Запуск сервиса карточек двойным щелчком.
rem  Сначала ставятся зависимости (если их нет), затем сервис
rem  запускается и через пару секунд открывается браузер.
rem  Окно НЕЛЬЗЯ закрывать, пока работаете с программой.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
title Сервис карточек приборов

echo.
echo   Запускаем сервис карточек...
echo   НЕ закрывайте это окно, пока работаете с программой!
echo   По окончании работы просто закройте это окно.
echo.

rem --- Проверяем, есть ли uv (рекомендуемый способ) ---
where uv >nul 2>nul
if %errorlevel%==0 (
    echo   Проверяем зависимости...
    uv sync
    echo   Запускаем...
    start "" cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8000/"
    uv run uvicorn app.main:app
) else (
    rem --- Запасной путь: обычный Python ---
    where python >nul 2>nul
    if not %errorlevel%==0 (
        echo   [ОШИБКА] Не найден ни uv, ни Python.
        echo   Попросите ИТ-специалиста установить Python или uv.
        pause
        exit /b 1
    )
    if not exist .venv (
        echo   Первый запуск: устанавливаем зависимости, это займёт пару минут...
        python -m venv .venv
        .venv\Scripts\pip install -r requirements.txt
    )
    echo   Запускаем...
    start "" cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:8000/"
    .venv\Scripts\python -m uvicorn app.main:app
)

echo.
echo   Сервис остановлен. Окно можно закрыть.
pause
