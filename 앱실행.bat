@echo off
chcp 65001 > nul
set APP_DIR=%~dp0
cd /d "%APP_DIR%"

echo BPT 수익화 인증글 생성기 시작 중...

rem 노트북마다 python 이 venv 등 다른 파이썬을 가리킬 수 있어,
rem streamlit 이 실제로 설치된 파이썬을 자동으로 찾는다 (py -3 우선, 없으면 python).
set PYCMD=
py -3 -c "import streamlit" >nul 2>&1 && set PYCMD=py -3
if not defined PYCMD (
    python -c "import streamlit" >nul 2>&1 && set PYCMD=python
)

if not defined PYCMD (
    echo.
    echo [오류] streamlit 이 설치된 파이썬을 찾지 못했습니다.
    echo        pip install -r requirements.txt 로 의존성을 먼저 설치하세요.
    echo.
    pause
    exit /b 1
)

echo 사용 파이썬: %PYCMD%
start "" http://localhost:8502
%PYCMD% -m streamlit run app.py --server.port 8502 --server.headless true
pause
