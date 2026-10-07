@echo off
REM [Run instructions](README.md). Keeps the local read-only server in this console.
chcp 65001 >nul
cd /d "%~dp0"
echo BridgeQA: http://127.0.0.1:8765
echo 保持此窗口打开；在浏览器访问上方地址。按 Ctrl+C 停止服务。
python "%~dp0server.py" --port 8765
pause
