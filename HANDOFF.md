# HANDOFF — BPT 수익화 인증글 생성기

> 여러 컴퓨터를 오갈 때 이 파일을 읽고 이어서 작업한다.
> **앉으면 pull, 뜨면 push.** (`worksync start` / `worksync end`)

## 현재 상태 (2026-07-21 기준)

**⭐ 웹 배포 완료·라이브** — URL 로 어디서든 접속(아래 '다음 할 일' #0). 이번 세션(2026-07-21)에 한 일:
① **웹배포**(Supabase Postgres 백엔드 + st.secrets + Streamlit Cloud 배포), 보관함 UI 분리(불러온 글을 오른쪽 생성영역 아래 별도 박스), 보안 규칙([[never-expose-secrets]]) 메모리화. **keepalive 만 GitHub 차단으로 대기**(#0).
② **전달(前月) 수익화 데이터 입력 기능** — 카톡칸 밑에 콘관시 표 캡처를 이미지로 첨부(Upload·드래그·**Ctrl+V 붙여넣기**=streamlit-paste-button, 한 카드로 그룹화, 텍스트칸은 제거). `gemini_generator` 가 전달 이미지에 '전달 데이터' 구분 라벨 파트를 붙여 이번 달 이미지와 안 섞이게 전달. 붙여넣기 이미지는 session_state 백업.
③ **생성 품질 대개선**(`prompts/system_prompt.md`) — 아래 '생성 판단 규칙' 참조.

앱 **정상 작동 + E2E 검증 완료.**

### 생성 판단 규칙 (이번 세션 확립 — 프롬프트에 반영됨, 다음 세션의 전제)
- **비포(문제 진단)도 노션의 구체 사례를 살린다**(일반론 금지). 실행뿐 아니라 첫 문단도 구체적으로.
- **달의 성격을 먼저 판단**: 성과 / 준비·빌드업 / 부진. **모든 달을 성공스토리로 쓰지 않는다.**
- **인과 창작 금지(핵심)**: 매출·전환율·신호등을 트레이너가 노션에 안 엮은 인과로 단정하지 않는다. **신호등=과제 수행도(성실도)**, 성과와 상관은 있어도 인과 아님.
- **전달 총매출 합산 → 이번 달(입력값) 비교를 매출 문단에 필수**. 표의 **'주간 목표' 열은 제외**(목표치), 주차 **실적만 합산**. '데이터 입력' 행 상품명(전자책 등)은 상시항목일 수 있어 특수이벤트로 단정 금지.
- **⭐ 매출 하락 시 정비 vs 부진 판단의 1순위 = 콘텐츠 발행 여부**: 콘텐츠 발행(=매출 근본 동력)이 부족/정체면 랜딩·기획을 했어도 **부진**(콘텐츠 안 올리면 매출 만들 방법이 없음). '정비의 달'은 콘텐츠 발행을 유지하며 **추가로** 구조를 다진 경우만.
- 카톡 없으면 인용 생략 가능, 인용 맥락 보존(준비의 보람을 성과 만족으로 둔갑 금지).
- ⚠️ 위 규칙은 배포 반영됨. **실검증(고미선님 등 재생성으로 '부진' 판단·전달 비교 확인)은 다음 세션에 사용자와** — 로컬엔 GEMINI 키 없어 생성 테스트 불가, 배포 앱에서만 확인 가능. 생성 엔진 = **Gemini(google-genai)** + **노션 이미지(콘관시 표) 멀티모달**.
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

0. ~~⭐웹 배포(2단계)~~ ✅ **완료·라이브(2026-07-21)** — Streamlit Cloud + Supabase.
   - **URL**: https://revenue-cert-generator-ehoztwbcdjco68tv2f45ep.streamlit.app/ (비공개 앱 — 본인 GitHub 로그인 시 접속. 회원 데이터라 비공개가 안전.) 저장소는 **public**(Streamlit 무료 앱 무제한).
   - **코드**: `history_store.py` 백엔드 자동전환(SUPABASE 키 있으면 Postgres `posts` upsert, 없으면 로컬 파일 — app.py 무영향, 4함수 인터페이스 유지). `app.py` `st.secrets`→env 브리지 + Path 의존 2줄 견고화. `requirements.txt` supabase(지연 임포트). **Python 3.12**(배포 시 3.14 기본이라 낮춰야 함).
   - **Supabase**: 새 프로젝트 `revenue-cert`(리전 서울), `posts`+`keepalive` 테이블 + RLS anon 정책(`deploy/supabase_setup.sql` SQL Editor 1회 실행). 발라내기 프로젝트와 **분리**(발라내기는 삭제 계획 있어 섞으면 위험). 키 = **anon/publishable**(service_role/secret 아님, RLS 로 제어).
   - **Secrets**: Streamlit Cloud 에 NOTION/GEMINI/SUPABASE_URL/SUPABASE_KEY(TOML). GitHub Secrets(keepalive용)에 SUPABASE_URL/KEY 등록 완료.
   - ⚠️ **keepalive 만 대기 중**: GitHub Actions 가 **"Repository access blocked"** 로 막힘 — 저장소를 오늘 **public 전환 + 신규활동 많아** GitHub 이 이 저장소만 일시 제한(계정·이메일 정상, **발라내기(private)는 세션23부터 keepalive 정상 작동 중** — 앞서 "발라내기가 keepalive 놓쳤다"고 한 건 오조사였음, 정정).
     - workflow(`.github/workflows/supabase-keepalive.yml`: 매일 select + gautamkrishnar/keepalive-workflow 로 60일 자동비활성화 방지)·secret 은 **이미 완비 — 차단만 풀리면 자동 작동.**
     - **대응 순서**: ① 2~3일 후 Actions 탭에서 "Supabase Keep-Alive" 수동 실행 → 초록불이면 끝. ② 안 풀리면 GitHub Support(support.github.com) 문의("Repository access blocked, account verified, restore Actions"). ③ 그래도 안 되면 **cron-job.org(무료)** 로 매일 Supabase 핑: URL=`https://<프로젝트>.supabase.co/rest/v1/keepalive?select=id&limit=1`, 헤더 `apikey`+`Authorization: Bearer`=anon key. Supabase 7일 방치 시 정지라 며칠 여유 있음.
1. **읽기 속도 최적화** — 기록 많은 회원(명지애)은 37초. 토글 자식 조회 병렬화 검토.
2. ~~**`앱실행.bat` 이 노트북 대응**~~ ✅ 완료(2026-07-20) — bat이 `streamlit` 설치된 파이썬을 자동 탐색(`py -3` import 테스트→실패 시 `python` 폴백, 둘 다 없으면 안내 후 종료). 이 노트북에서 `py -3` 선택 + 앱 HTTP 200 구동 검증. 두 노트북 모두 더블클릭 실행 가능.
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
