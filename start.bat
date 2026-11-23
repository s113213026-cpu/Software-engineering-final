@echo off
setlocal
pushd "%~dp0" || exit /b 1

python start.py
set "portal_exit=%errorlevel%"
popd
if not "%portal_exit%"=="0" pause
exit /b %portal_exit%
