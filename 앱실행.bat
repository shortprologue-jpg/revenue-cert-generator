@echo off
chcp 65001 > nul
set APP_DIR=%~dp0
cd /d "%APP_DIR%"

echo BPT 수익화 인증글 생성기 시작 중...
start "" http://localhost:8502
python -m streamlit run app.py --server.port 8502 --server.headless true
pause
