@echo off
chcp 65001 >nul
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 缺少本项目 .venv，请按 README 的准备步骤安装本地依赖。
    popd
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 launch_local.py %*
set "astro_exit=%errorlevel%"
popd
if not "%astro_exit%"=="0" pause
exit /b %astro_exit%
