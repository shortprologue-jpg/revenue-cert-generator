# HANDOFF — BPT 수익화 인증글 생성기

> 여러 컴퓨터를 오갈 때 이 파일을 읽고 이어서 작업한다.
> **앉으면 pull, 뜨면 push.** (`worksync start` / `worksync end`)

## 현재 상태 (2026-07-20 기준)

앱 **정상 작동 + E2E 검증 완료.** 생성 엔진 = **Gemini(google-genai)** + **노션 이미지(콘관시 표) 멀티모달**.
이번 세션에 **① 프롬프트 톤 2건**, **② 회원 전환 시 입력·출력 초기화(+근본버그 수정)**, **③ 생성글 보관함(히스토리)**
을 추가했다. 실제 회원(이도하)으로 노션→이미지→생성까지 돌려 funnel 숫자 반영 확인.

### 이번 세션(2026-07-20 오후)에 한 일
1. **프롬프트 톤 2건** (`prompts/system_prompt.md`):
   - 인용문 뒤 서술어를 자연스러운 높임 반응형으로("…라고 이야기해 주셨습니다/뿌듯해하셨습니다"), 딱딱한 보고체 금지.
   - 마지막 문장 = **트레이너 시점의 방향·계획**("…해 나가려고 합니다"), 회원에 대한 기대("…하기를 기대합니다") 금지.
2. **회원 전환 초기화** (`app.py`): 회원 selectbox `on_change=_reset_member_form` → 기간·매출·카톡·생성글 리셋.
   - form_nonce 접미사로 입력 위젯 key 를 갈아끼워 리셋(빈 위젯).
   - ⚠️ **근본버그 수정**: 예전엔 매 rerun 마다 member_sel 비교였는데, 사이드바/삭제의 `st.rerun` 이 col_input 을
     건너뛰면 member_sel 위젯이 안 그려져 세션에서 사라지고(None) → '바뀐 걸로 오판' → 불러온 글까지 삭제됐다.
     `on_change`(실제 사용자 변경 시에만 호출)로 바꿔 원천 차단.
3. **생성글 보관함(히스토리)** — 신규 `src/history_store.py` + `app.py` 사이드바:
   - 생성하면 **자동 저장**(`outputs/<회원>__<기간>.txt`, 같은 회원·기간이면 덮어씀). 헤더에 회원·기간·매출·생성일.
   - 사이드바 **📚 보관함** = **회원(검색 팝오버) → 그 회원 인증글(목록 팝오버) → 클릭 즉시 오른쪽에 불러오기 / 🗑️ 삭제.**
   - ⚠️ **출력칸 위 팝오버는 결과글을 덮어서** 사이드바로 분리(안 겹침). **selectbox 는 '타이핑=검색'이라 편집되는 듯한
     백스페이스**가 생겨서 → product-classifier 처럼 '팝오버 버튼 + 안 검색창 + 목록 버튼'으로 구현(트리거는 버튼=편집불가).
   - 팝오버 선택 후 닫힘 = 컨테이너 key 에 gen 붙여 선택 시 +1(리마운트). (product-classifier 교훈)
   - `outputs/`(회원 실데이터)는 `.gitignore` 로 커밋 제외 — **두 노트북 동기화는 OneDrive 담당**.
4. **keep-alive 조사**: product-classifier 의 `supabase-keepalive.yml` 은 **Supabase 무료 프로젝트 7일 방치 정지** 방지용.
   현재 우리 앱은 **로컬**이라 불필요. **웹 배포(2단계) 때** 필요(아래 '다음 할 일').

### 실행 방법 (이 노트북)
- 앱 실행: 직접 `C:\Users\xytyp\AppData\Local\Programs\Python\Python312\Scripts\streamlit.exe run app.py --server.port 8502`.
  - ⚠️ 기본 `python`이 hermes venv라 streamlit 없음. `앱실행.bat`의 `python -m streamlit`은 이 노트북에서 실패 가능(다음 할 일).
- 의존성: `streamlit`, `notion-client`(3.x), `python-dotenv`, **`google-genai`** — Python312에 설치 완료.
- `.env` (커밋 안 됨, 노트북마다 필요):
  - `NOTION_API_KEY` (ntn_…)
  - `GEMINI_API_KEY` (AIza…, **유료 키** — 무료 티어는 보낸 데이터를 학습에 쓸 수 있어 유료 사용). AI Studio에서 발급.
  - 앱 사이드바에서 각 키 저장 버튼으로도 `.env`에 기록 가능(다른 키 안 덮어씀).

## 이번 세션에 한 일 (핵심)

1. **노션 읽기 엔진 재작성** (`src/notion_fetcher.py`) — 지난 결함 3건 해결:
   - 토글 안까지 **재귀로 펼쳐** 읽는다 (예전: 최상위 라벨만 → 내용 누락).
   - **읽기 창 = [기간시작+7일] ~ [기간끝+7일]** (아래 '주요 결정' 참고). 창에 드는 주차만 선택.
   - 최상위(주차 heading_2)만 먼저 훑어 날짜 파악 → 선택 주차만 토글 펼침 → 타임아웃 회피.
2. **생성 오류 수정** (`src/claude_generator.py`) — Claude CLI 최신판에서 없어진 `--no-tools` 제거.
3. **회원 드롭다운 = 마스터시트 활동 회원** (`app.py` + `list_active_members`) — 검색 방식 폐기.
4. **회원 → 성장 히스토리 자동 연결** (`find_member_history_page_id`) — 행 안 `callout > child_page`.
5. **사이드바 정리** — 키/인증 접기(둘 다 되면), Claude 로그인 1회 자동 확인, `.env` 저장 버튼.
6. (사용자) **마스터시트 DB 전체를 통합에 공유** → 성장 히스토리 개별 공유 불필요해짐.
7. **UI 개선** (`app.py` + `.streamlit/config.toml`):
   - 수익화 기간 = **달력(`st.date_input` 범위)**. baseweb 달력 로케일이 없어 `localize_datepicker()`가
     JS(`components.html`)로 영어 월→한글 월(6월), 'Choose a date range' quickSelect 숨김, 스크롤 시 정리.
     (product-classifier의 `_localize_datepicker_js` **달력 부분만** 참고, 다른 코드 미반입.)
   - 입력/결과를 카드(`st.columns(border=True)`)로, 결과 전 오른쪽에 **빈 상태 안내 카드**.
   - 결과를 **편집 가능한 text_area**로(위/아래 중복 제거). 헤더 앵커(🔗) 제거(`anchor=False`). 테마 파일 신규(오렌지·둥근 모서리).
8. **생성 엔진 교체: Claude CLI → Gemini** (`src/gemini_generator.py` 신규):
   - 이유: Claude CLI는 호출마다 콜드스타트+MCP 6개 연결로 **~36초 오버헤드**(측정) → 생성 158초.
     Gemini API 직통은 오버헤드 없어 **텍스트 생성 ~15초**. 모델 = **`gemini-3.5-flash`**
     (2.5-pro는 신규 사용자 차단됨, 2.5-flash는 지시 준수·문체가 약함 → 3.5-flash가 클로드 느낌에 가장 근접).
   - `build_user_message`·`system_prompt.md`는 `claude_generator`에서 재사용(모델 무관). 사이드바는 Claude 인증 대신 Gemini 키 상태로.
9. **멀티모달 — 노션 이미지(콘관시 표) 읽기** ⭐:
   - **funnel 숫자(매출·객단가·유료 고객 수·전환율·랜딩 접속·주차별 클릭률)는 노션 텍스트가 아니라 "이미지 캡처"에 있음.**
     콘관시 표(주차별 지표)가 유튜브 스튜디오 분석 캡처들과 함께 이미지로 붙어 있음.
   - `notion_fetcher`가 선택 주차의 **이미지 URL도 수집**(MAX_IMAGES=12) → `gemini_generator`가 httpx로 받아
     `types.Part.from_bytes`로 텍스트와 함께 전송 → Gemini가 표에서 숫자를 읽음. 프롬프트에 "이 표는 실제 데이터, 읽어 써라" 명시.
   - 생성 시간: 이미지 포함 시 ~44초(+노션 읽기 ~20초) = **~64초**. (여전히 Claude 158초보다 빠름)
10. **프롬프트 대개편** (`prompts/system_prompt.md`) — 공식 양식(사용자 제공)을 뼈대로 두고 정교화:
   - 트레이너가 노션에 쓴 것 + 카톡만 사용, **모델의 주관 해석·인과 창작 금지**(매출 인과는 '콘관시 체크'만).
   - 콘관시 체크=매출 인과/숫자, 콘텐츠 피드백=콘텐츠 개선(매출과 분리), 성 제외 강제(도하님), 과한 높임(께) 금지,
     비유·관용구·수사·홍보체·공허한 코칭표현 전면 금지, 매출 첫문장 강제 금지(진입점 변주), 매출 표현 간결화(괄호 매출원).

## 학습한 노션 구조 (중요 — 다음 작업의 전제)

- **마스터시트 DB** = 전체 회원 명단의 단일 출처.
  - DB id `1a31a6604ea0808199e1ef2cb275368e`, 데이터소스 1개(`…80b7…`), **84행**.
  - notion-client **3.x**: `client.data_sources.query(data_source_id=…)` 로 조회(구 `databases.query` 없음).
  - 속성: 회원명(title)·상태(select)·수익화·로열티·주차자동(formula)·첫 트레이닝·유튜브·과제시트 등.
  - `상태` 값: 진행(21)·탈퇴(18)·강의반(16)·졸업(9)·졸업후 진행(7)·이관(5)·OT전탈퇴(4)·유예(3)·OT후3일탈퇴(1).
  - **활동 = 진행 + 졸업후 진행 = 28명** (드롭다운 대상).
- **회원 데이터가 두 군데** 있다:
  - ① 마스터시트 **행** = 프로필 + 과거 수익화 인증 보관(H2 date별 + '인증자료' 토글).
  - ② 행 안 `callout > child_page("○○님 성장 히스토리(공유)")` = **주차별 트레이닝 상세**(원재료).
    - 인증글 생성은 ②를 읽는다. 주차 경계 = heading_2(제목 앞 YYMMDD), 최신이 맨 위, 주차'번호'는 신뢰 불가(날짜로만 판단).
- 검색(`client.search`)은 **색인 지연으로 누락**됨(명지애 등) → 쓰지 않는다. **행에서 직접** 따라간다.

## 다음 할 일 (우선순위)

0. **⭐웹 배포(2단계) — 사용자 목표**: 노트북 2대에서 URL 로 접속(product-classifier 처럼). 큰 별도 작업.
   - **호스팅 = Streamlit Cloud**(무료). ⚠️ **파일시스템이 재시작 때 날아감** → `outputs/` 로컬 저장이 안 남음.
   - **저장소를 Supabase 로 이전**: `history_store.py` 의 함수 4개(list/save/load/delete) 백엔드만 갈아끼우면 됨(그래서 분리 설계함).
   - **keep-alive 필요**: Supabase 무료는 7일 방치 시 정지 → product-classifier 의 `.github/workflows/supabase-keepalive.yml`
     + `_keepalive/setup.sql` 방식(이틀에 한 번 DB ping) 이식. GitHub Secrets 에 SUPABASE_URL/KEY.
   - **키(NOTION/GEMINI)**를 `.env` 대신 **Streamlit Cloud Secrets** 로.
1. **읽기 속도 최적화** — 기록 많은 회원(명지애)은 37초. 토글 자식 조회 병렬화 검토.
2. **`앱실행.bat` 이 노트북 대응** — `python -m streamlit`이 hermes venv라 실패 가능. `py -3` 등으로 견고화 검토.
3. (선택) 생성 진행 표시 개선 — `st.status`+`st.write_stream`으로 노션 로드→생성을 단계형 UX로 묶기(계획만 세워둠, 생성 로직 건드려서 보류).
4. (선택) 생성한 인증글을 마스터시트 행/인증자료에 되기록(back-write) 할지 결정.
5. 활동 28명 중 여러 명으로 추가 E2E — 신규(0~1주차) 회원은 주차 기록이 적어 카톡 위주가 될 수 있음.

## 주요 결정

- **읽기 창 = 수익화기간을 통째로 +1주(LEAD_DAYS=7).** 예: 6/1~6/30 → 노션 6/8~7/7.
  - 이유: **콘텐츠 관리시트 데이터가 뜨는 데 ~1주 걸려**, 코치가 1주 전 데이터를 보고 피드백을 쓴다.
    즉 노션 피드백은 '1주 전' 활동에 대한 것 → 기간 내용을 찾으려면 1주 뒤 기록을 봐야 함.
  - 날짜가 딱 안 맞으므로(회원마다 트레이닝 요일 다름) 창 경계에 여유 ±3일(GRACE_DAYS).
- **회원 명단 = 마스터시트 `상태` 필터** (검색 폐기). 신규/졸업은 노션에서 상태만 바꾸면 자동 반영.
- **회원 이름은 전체(성 포함)로 다룬다** — 특정에 유리. 성 제외는 인증글 작성 시 프롬프트가 처리.
- **생성 엔진 = Gemini `gemini-3.5-flash`** (Claude CLI 폐기 — 오버헤드 36초+). 유료 키 사용(무료 티어는 데이터 학습 이슈).
  - `claude_generator.py`는 `build_user_message`/`SYSTEM_PROMPT_FILE` 재사용 목적으로만 남김(생성엔 안 씀).
- **funnel 지표 숫자는 노션 "이미지"(콘관시 표)에만 있음** → 텍스트만으론 못 읽음 → **멀티모달(이미지 전송)로 해결.**
  - 콘관시 체크/콘텐츠 피드백에 유튜브 분석 캡처 + 콘관시 표가 이미지로 들어감(주차마다 양 다름, 아예 이미지만 있는 주도 있음).
- 저장소 이름 `revenue-cert-generator`, 브랜치 `main` 하나. 비밀키는 커밋 안 함(`.env` 로컬 전용, `NOTION_API_KEY`+`GEMINI_API_KEY`).
- **보관함 = 로컬 파일(`src/history_store.py`)**, 저장은 `outputs/<회원>__<기간>.txt`(회원+기간 같으면 덮어씀).
  - **UI/저장 분리**(product-classifier 원칙): 나중에 Supabase 로 백엔드만 교체하려고 list/save/load/delete 4함수로 캡슐화.
  - `outputs/`는 회원 실데이터 → **커밋 금지(.gitignore)**, 동기화는 OneDrive.
  - UI 는 selectbox 대신 **팝오버(버튼)+검색창+목록** — selectbox 의 타이핑편집(백스페이스) 혼란 회피. 사이드바 배치로 출력칸과 안 겹침.
- **참고 레포 = product-classifier**(비공개, 브랜치 `deploy`) — pull 금지, 구조·규칙만 참고. 회원 팝오버·period 선택기·keepalive 이식 원본.
- `bpt-member-log`와 코드 섞지 않음(구조만 참고).
