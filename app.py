import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# override=True: 앱 실행 중 .env를 고쳐도 새로고침하면 반영되게.
load_dotenv(override=True)

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import streamlit.components.v1 as components  # 부모 DOM(달력) 조작용 JS 주입

# 배포(Streamlit Cloud)엔 .env 가 없다 → st.secrets 의 키를 환경변수로 브리지한다.
# '없을 때만' 채우므로 로컬(.env override) 동작은 그대로. 생성기·노션·보관함이 os.environ 에서 읽음.
for _k in ("NOTION_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
           "SUPABASE_URL", "SUPABASE_KEY"):
    if not os.environ.get(_k):
        try:
            _v = st.secrets.get(_k)
        except Exception:  # noqa: BLE001 — secrets.toml 미존재 시 예외 → 로컬로 폴백
            _v = None
        if _v:
            os.environ[_k] = str(_v)

from src.gemini_generator import generate_certification_post
from src.history_store import delete_post, list_posts, load_post, save_post
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


def save_env_var(name: str, value: str) -> None:
    """`.env`에서 name 키만 갱신(없으면 추가). 다른 키는 보존한다."""
    env_path = Path(__file__).parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    out, found = [], False
    for ln in lines:
        if ln.strip().startswith(f"{name}="):
            out.append(f"{name}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{name}={value}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[name] = value


def _reset_member_form() -> None:
    """회원 selectbox 변경 시에만 호출(on_change): 입력 위젯 key 를 갈아끼울
    form_nonce +1 + 출력물(생성글·메타·보관함선택) 비움. 실제 사용자 변경에서만
    돌아서, 사이드바/삭제의 st.rerun 이 유발하던 오발동 리셋을 없앤다."""
    st.session_state["form_nonce"] = st.session_state.get("form_nonce", 0) + 1
    for k in ("generated_text", "meta", "edit_area", "hist_loaded"):
        st.session_state.pop(k, None)


# ── 보관함(생성글 히스토리) ────────────────────────────────────────────────────
# 회원별 → 인증글 2단계로 '사이드바'에 배치 → 출력 영역과 물리적으로 분리(안 겹침).
# 저장은 history_store(로컬 파일). 나중에 Supabase 로 백엔드만 교체 가능.


@st.dialog("보관함에서 삭제")
def _confirm_delete_post(path_str: str) -> None:
    st.write("이 인증글을 보관함에서 삭제할까요?")
    st.caption(Path(path_str).name)
    c1, c2 = st.columns(2)
    if c1.button("취소", use_container_width=True):
        st.rerun()
    if c2.button("삭제", type="primary", use_container_width=True):
        delete_post(path_str)
        # 지금 화면에 띄워둔 글을 지웠으면 결과칸도 비운다.
        if st.session_state.get("hist_loaded") == path_str:
            for k in ("generated_text", "meta", "edit_area", "hist_loaded"):
                st.session_state.pop(k, None)
        st.rerun()


def _post_label(p: dict) -> str:
    """보관함 인증글 라벨: '기간 (MM/DD)'. 기간 없으면 파일명."""
    core = p["period"] or Path(str(p["path"])).stem
    created = p.get("created") or ""
    when = f" ({created[4:6]}/{created[6:8]})" if len(created) == 8 else ""
    return f"{core}{when}"


_HIST_CSS = """
<style>
/* 보관함 목록 버튼: 왼쪽 정렬 + 길면 말줄임(…) */
[class*="st-key-histmem_"] button, [class*="st-key-histpost_"] button {
    justify-content: flex-start !important;
}
[class*="st-key-histmem_"] button p, [class*="st-key-histpost_"] button p {
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    text-align: left; width: 100%;
}
/* 🗑️ = 박스 없는 회색 이모지 */
[class*="st-key-histdel_"] button {
    background: transparent !important; border: none !important;
    box-shadow: none !important; filter: grayscale(1); opacity: .5;
}
[class*="st-key-histdel_"] button:hover { opacity: .95; }
</style>
"""


def _render_history_sidebar() -> None:
    """사이드바 보관함 — 회원(검색 팝오버) → 그 회원의 인증글(목록 팝오버) → 클릭 즉시 불러오기.

    selectbox 는 '타이핑=검색'이라 값이 편집되는 듯한 백스페이스가 생긴다 →
    product-classifier 처럼 '팝오버 트리거(버튼) + 안에 검색창 + 목록 버튼' 으로 구현.
    트리거는 버튼이라 편집 불가, 검색은 팝오버 안 전용 검색창이 담당. 사이드바라 안 겹침.
    팝오버가 선택 후 안 닫히는 함정 → 컨테이너 key 에 gen 을 붙여 선택 시 +1(리마운트=닫힘).
    """
    st.markdown(_HIST_CSS, unsafe_allow_html=True)
    st.header("📚 보관함", anchor=False)
    posts = list_posts()  # 최신순
    if not posts:
        st.caption("아직 저장된 인증글이 없어요.\n생성하면 자동으로 여기에 쌓입니다.")
        return

    # 회원별 그룹(최신순 유지)
    by_member: dict[str, list] = {}
    for p in posts:
        by_member.setdefault(p["member_name"] or "미상", []).append(p)
    members = list(by_member.keys())

    # ── 회원 선택 팝오버 (검색창 + 버튼 목록) ──
    mgen = st.session_state.get("hist_mem_gen", 0)
    cur_member = st.session_state.get("hist_member")
    if cur_member not in members:  # 저장된 값이 사라졌으면 미선택으로
        cur_member = None
    trig = f"👤 {cur_member}" if cur_member else "👤 회원 선택"
    with st.container(key=f"histmemhold_{mgen}"):
        with st.popover(trig, use_container_width=True):
            q = st.text_input(
                "회원 검색", placeholder="이름으로 찾기",
                key=f"hist_mem_q_{mgen}", label_visibility="collapsed",
            )
            ql = (q or "").strip().lower()
            shown_m = [m for m in members if ql in m.lower()] if ql else members
            with st.container(height=min(max(len(shown_m), 1), 6) * 44 + 8, border=False):
                if not shown_m:
                    st.caption("검색 결과가 없어요.")
                for i, m in enumerate(members):
                    if m not in shown_m:
                        continue
                    is_cur = (m == cur_member)
                    if st.button(
                        f"{m}  ·  {len(by_member[m])}건", key=f"histmem_{i}",
                        use_container_width=True,
                        type="primary" if is_cur else "secondary",
                    ):
                        st.session_state["hist_member"] = m
                        st.session_state["hist_mem_gen"] = mgen + 1  # 리마운트=닫힘+검색초기화
                        st.rerun()

    if not cur_member:
        st.caption(f"저장된 회원 {len(members)}명. 회원을 고르세요.")
        return

    # ── 그 회원의 인증글 선택 팝오버 (줄마다 [선택][🗑️]) ──
    mposts = by_member[cur_member]
    pgen = st.session_state.get("hist_post_gen", 0)
    cur_post = st.session_state.get("hist_loaded")
    cur_label = next((_post_label(p) for p in mposts if str(p["path"]) == cur_post), None)
    ptrig = f"🗓️ {cur_label}" if cur_label else "🗓️ 인증글 선택"
    mi = members.index(cur_member)
    with st.container(key=f"histposthold_{mi}_{pgen}"):
        with st.popover(ptrig, use_container_width=True):
            with st.container(height=min(max(len(mposts), 1), 6) * 46 + 8, border=False):
                for i, p in enumerate(mposts):
                    pth = str(p["path"])
                    is_cur = (pth == cur_post)
                    c_name, c_del = st.columns(
                        [5, 1], gap="small", vertical_alignment="center"
                    )
                    with c_name:
                        if st.button(
                            _post_label(p), key=f"histpost_{i}",
                            use_container_width=True,
                            type="primary" if is_cur else "secondary",
                        ):
                            body, meta = load_post(p["path"])
                            st.session_state["generated_text"] = body
                            st.session_state["meta"] = meta
                            st.session_state["edit_area"] = body
                            st.session_state["hist_loaded"] = pth
                            st.session_state["hist_post_gen"] = pgen + 1  # 리마운트=닫힘
                            st.rerun()
                    with c_del:
                        if st.button("🗑️", key=f"histdel_{i}",
                                     use_container_width=True):
                            _confirm_delete_post(pth)
    if cur_label:
        st.caption("✅ 지금 오른쪽에 열려 있는 글")


# ── 사이드바 ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 설정", anchor=False)

    _PLACEHOLDERS = ("여기에_키를_붙여넣으세요", "여기에_제미나이_키_붙여넣기")

    def _env_val(name: str) -> str:
        v = os.getenv(name, "")
        return "" if v in _PLACEHOLDERS else v

    notion_env = _env_val("NOTION_API_KEY")
    gemini_env = _env_val("GEMINI_API_KEY") or _env_val("GOOGLE_API_KEY")

    # 필드 입력 시 즉시 사용 가능하게 os.environ에도 반영 (생성기가 여기서 읽음).
    _gk_typed = (st.session_state.get("gk") or "").strip()
    if _gk_typed:
        os.environ["GEMINI_API_KEY"] = _gk_typed

    notion_key = (st.session_state.get("nk") or "") or notion_env
    gemini_ok = bool(_gk_typed or gemini_env)
    both_ok = bool(notion_key) and gemini_ok

    if both_ok:
        st.success("✅ 노션 · Gemini 설정 완료")

    with st.expander("🔧 노션 키 · Gemini 키", expanded=not both_ok):
        st.caption("Notion API 키")
        notion_key_input = st.text_input(
            "NOTION_API_KEY", type="password", key="nk",
            placeholder="ntn_...", label_visibility="collapsed",
        )
        if notion_key_input or notion_env:
            st.success("✅ Notion 키 설정됨")
        else:
            st.warning("⚠️ Notion 키 없음")
        if st.button("💾 Notion 키 저장", use_container_width=True,
                     disabled=not notion_key_input.strip()):
            save_env_var("NOTION_API_KEY", notion_key_input.strip())
            st.success("✅ 저장 완료!")

        st.divider()

        st.caption("Gemini API 키 (무료 — aistudio.google.com/apikey)")
        gemini_key_input = st.text_input(
            "GEMINI_API_KEY", type="password", key="gk",
            placeholder="AIza...", label_visibility="collapsed",
        )
        if gemini_key_input or gemini_env:
            st.success("✅ Gemini 키 설정됨")
        else:
            st.warning("⚠️ Gemini 키 없음 — 위 칸에 붙여넣고 저장")
        if st.button("💾 Gemini 키 저장", use_container_width=True,
                     disabled=not gemini_key_input.strip()):
            save_env_var("GEMINI_API_KEY", gemini_key_input.strip())
            os.environ["GEMINI_API_KEY"] = gemini_key_input.strip()
            st.success("✅ 저장 완료!")

    st.divider()
    _render_history_sidebar()


# ── 메인: 2단 레이아웃 ────────────────────────────────────────────────────────

col_input, col_output = st.columns([1, 1], gap="large", border=True)

with col_input:
    st.subheader("입력", anchor=False)

    # ── 회원이 바뀌면 입력·출력을 초기화 (아래 회원 selectbox on_change 에서 처리) ──
    # 예전엔 매 rerun 마다 member_sel 을 비교했는데, 사이드바/삭제의 st.rerun 이
    # col_input 을 건너뛰면 member_sel 위젯이 안 그려져 세션에서 사라지고(None) →
    # 다음 rerun 에서 '바뀐 걸로' 오판해 방금 불러온 글까지 지웠다.
    # on_change(_reset_member_form)는 '실제 사용자 변경'에서만 돌아 그 오판이 없다.
    # form_nonce = 입력 위젯 key 접미사(바뀌면 빈 위젯으로 리마운트).
    nonce = st.session_state.setdefault("form_nonce", 0)

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
            key="member_sel",
            on_change=_reset_member_form,
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
        key=f"date_{nonce}",  # 회원 바뀌면 새 key → 기간도 초기화(회원마다 기간 다름)
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

    revenue = st.text_input(
        "매출 금액 *", placeholder="2,027,990원", key=f"revenue_{nonce}"
    )

    st.markdown("**카카오톡 내용** *")
    uploaded_file = st.file_uploader(
        ".txt 파일 업로드",
        type=["txt"],
        label_visibility="collapsed",
        help="KakaoTalk에서 대화 내보내기로 받은 .txt 파일을 여기에 드래그하세요",
        key=f"kakao_file_{nonce}",  # 회원 바뀌면 새 key → 업로드 파일도 초기화
    )
    kakao_key = f"kakao_{nonce}"
    if uploaded_file is not None:
        file_text = uploaded_file.read().decode("utf-8", errors="replace")
        st.success(f"파일 로드 완료 ({len(file_text):,}자)")
        # 업로드 내용으로 입력칸 채우기(아직 비어 있을 때만 — 위젯 생성 전 주입).
        if not st.session_state.get(kakao_key):
            st.session_state[kakao_key] = file_text

    kakao_text = st.text_area(
        "카카오톡 내용 직접 입력",
        height=220,
        placeholder="카카오톡 내용을 여기에 붙여넣기 하세요",
        label_visibility="collapsed",
        key=kakao_key,  # 회원 바뀌면 새 key → 이전 카톡 내용 초기화
    )

    can_generate = bool(notion_key and gemini_ok)
    generate_btn = st.button(
        "인증글 생성",
        type="primary",
        use_container_width=True,
        disabled=not can_generate,
    )
    if not notion_key:
        st.caption("⚠️ 사이드바에서 Notion 키를 설정하세요.")
    elif not gemini_ok:
        st.caption("⚠️ 사이드바에서 Gemini 키를 설정하세요.")


with col_output:
    st.subheader("생성된 인증글", anchor=False)
    # 현재 화면에 뜬 글이 누구·언제 것인지 표시(보관함에서 불러왔거나 방금 생성).
    _cur_meta = st.session_state.get("meta")
    if _cur_meta and _cur_meta.get("member_name"):
        st.caption(f"📄 {_cur_meta.get('member_name','')} · {_cur_meta.get('period','')}")
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
        notion_images: list[str] = []
        with status_placeholder.container():
            with st.spinner("노션에서 해당 주차만 펼쳐 읽는 중 (이미지 포함)... (20~60초)"):
                try:
                    rs, re_ = read_window
                    hist_id = resolve_history_id(notion_key, member_row_id)
                    if not hist_id:
                        st.warning(
                            "⚠️ 이 회원의 '성장 히스토리' 페이지를 찾지 못했습니다.\n\n"
                            "카카오톡 내용만으로 진행합니다."
                        )
                    else:
                        notion_context, notion_images = fetch_member_page_content(
                            notion_key, hist_id, rs, re_
                        )
                        if notion_context.strip():
                            line_count = len(
                                [l for l in notion_context.splitlines() if l.strip()]
                            )
                            img_note = (
                                f" · 이미지 {len(notion_images)}장 포함"
                                if notion_images else ""
                            )
                            st.success(
                                f"✅ 노션 {line_count}줄 로드 완료{img_note} "
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
                        notion_images=notion_images,
                    ):
                        full_text += chunk
                        stream_area.markdown(full_text + "▌")

                stream_area.markdown(full_text)

            except PermissionError as e:
                st.error(f"🔐 {e}")
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
                st.session_state["edit_area"] = full_text
                # 자동 저장 — 생성하면 보관함에 바로 쌓인다(같은 회원·기간이면 덮어씀).
                try:
                    _saved = save_post(
                        full_text, member_name.strip(),
                        period_str.strip(), revenue.strip(),
                    )
                    st.session_state["hist_loaded"] = str(_saved)
                except Exception as _e:  # noqa: BLE001 — 저장 실패해도 생성 결과는 보존
                    st.warning(f"⚠️ 보관함 자동 저장 실패(글은 화면에 있음): {_e}")

        # 스트리밍으로 그린 잔상을 지워, 아래 '수정 가능' 편집칸 하나만 남긴다.
        output_placeholder.empty()

# ── 출력 / 저장 ───────────────────────────────────────────────────────────────

if "generated_text" in st.session_state:
    meta = st.session_state.get("meta", {})
    if "edit_area" not in st.session_state:
        st.session_state["edit_area"] = st.session_state["generated_text"]

    with col_output:
        # 하나의 편집 가능한 영역. 여기서 바로 고치면 다운로드·저장에 그대로 반영됨.
        edited = st.text_area(
            "생성된 인증글 — 여기서 바로 수정할 수 있어요",
            height=460,
            key="edit_area",
        )

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
                data=(header + edited).encode("utf-8"),
                file_name=file_name,
                mime="text/plain",
                use_container_width=True,
            )

        with btn_col2:
            # 자동 저장은 '생성 원문' 기준. 여기서 수정한 내용을 보관함에 덮어써 반영.
            if st.button("📁 수정본 저장", use_container_width=True,
                         help="위에서 고친 내용을 보관함에 덮어씁니다(자동저장 갱신)"):
                saved = save_post(
                    edited,
                    meta.get("member_name", ""),
                    meta.get("period", ""),
                    meta.get("revenue", ""),
                )
                st.session_state["hist_loaded"] = str(saved)
                st.success("저장됨 ✅")
