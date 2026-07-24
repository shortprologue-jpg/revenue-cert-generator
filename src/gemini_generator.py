"""
Google Gemini(google-genai SDK)를 호출해 인증글을 스트리밍 생성.
.env의 GEMINI_API_KEY 필요 (무료 티어). Claude Code CLI 대비 오버헤드가 없어 훨씬 빠름.
"""
import os
from collections.abc import Generator

import httpx
from google import genai
from google.genai import errors, types

# build_user_message / 시스템 프롬프트 경로는 모델과 무관하므로 재사용.
from src.claude_generator import SYSTEM_PROMPT_FILE, build_user_message

DEFAULT_MODEL = "gemini-3.5-flash"
_PLACEHOLDER = "여기에_제미나이_키_붙여넣기"


def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not key or key == _PLACEHOLDER:
        return ""
    return key


def check_key() -> tuple[bool, str]:
    """Gemini API 키 존재 확인. (is_ok, message)"""
    if not _get_api_key():
        return False, "GEMINI_API_KEY 없음 — .env에 추가하세요."
    return True, "OK"


def _fetch_image_parts(urls: list[str] | None) -> list:
    """노션 이미지 URL들을 bytes로 받아 Gemini Part로 변환. 실패한 건 건너뜀."""
    parts = []
    for url in urls or []:
        try:
            resp = httpx.get(url, timeout=20, follow_redirects=True)
            if resp.status_code == 200 and resp.content:
                mime = resp.headers.get("content-type", "image/png").split(";")[0].strip()
                if not mime.startswith("image/"):
                    mime = "image/png"
                parts.append(types.Part.from_bytes(data=resp.content, mime_type=mime))
        except Exception:  # noqa: BLE001 — 개별 이미지 실패는 무시하고 진행
            continue
    return parts


def _guess_img_mime(data: bytes) -> str:
    """이미지 bytes 시그니처로 MIME 추정(업로드 파일용)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _bytes_image_parts(images: list[bytes] | None) -> list:
    """업로드된 이미지 bytes(전달 수익화 데이터 캡처 등)를 Gemini Part 로 변환."""
    parts = []
    for data in images or []:
        if data:
            parts.append(types.Part.from_bytes(data=data, mime_type=_guess_img_mime(data)))
    return parts


def generate_certification_post(
    member_name: str,
    period: str,
    revenue: str,
    kakao_content: str,
    notion_context: str,
    notion_images: list[str] | None = None,
    prev_month_text: str = "",
    prev_month_images: list[bytes] | None = None,
    model: str = DEFAULT_MODEL,
) -> Generator[str, None, None]:
    """Gemini로 인증글을 스트리밍 생성. Yields: 텍스트 청크.

    notion_images: 콘관시·콘텐츠 피드백 캡처 이미지 URL들. 텍스트와 함께 보내
    이미지 속 수치(전환율·객단가 등)까지 읽어 활용하게 한다(멀티모달).
    """
    api_key = _get_api_key()
    if not api_key:
        raise PermissionError(
            "GEMINI_API_KEY가 없습니다. .env에 발급받은 키를 넣으세요."
        )

    system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    user_message = build_user_message(
        member_name, period, revenue, kakao_content, notion_context, prev_month_text
    )

    contents = [types.Part.from_text(text=user_message)] + _fetch_image_parts(notion_images)
    prev_parts = _bytes_image_parts(prev_month_images)
    if prev_parts:
        # 전달 이미지에 명확한 구분 라벨을 붙인다 — 없으면 모델이 이번 달 콘관시
        # 이미지와 섞어, 전달 데이터를 비교하지 못하거나 이번 달 수치로 오인한다.
        contents.append(types.Part.from_text(
            text=(
                "\n\n[중요] 아래 첨부 이미지는 **전달(前月) 수익화 데이터** 캡처입니다. "
                "위의 노션/이번 달 콘관시 이미지와 반드시 구분하세요. "
                "이번 달 수치를 전달과 비교해 성과/정체/하락을 판단하는 용도로만 쓰고, "
                "전달 수치를 이번 달 것으로 오인하지 마세요."
            )
        ))
        contents += prev_parts

    client = genai.Client(api_key=api_key)
    try:
        stream = client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except errors.ClientError as e:
        code = getattr(e, "code", None)
        if code == 403:
            raise PermissionError(
                f"Gemini API 키 인증 실패 (키를 확인하세요): {getattr(e, 'message', e)}"
            ) from e
        if code == 429:
            raise RuntimeError(
                f"Gemini 호출 한도 초과 — 잠시 후 다시 시도하세요: {getattr(e, 'message', e)}"
            ) from e
        raise RuntimeError(f"Gemini 클라이언트 오류: {getattr(e, 'message', e)}") from e
    except errors.ServerError as e:
        raise RuntimeError(f"Gemini 서버 오류(잠시 후 재시도): {getattr(e, 'message', e)}") from e
