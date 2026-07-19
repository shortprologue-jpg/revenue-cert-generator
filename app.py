import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import streamlit.components.v1 as components  # 부모 DOM(달력) 조작용 JS 주입

from src.claude_generator import (
    _find_claude_exe,
    check_auth,
    generate_certification_post,
)
from src.file_saver import save_output
from src.notion_fetcher import (
    NotionFetchError,
    PageNotFoundError,
    compute_read_window,
    fetch_member_page_content,
    find_member_history_page_id,
    list_active_members,
)

st.set_page_config(
    page_title="BPT 수익화 인증글 생성기",
    page_icon="🏋️",
    layout="wide",
)

st.title("🏋️ BPT 수익화 인증글 생성기", anchor=False)


@st.cache_data(ttl=600, show_spinner="회원 목록 불러오는 중...")
def load_members(notion_api_key: str) -> list[dict]:
    """마스터시트에서 현재 활동 회원 목록 로드. 10분 캐시."""
    return list_active_members(notion_api_key)


@st.cache_data(ttl=600, show_spinner=False)
def resolve_history_id(notion_api_key: str, row_id: str) -> str | None:
    """회원 행 → 성장 히스토리 page_id (회원별 캐시)."""
    return find_member_history_page_id(notion_api_key, row_id)


def localize_datepicker() -> None:
    """st.date_input 달력 보정 (baseweb 로케일 옵션이 없어 부모 DOM을 직접 손봄):
    (A) 영어 월(June) → 한글 월(6월), (B) 'Choose a date range' 블록 숨김,
    (C) 본문 스크롤 시 달력 정리. (product-classifier의 달력 처리 방식 참고)"""
    components.html(
        """
<script>
(function(){
  var doc = window.parent.document;
  var M = {January:'1월',February:'2월',March:'3월',April:'4월',May:'5월',June:'6월',
           July:'7월',August:'8월',September:'9월',October:'10월',November:'11월',December:'12월'};
  function fixIn(root){
    if(!root) return;
    var tw = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var hits=[], n;
    while(n = tw.nextNode()){ if(M[(n.nodeValue||'').trim()]) hits.push(n); }
    hits.forEach(function(node){
      var k=(node.nodeValue||'').trim(); if(M[k]) node.nodeValue = node.nodeValue.replace(k, M[k]);
    });
  }
  function hideQuickSelect(cal){
    var pop = cal.closest('[data-baseweb="popover"]') || cal.parentElement; if(!pop) return;
    var nodes = pop.querySelectorAll('div,label');
    for(var i=0;i<nodes.length;i++){
      var el = nodes[i];
      if(el.contains(cal)) continue;
      if(/Choose a date range/i.test(el.textContent||'')){
        el.style.setProperty('display','none','important'); break;
      }
    }
  }
  function run(){
    var cal = doc.querySelector('[data-baseweb="calendar"]');
    doc.querySelectorAll('[data-baseweb="calendar"]').forEach(fixIn);
    doc.querySelectorAll('[role="option"]').forEach(function(o){
      if(M[(o.textContent||'').trim()]) fixIn(o);
    });
    if(cal) hideQuickSelect(cal);
  }
  var pending=false;
  function schedule(){ if(pending) return; pending=true;
    window.parent.setTimeout(function(){ pending=false; run(); }, 0);
  }
  if(window.parent.__bptDateLocaleObs) window.parent.__bptDateLocaleObs.disconnect();
  var obs = new MutationObserver(schedule);
  obs.observe(doc.body, {childList:true, subtree:true});
  window.parent.__bptDateLocaleObs = obs;
  run();

  var CLOSE_PX = 36;
  var baseTop = null;
  function closeCal(){
    var a = doc.activeElement;
    doc.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,which:27,bubbles:true}));
    try{ doc.body.dispatchEvent(new MouseEvent('mousedown',{bubbles:true})); }catch(e){}
    if(a && a.blur) a.blur();
  }
  var main = doc.querySelector('[data-testid="stMain"]');
  function onCalScroll(){
    if(!doc.querySelector('[data-baseweb="calendar"]')){ baseTop = null; return; }
    if(baseTop === null) baseTop = main.scrollTop;
    if(Math.abs(main.scrollTop - baseTop) >= CLOSE_PX){ baseTop = null; closeCal(); return; }
    try{ window.parent.dispatchEvent(new Event('scroll')); }catch(e){}
  }
  if(main && !main.__bptCalScroll){
    main.addEventListener('scroll', onCalScroll, {passive:true});
    main.__bptCalScroll = true;
  }
})();
</script>
""",
        height=0,
    )


# ── 사이드바 ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 설정", anchor=False)

    _env_key = os.getenv("NOTION_API_KEY", "")
    _env_key = "" if _env_key == "여기에_키를_붙여넣으세요" else _env_key

    # Claude 인증: 세션 첫 로드 시 1회 자동 확인 (버튼 안 눌러도 상태 파악)
    if "claude_auth_ok" not in st.session_state:
        with st.spinner("Claude 로그인 상태 확인 중..."):
            try:
                _ok, _msg = check_auth()
            except Exception as e:  # noqa: BLE001
                _ok, _msg = False, str(e)
        st.session_state["claude_auth_ok"] = _ok
        st.session_state["claude_auth_msg"] = _msg

    claude_ok = bool(st.session_state.get("claude_auth_ok"))
    both_ok = bool(_env_key) and claude_ok

    # 둘 다 되면 접어둔다 (설정 완료 — 평소엔 안 보임)
    if both_ok:
        st.success("✅ 노션 · Claude 설정 완료")

    with st.expander("🔧 노션 키 · Claude 인증", expanded=not both_ok):
        st.caption("Notion API 키")
        notion_key_input = st.text_input(
            "NOTION_API_KEY", type="password", key="nk",
            placeholder="ntn_... 붙여넣기 (Ctrl+V)", label_visibility="collapsed",
        )
        notion_key = notion_key_input or _env_key
        if notion_key:
            st.success("✅ Notion 키 설정됨")
        else:
            st.warning("⚠️ Notion 키 없음 — 위 칸에 붙여넣고 '💾 저장'")
        if st.button("💾 이 키를 .env에 저장", use_container_width=True,
                     disabled=not notion_key_input.strip()):
            env_path = Path(__file__).parent / ".env"
            env_path.write_text(
                f"NOTION_API_KEY={notion_key_input.strip()}\n", encoding="utf-8"
            )
            st.success("✅ .env에 저장 완료! 다음부터 자동으로 불러옵니다.")

        st.divider()

        st.caption("Claude Code 인증")
        col_auth1, col_auth2 = st.columns([2, 1])
        with col_auth2:
            if st.button("다시 확인", key="check_auth"):
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
                st.info("상태 확인 필요")

        if not st.session_state.get("claude_auth_ok"):
            with st.expander("🔑 초기 로그인 방법"):
                try:
                    exe = _find_claude_exe()
                    st.code(f'& "{exe}" setup-token', language="powershell")
                except FileNotFoundError:
                    st.code("claude setup-token", language="powershell")
                st.caption("PowerShell에서 위 명령 실행 → 브라우저 인증 → 완료 후 '다시 확인'")

    # notion_key를 메인에서 쓰도록 노출 (expander 밖에서도 유효)
    notion_key = (st.session_state.get("nk") or "") or _env_key


# ── 메인: 2단 레이아웃 ────────────────────────────────────────────────────────

col_input, col_output = st.columns([1, 1], gap="large", border=True)

with col_input:
    st.subheader("입력", anchor=False)

    # ── 회원 선택 (노션에서 자동 수집, 이름 드롭다운) ──
    members: list[dict] = []
    members_error = ""
    if notion_key:
        try:
            members = load_members(notion_key)
        except Exception as e:  # noqa: BLE001
            members_error = str(e)

    col_sel, col_refresh = st.columns([5, 1])
    with col_sel:
        member_options = ["— 회원 선택 —"] + [m["name"] for m in members]
        selected_member = st.selectbox(
            "회원 선택 *",
            options=member_options,
        )
    with col_refresh:
        st.write("")
        st.write("")
        if st.button("🔄", help="회원 목록 새로고침"):
            load_members.clear()
            st.rerun()

    name_to_row = {m["name"]: m["row_id"] for m in members}
    name_to_week = {m["name"]: m.get("week") for m in members}
    member_name = "" if selected_member.startswith("—") else selected_member
    member_row_id = name_to_row.get(selected_member, "")

    if members_error:
        st.warning(f"⚠️ 회원 목록 로드 실패: {members_error}")
    elif not notion_key:
        st.caption("먼저 사이드바에서 Notion 키를 설정하세요.")
    elif member_row_id:
        st.caption(f"🏃 현재 {name_to_week.get(selected_member) or '—'}")

    date_range = st.date_input(
        "수익화 기간 *",
        value=(),
        format="YYYY/MM/DD",
    )
    localize_datepicker()
    period_str = ""
    read_window: tuple[date, date] | None = None
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        period_start, period_end = date_range
        period_str = (
            f"{period_start.month}/{period_start.day}"
            f"~{period_end.month}/{period_end.day}"
        )
        read_window = compute_read_window(period_start, period_end)
        rs, re_ = read_window
        st.caption(
            f"노션 읽는 구간: {rs.month}/{rs.day} ~ {re_.month}/{re_.day} "
            f"(기간보다 1주 뒤 — 피드백 지연 반영)"
        )
    elif isinstance(date_range, (tuple, list)) and len(date_range) == 1:
        st.caption("종료일도 선택하세요.")

    revenue = st.text_input("매출 금액 *", placeholder="2,027,990원")

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
    st.subheader("생성된 인증글", anchor=False)
    output_placeholder = st.empty()
    status_placeholder = st.empty()

    # 아직 생성 전이면 허전하지 않게 안내 카드를 보여준다.
    if "generated_text" not in st.session_state:
        with output_placeholder.container(border=True):
            st.markdown(
                "<div style='text-align:center; padding:64px 16px; color:#8a8f98;'>"
                "<div style='font-size:46px; line-height:1;'>✨</div>"
                "<div style='margin-top:14px; font-size:15px; line-height:1.6;'>"
                "왼쪽에서 정보를 입력하고<br><b>‘인증글 생성’</b>을 누르면<br>"
                "여기에 결과가 표시됩니다."
                "</div></div>",
                unsafe_allow_html=True,
            )


# ── 생성 실행 ─────────────────────────────────────────────────────────────────

if generate_btn:
    errors = []
    if read_window is None:
        errors.append("수익화 기간(시작일·종료일)을 달력에서 선택하세요.")
    if not revenue.strip():
        errors.append("매출 금액을 입력하세요.")
    if not member_row_id:
        errors.append("회원을 선택하세요.")
    if not kakao_text.strip():
        errors.append("카카오톡 내용을 입력하거나 파일을 업로드하세요.")

    if errors:
        for err in errors:
            st.warning(err)
    else:
        notion_context = ""
        with status_placeholder.container():
            with st.spinner("노션에서 해당 주차만 펼쳐 읽는 중... (10~40초)"):
                try:
                    rs, re_ = read_window
                    hist_id = resolve_history_id(notion_key, member_row_id)
                    if not hist_id:
                        st.warning(
                            "⚠️ 이 회원의 '성장 히스토리' 페이지를 찾지 못했습니다.\n\n"
                            "카카오톡 내용만으로 진행합니다."
                        )
                    else:
                        notion_context = fetch_member_page_content(
                            notion_key, hist_id, rs, re_
                        )
                        if notion_context.strip():
                            line_count = len(
                                [l for l in notion_context.splitlines() if l.strip()]
                            )
                            st.success(
                                f"✅ 노션 {line_count}줄 로드 완료 "
                                f"(구간: {rs.month}/{rs.day}~{re_.month}/{re_.day})"
                            )
                        else:
                            st.warning(
                                f"⚠️ {rs.month}/{rs.day}~{re_.month}/{re_.day} 구간에 "
                                "해당하는 주차 기록을 못 찾았습니다.\n\n"
                                "카카오톡 내용만으로 진행합니다. (기간을 확인해 보세요)"
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
        tab_view, tab_raw = st.tabs(["📖 미리보기", "📋 복사용 원문"])
        with tab_view:
            st.markdown(generated)
        with tab_raw:
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
