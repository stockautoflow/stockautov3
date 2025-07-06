@echo off
setlocal

if "%~1"=="" (
    echo エラー: 引数が指定されていません。
    echo 使用法: %~nx0 ^<引数^>
    echo.
    echo 有効な引数と対応するファイル名:
    echo   i: initialize
    echo   c: core
    echo   b: backtest
    echo   e: evaluation
    echo   r: realtime
    echo   d: dashboard
    goto :eof
)

set "ARG_KEY=%~1"
set "FILENAME="

rem 引数とファイル名のマッピング
if /i "%ARG_KEY%"=="i" set "FILENAME=initialize"
if /i "%ARG_KEY%"=="c" set "FILENAME=core"
if /i "%ARG_KEY%"=="b" set "FILENAME=backtest"
if /i "%ARG_KEY%"=="e" set "FILENAME=evaluation"
if /i "%ARG_KEY%"=="r" set "FILENAME=realtime"
if /i "%ARG_KEY%"=="d" set "FILENAME=dashboard"

if "%FILENAME%"=="" (
    echo エラー: 無効な引数 "%ARG_KEY%" が指定されました。
    echo 有効な引数と対応するファイル名:
    echo   i: initialize
    echo   c: core
    echo   b: backtest
    echo   e: evaluation
    echo   r: realtime
    echo   d: dashboard
    goto :eof
)

echo %FILENAME% スクリプトを実行します...
python ./tools/merge_changes.py scripts/create_%FILENAME%.py

endlocal