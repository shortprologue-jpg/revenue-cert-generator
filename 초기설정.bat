@echo off
chcp 65001 > nul
echo ============================================
echo  BPT 수익화 인증글 생성기 - 초기 설정
echo ============================================
echo.

set CLAUDE=C:\Users\xytyp\AppData\Roaming\Claude\claude-code\2.1.156\claude.exe
set APP_DIR=%~dp0

echo [1단계] Claude Code 로그인 설정 중...
echo  (브라우저가 열리면 로그인 후 완료해주세요)
echo.
"%CLAUDE%" setup-token
echo.

echo [2단계] Notion API 키 설정
echo  notion.so/my-integrations 에서 키를 복사해주세요.
echo.
set /p NOTION_KEY=Notion API 키를 붙여넣기 하세요:

echo NOTION_API_KEY=%NOTION_KEY% > "%APP_DIR%.env"
echo .env 파일 저장 완료!
echo.

echo ============================================
echo  설정 완료! 이제 앱실행.bat 을 실행하세요.
echo ============================================
pause
