@echo off
chcp 65001 >nul
echo 正在切换到 Claude Sonnet 4.6...
copy /y "C:\Users\78590\.claude\claude sonnet4.6 settings.json" "C:\Users\78590\.claude\settings.json" >nul
echo 已切换，正在启动 Claude Code...
cd /d "%~dp0"
claude