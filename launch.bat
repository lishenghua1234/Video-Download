@echo off
cd /d D:\WorFlow\AntiGravity

:: 检查本地 8001 端口是否已经提供服务 (避免重复启动导致端口占用崩溃)
netstat -ano | findstr :8001 >nul
if %errorlevel% neq 0 (
    echo Starting VideoSnap Engine...
    :: 在后台拉起 FastAPI/uvicorn 底层服务
    start /b uv run uvicorn main:app --host 0.0.0.0 --port 8001
    :: 强制挂起 3 秒钟，等待 Python 引擎完整加载完毕
    timeout /t 3 /nobreak >nul
)

:: 拉起属于用户的极简客户端微端！
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app=http://localhost:8001
