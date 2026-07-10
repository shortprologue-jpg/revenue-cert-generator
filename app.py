import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from src.claude_generator import (
    _find_claude_exe,
    check_auth,
    generate_certification_post,
)
from src.file_saver import save_output
from src.notion_fetcher import (
    NotionFetchError,
    PageNotFoundError,
    compute_cutoff_date,
    fetch_member_page_content,
)

st.set_page_config(
    page_title="BPT 수익화 인증글 생성기",
    page_icon="🏋️",
    layout="wide",
)

st.title("🏋️ BPT 수익화 인증글 생성기")


def parse_revenue_period(period_str: str) -> tuple[date, date]:
    year = date.today().year
    match = re.match(r"(\d{1,2})/(\d{1,2})\s*~\s*(\d{1,2})/(\d{1,2})", period_str.strip())
    if not match:
        raise ValueError(f"기간 형식 오류 (예: 4/13~5/24): '{period_str}'")
    sm, sd, em, ed = map(int, match.groups())
    start = date(year, sm, sd)
    end_year = year if em >= sm else year + 1
    end = date(end_year, em, ed)
    return start, end


# ── 사이드바 ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 설정")

    # ① Notion API 키
    st.subheader("Notion API 키")
    notion_key_input = st.text_input("NOTION_API_KEY", type="password", key="nk",
                                      placeholder="secret_...")
    notion_key = notion_key_input or os.getenv("NOTION_API_KEY", "")
    if notion_key:
        st.success("✅ Notion 키 설정됨")
    else:
        st.warning("⚠️ Notion 키 없음 — .env 파일에 추가하거나 위에 입력")

    st.divider()

    # ② Claude Code 인증 상태
    st.subheader("Claude Code 인증")
    if "claude_auth_ok" not in st.session_state:
        st.session_state["claude_auth_ok"] = False

    col_auth1, col_auth2 = st.columns([2, 1])
    with col_auth2:
        if st.button("확인", key="check_auth"):
            with st.spinner("확인 중..."):
                ok, msg = check_auth()
                st.session_state["claude_auth_ok"] = ok
                st.session_state["claude_auth_msg"] = msg

    with col_auth1:
        if st.session_state.get("claude_auth_ok"):
            st.success("✅ 로그인됨")
        elif "claude_auth_msg" in st.session_state:
            st.error(f"❌ {st.session_state['claude_auth_msg']}")
        else:
            st.info("버튼으로 상태 확인")

    if not st.session_state.get("claude_auth_ok"):
        with st.expander("🔑 초기 로그인 방법"):
            try:
                exe = _find_claude_exe()
                st.code(f'& "{exe}" setup-token', language="powershell")
            except FileNotFoundError:
                st.code("claude setup-token", language="powershell")
            st.caption("PowerShell에서 위 명령 실행 → 브라우저 인증 → 완료 후 '확인' 버튼")

    st.divider()
    st.caption("노션 통합(integration)이 회원 페이지에 공유되어 있어야 합니다.")


# ── 메인: 2단 레이아웃 ────────────────────────────────────────────────────────

col_input, col_output = st.columns([1, 1], gap="large")

with col_input:
    st.subheader("입력")

    member_name = st.text_input(
        "회원 이름 (선택 — 이름만, 성 제외)",
        placeholder="혁진",
    )

    period_str = st.text_input("수익화 기간 *", placeholder="4/13~5/24")
    cutoff_date: date | None = None
    if period_str.strip():
        try:
            _, period_end = parse_revenue_period(period_str)
            cutoff_date = compute_cutoff_date(period_end)
            st.caption(
                f"컷오프 날짜: {cutoff_date.month}/{cutoff_date.day} "
                f"(이 날짜 이전 노션 기록만 포함)"
            )
        except ValueError as e:
            st.warning(str(e))

    revenue = st.text_input("매출 금액 *", placeholder="2,027,990원")

    notion_url = st.text_input(
        "회원 노션 페이지 URL *",
        placeholder="https://www.notion.so/...",
    )

    st.markdown("**카카오톡 내용** *")
    uploaded_file = st.file_uploader(
        ".txt 파일 업로드",
        type=["txt"],
        label_visibility="collapsed",
        help="KakaoTalk에서 대화 내보내기로 받은 .txt 파일을 여기에 드래그하세요",
    )
    kakao_text = ""
    if uploaded_file is not None:
        kakao_text = uploaded_file.read().decode("utf-8", errors="replace")
        st.success(f"파일 로드 완료 ({len(kakao_text):,}자)")

    kakao_input = st.text_area(
        "카카오톡 내용 직접 입력",
        value=kakao_text,
        height=220,
        placeholder="카카오톡 내용을 여기에 붙여넣기 하세요",
        label_visibility="collapsed",
    )
    if kakao_input:
        kakao_text = kakao_input

    can_generate = bool(notion_key and st.session_state.get("claude_auth_ok"))
    generate_btn = st.button(
        "인증글 생성",
        type="primary",
        use_container_width=True,
        disabled=not can_generate,
    )
    if not notion_key:
        st.caption("⚠️ 사이드바에서 Notion 키를 설정하세요.")
    elif not st.session_state.get("claude_auth_ok"):
        st.caption("⚠️ 사이드바에서 Claude Code 인증을 확인하세요.")


with col_output:
    st.subheader("생성된 인증글")
    output_placeholder = st.empty()
    status_placeholder = st.empty()


# ── 생성 실행 ─────────────────────────────────────────────────────────────────

if generate_btn:
    errors = []
    if not period_str.strip():
        errors.append("수익화 기간을 입력하세요.")
    elif cutoff_date is None:
        errors.append("수익화 기간 형식을 확인하세요 (예: 4/13~5/24).")
    if not revenue.strip():
        errors.append("매출 금액을 입력하세요.")
    if not notion_url.strip():
        errors.append("노션 URL을 입력하세요.")
    if not kakao_text.strip():
        errors.append("카카오톡 내용을 입력하거나 파일을 업로드하세요.")

    if errors:
        for err in errors:
            st.warning(err)
    else:
        notion_context = ""
        with status_placeholder.container():
            with st.spinner("노션 페이지 불러오는 중..."):
                try:
                    notion_context = fetch_member_page_content(
                        notion_key, notion_url, cutoff_date
                    )
                    line_count = len([l for l in notion_context.splitlines() if l.strip()])
                    st.success(
                        f"✅ 노션 {line_count}줄 로드 완료 "
                        f"(컷오프: {cutoff_date.month}/{cutoff_date.day})"
                    )
                except PageNotFoundError as e:
                    st.warning(f"⚠️ {e}\n\n카카오톡 내용만으로 진행합니다.")
                except NotionFetchError as e:
                    st.warning(f"⚠️ 노션 로드 실패: {e}\n\n카카오톡 내용만으로 진행합니다.")
                except ValueError as e:
                    st.error(f"❌ {e}")
                    st.stop()

        with output_placeholder.container():
            stream_area = st.empty()
            full_text = ""

            try:
                with st.spinner("인증글 생성 중..."):
                    for chunk in generate_certification_post(
                        member_name=member_name.strip(),
                        period=period_str.strip(),
                        revenue=revenue.strip(),
                        kakao_content=kakao_text.strip(),
                        notion_context=notion_context,
                    ):
                        full_text += chunk
                        stream_area.markdown(full_text + "▌")

                stream_area.markdown(full_text)

            except PermissionError as e:
                st.error(f"🔐 {e}")
                st.session_state["claude_auth_ok"] = False
                st.stop()
            except Exception as e:
                st.error(f"❌ 생성 오류: {e}")
                st.stop()

            if full_text:
                st.session_state["generated_text"] = full_text
                st.session_state["meta"] = {
                    "member_name": member_name.strip(),
                    "period": period_str.strip(),
                    "revenue": revenue.strip(),
                }

# ── 출력 / 저장 ───────────────────────────────────────────────────────────────

if "generated_text" in st.session_state:
    generated = st.session_state["generated_text"]
    meta = st.session_state.get("meta", {})

    with col_output:
        st.divider()
        st.caption("복사용 텍스트 (우측 상단 아이콘으로 복사)")
        st.code(generated, language=None)

        btn_col1, btn_col2 = st.columns(2)
        today_str = date.today().strftime("%Y%m%d")
        name_str = meta.get("member_name") or "미상"
        file_name = f"{today_str}_{name_str}.txt"
        header = (
            f"# BPT 수익화 인증글\n"
            f"생성일: {today_str}\n"
            f"회원: {name_str}\n"
            f"기간: {meta.get('period', '')}\n"
            f"매출: {meta.get('revenue', '')}\n\n---\n\n"
        )

        with btn_col1:
            st.download_button(
                label="💾 다운로드",
                data=(header + generated).encode("utf-8"),
                file_name=file_name,
                mime="text/plain",
                use_container_width=True,
            )

        with btn_col2:
            if st.button("📁 서버 저장", use_container_width=True):
                saved = save_output(
                    generated,
                    meta.get("member_name", ""),
                    meta.get("period", ""),
                    meta.get("revenue", ""),
                )
                st.success(f"저장: {saved.name}")
