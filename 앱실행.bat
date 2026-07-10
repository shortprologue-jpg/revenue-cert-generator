@echo off
chcp 65001 > nul
set STREAMLIT=C:\Users\xytyp\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Scripts\streamlit.exe
set APP_DIR=%~dp0

echo BPT 수익화 인증글 생성기 시작 중...
cd /d "%APP_DIR%"
start "" http://localhost:8502
"%STREAMLIT%" run app.py --server.port 8502 --server.headless true
pause
