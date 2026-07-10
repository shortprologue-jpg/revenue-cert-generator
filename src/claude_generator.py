"""
Claude Code CLI를 subprocess로 호출해 텍스트 생성.
별도 API 키 없이 기존 Claude 구독으로 동작.
"""
import os
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path

# Claude Code 실행 파일 경로 (자동 감지 포함)
_CANDIDATE_PATHS = [
    r"C:\Users\xytyp\AppData\Roaming\Claude\claude-code\2.1.156\claude.exe",
    r"C:\Users\xytyp\AppData\Roaming\Claude\claude-code\2.1.154\claude.exe",
]

SYSTEM_PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "system_prompt.md"


def _find_claude_exe() -> str:
    for path in _CANDIDATE_PATHS:
        if Path(path).exists():
            return path
    # PATH에서 찾기
    for candidate in ["claude", "claude.exe", "claude.cmd"]:
        result = subprocess.run(
            ["where", candidate] if os.name == "nt" else ["which", candidate],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[0]
    raise FileNotFoundError(
        "Claude Code 실행 파일을 찾을 수 없습니다. "
        "Claude Code 앱이 설치되어 있는지 확인하세요."
    )


def build_user_message(
    member_name: str,
    period: str,
    revenue: str,
    kakao_content: str,
    notion_context: str,
) -> str:
    notion_section = notion_context.strip() if notion_context.strip() else "(노션 데이터 없음 — 카카오톡 내용만으로 작성)"
    return f"""## 입력 정보

- 회원 이름: {member_name or '(미입력)'}
- 수익화 기간: {period}
- 매출 금액: {revenue}

## 카카오톡 내용
{kakao_content}

## 노션 회원 페이지 기록 (컷오프 적용)
{notion_section}"""


def check_auth() -> tuple[bool, str]:
    """Claude CLI 인증 상태 확인. (is_ok, message)"""
    try:
        exe = _find_claude_exe()
    except FileNotFoundError as e:
        return False, str(e)

    result = subprocess.run(
        [exe, "-p", "ping", "--output-format", "text"],
        capture_output=True, text=True, encoding="utf-8",
        timeout=15,
    )
    if "Not logged in" in result.stderr or "Please run /login" in result.stderr:
        return False, "로그인 필요"
    return True, "OK"


def generate_certification_post(
    member_name: str,
    period: str,
    revenue: str,
    kakao_content: str,
    notion_context: str,
) -> Generator[str, None, None]:
    """
    Claude Code CLI를 호출해 인증글을 스트리밍으로 생성.
    Yields: text chunks
    """
    exe = _find_claude_exe()
    user_message = build_user_message(member_name, period, revenue, kakao_content, notion_context)

    # 긴 프롬프트는 임시 파일로 전달
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(user_message)
        tmp_path = tmp.name

    try:
        cmd = [
            exe, "-p",
            "--system-prompt-file", str(SYSTEM_PROMPT_FILE),
            "--input-format", "text",
            "--output-format", "text",
            "--no-tools",
        ]

        proc = subprocess.Popen(
            cmd,
            stdin=open(tmp_path, "r", encoding="utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 한 문자씩 읽어 실시간 스트리밍
        while True:
            chunk = proc.stdout.read(32)
            if not chunk:
                break
            yield chunk

        proc.wait()

        if proc.returncode != 0:
            stderr_out = proc.stderr.read()
            if "Not logged in" in stderr_out or "Please run /login" in stderr_out:
                raise PermissionError(
                    "Claude Code 로그인이 필요합니다. "
                    "앱 사이드바의 '초기 설정' 버튼을 클릭하세요."
                )
            raise RuntimeError(f"Claude CLI 오류: {stderr_out}")

    finally:
        try:
            import os as _os
            _os.unlink(tmp_path)
        except OSError:
            pass
