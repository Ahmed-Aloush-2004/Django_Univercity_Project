@echo off
set PROJECT_DIR=%~dp0

set CONFIG_PATH=%PROJECT_DIR%nginx.conf

cd /d C:\nginx
echo Starting Nginx with project configuration...
nginx.exe -p C:\nginx\ -c "%CONFIG_PATH%"

pause