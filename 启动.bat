@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   智能财务记账助手 - 启动中...
echo ============================================
echo.
echo 启动后请不要关闭本窗口，关闭即停止服务。
echo 然后在浏览器打开： http://127.0.0.1:8010
echo.
D:\Users\Lenovo\anaconda3\envs\langchain1.2\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
pause
