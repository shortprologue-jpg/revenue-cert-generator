"""
노션 회원 '성장 히스토리' 페이지에서 인증글 재료를 읽어온다.

핵심 전략 (실측 기반):
- 페이지 최상위는 flat 구조. 주차 경계 = heading_2, 제목 앞에 YYMMDD 날짜.
  (주차 '번호'는 신뢰 불가 — 날짜로만 판단한다. 최신이 맨 위.)
- 각 주차 밑에 토글들이 형제로 붙어 있고, 토글 안에 또 토글이 있다(다단).
- 실제 내용(과제체크·콘텐츠 피드백·주차별 트레이닝 등)은 전부 토글 '안'에 있다.

그래서 2단계로 읽는다:
  1) 최상위만 훑어(토글 안 펼침 없이) 주차별 날짜를 파악한다. → 빠름.
  2) '읽기 창'에 드는 주차만 골라, 그 주차의 토글만 재귀로 펼쳐 읽는다. → 낭비 없음.

읽기 창 = [기간시작 + LEAD] ~ [기간끝 + LEAD].
  콘텐츠 관리시트 데이터가 뜨는 데 ~1주 걸려, 코치는 1주 전 데이터를 보고
  피드백을 쓴다. 즉 노션의 피드백은 '1주 전' 활동에 대한 것이므로,
  수익화 기간의 내용을 찾으려면 노션에선 1주 뒤 기록을 봐야 한다.
"""
import re
import time
from datetime import date, timedelta

from notion_client import Client
from notion_client.errors import APIResponseError


class NotionFetchError(Exception):
    pass


class PageNotFoundError(NotionFetchError):
    pass


YYMMDD_RE = re.compile(r"\b(\d{2})(\d{2})(\d{2})\b")
PAGE_ID_RE = re.compile(
    r"([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})",
    re.I,
)
# "○○님 성장 히스토리" 제목에서 회원 이름 추출.
MEMBER_TITLE_RE = re.compile(r"^\s*(.+?)님\s*성장\s*히스토리")

# 마스터시트 DB — 전체 회원 명단의 단일 출처.
MASTER_DB_ID = "1a31a6604ea0808199e1ef2cb275368e"
# 드롭다운에 넣을 '현재 활동' 상태값.
ACTIVE_STATUSES = ("진행", "졸업후 진행")

# 콘텐츠 관리시트 지연분 — 노션 기록을 기간보다 이만큼 뒤로 밀어 읽는다.
LEAD_DAYS = 7
# 회원마다 트레이닝 요일이 달라 날짜가 정확히 안 맞으므로, 창 경계에 여유를 둔다.
GRACE_DAYS = 3
# 안전 상한 (선택된 주차만 읽으므로 넉넉하게).
MAX_BLOCKS = 3000
MAX_DEPTH = 5


def extract_page_id(url: str) -> str:
    match = PAGE_ID_RE.search(url)
    if not match:
        raise ValueError(f"URL에서 page_id를 추출할 수 없습니다: {url}")
    return match.group(1).replace("-", "")


def _page_title(page: dict) -> str:
    props = page.get("properties", {})
    for value in props.values():
        if value.get("type") == "title":
            return "".join(
                t.get("plain_text", "") for t in value.get("title", [])
            ).strip()
    return ""


def list_member_pages(notion_api_key: str) -> list[dict]:
    """이 앱 통합에 공유된 '○○님 성장 히스토리' 페이지 목록.

    반환: [{"name": 전체이름, "page_id": 32자, "title": 원제목}], 이름순.
    이름은 전체(성 포함)로 둔다 — 특정에 유리. 성 제외는 인증글 작성 시 프롬프트가 처리.
    """
    client = Client(auth=notion_api_key)
    results: list[dict] = []
    cursor = None
    while True:
        kwargs: dict = {
            "filter": {"property": "object", "value": "page"},
            "page_size": 100,
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        res = client.search(**kwargs)
        results.extend(res["results"])
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    members: list[dict] = []
    seen: set[str] = set()
    for page in results:
        title = _page_title(page)
        m = MEMBER_TITLE_RE.match(title)
        if not m:
            continue
        pid = page["id"].replace("-", "")
        if pid in seen:
            continue
        seen.add(pid)
        members.append({"name": m.group(1).strip(), "page_id": pid, "title": title})

    members.sort(key=lambda x: x["name"])
    return members


def _select_name(page: dict, prop: str) -> str | None:
    v = page.get("properties", {}).get(prop, {})
    t = v.get("type")
    if t == "select" and v.get("select"):
        return v["select"]["name"]
    if t == "status" and v.get("status"):
        return v["status"]["name"]
    return None


def _formula_str(page: dict, prop: str) -> str | None:
    v = page.get("properties", {}).get(prop, {})
    if v.get("type") == "formula":
        f = v.get("formula", {})
        if f.get("string"):
            return f["string"]
        if f.get("number") is not None:
            return str(f["number"])
    return None


def _master_data_source_id(client: Client) -> str:
    """마스터시트 DB의 데이터소스 id (notion-client 3.x: DB→data_sources)."""
    db = client.databases.retrieve(MASTER_DB_ID)
    sources = db.get("data_sources", [])
    if not sources:
        raise NotionFetchError("마스터시트 데이터소스를 찾을 수 없습니다.")
    return sources[0]["id"]


def list_active_members(notion_api_key: str) -> list[dict]:
    """마스터시트에서 '현재 활동'(진행/졸업후 진행) 회원만.

    반환: [{"name": 회원명, "row_id": 32자, "status": 상태, "week": 주차}], 이름순.
    회원명은 전체 그대로(성 포함) — 특정에 유리. 인증글 작성 시 프롬프트가 성 제외 처리.
    """
    client = Client(auth=notion_api_key)
    ds_id = _master_data_source_id(client)
    rows: list[dict] = []
    cursor = None
    while True:
        kwargs: dict = {"data_source_id": ds_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        res = client.data_sources.query(**kwargs)
        rows.extend(res["results"])
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    members: list[dict] = []
    for row in rows:
        status = _select_name(row, "상태")
        if status not in ACTIVE_STATUSES:
            continue
        members.append({
            "name": _page_title(row),
            "row_id": row["id"].replace("-", ""),
            "status": status,
            "week": _formula_str(row, "주차자동"),
        })
    members.sort(key=lambda x: x["name"])
    return members


def find_member_history_page_id(
    notion_api_key: str, row_id: str, max_depth: int = 2
) -> str | None:
    """회원 행 안에서 '성장 히스토리' child_page의 page_id를 찾는다.

    구조: 회원 행 → (callout 등) → child_page("○○님 성장 히스토리(공유)").
    검색(search)은 색인 지연으로 누락되므로, 행을 직접 훑는 이 방식이 확실하다.
    """
    client = Client(auth=notion_api_key)

    def walk(bid: str, depth: int) -> str | None:
        if depth > max_depth:
            return None
        for b in fetch_all_blocks(client, bid):
            if b.get("type") == "child_page":
                title = b["child_page"].get("title", "")
                if "성장" in title and "히스토리" in title:
                    return b["id"].replace("-", "")
                continue  # child_page 내부로는 안 들어감
            if b.get("has_children"):
                found = walk(b["id"], depth + 1)
                if found:
                    return found
        return None

    return walk(row_id, 0)


def fetch_all_blocks(client: Client, block_id: str, retries: int = 3) -> list[dict]:
    """block_id의 '직속 자식'만 전부 가져온다(손자 이하는 안 펼침)."""
    blocks: list[dict] = []
    cursor = None
    while True:
        kwargs: dict = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        for attempt in range(retries):
            try:
                result = client.blocks.children.list(**kwargs)
                break
            except APIResponseError as e:
                if e.status == 429 and attempt < retries - 1:
                    retry_after = int(e.headers.get("Retry-After", "2"))
                    time.sleep(retry_after)
                    continue
                raise
        blocks.extend(result["results"])
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")
    return blocks


def get_block_plain_text(block: dict) -> str:
    block_type = block.get("type", "")
    type_data = block.get(block_type, {})
    if not isinstance(type_data, dict):
        return ""
    rich_text = type_data.get("rich_text", [])
    return "".join(part.get("plain_text", "") for part in rich_text).strip()


def block_line(block: dict) -> str:
    """한 블록을 한 줄 텍스트로. 표/체크박스 등 특수 타입도 처리."""
    btype = block.get("type", "")
    if btype == "table_row":
        cells = block.get("table_row", {}).get("cells", [])
        parts = ["".join(t.get("plain_text", "") for t in cell).strip() for cell in cells]
        parts = [p for p in parts if p]
        return " | ".join(parts)
    text = get_block_plain_text(block)
    if btype == "to_do":
        checked = block.get("to_do", {}).get("checked", False)
        return (("[x] " if checked else "[ ] ") + text).strip()
    return text


def parse_yymmdd(text: str) -> date | None:
    match = YYMMDD_RE.search(text)
    if not match:
        return None
    yy, mm, dd = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return date(2000 + yy, mm, dd)
    except ValueError:
        return None


def compute_read_window(
    period_start: date, period_end: date, lead_days: int = LEAD_DAYS
) -> tuple[date, date]:
    """수익화 기간 → 노션 읽기 창. 기간을 통째로 lead_days만큼 뒤로 민다."""
    return (
        period_start + timedelta(days=lead_days),
        period_end + timedelta(days=lead_days),
    )


def split_week_sections(top_blocks: list[dict]) -> list[dict]:
    """최상위 블록들을 주차 단위로 자른다.

    각 주차 = 날짜 있는 heading_2 하나 + 다음 날짜 heading_2 전까지의 블록들.
    첫 날짜 heading_2 이전(안내문·synced 블록 등)과 날짜 없는 템플릿 heading은 버린다.
    """
    sections: list[dict] = []
    current: dict | None = None
    for block in top_blocks:
        if block.get("type") == "heading_2":
            d = parse_yymmdd(get_block_plain_text(block))
            if d is not None:
                current = {
                    "date": d,
                    "title": get_block_plain_text(block),
                    "body": [],
                }
                sections.append(current)
                continue
        if current is not None:
            current["body"].append(block)
    return sections


def select_sections(
    sections: list[dict],
    read_start: date,
    read_end: date,
    grace_days: int = GRACE_DAYS,
) -> list[dict]:
    """읽기 창(여유 포함)에 드는 주차만 고른다."""
    lo = read_start - timedelta(days=grace_days)
    hi = read_end + timedelta(days=grace_days)
    return [s for s in sections if lo <= s["date"] <= hi]


def _collect_text(
    client: Client,
    blocks: list[dict],
    depth: int,
    counter: dict,
    lines: list[str],
    indent: int = 0,
) -> None:
    """블록들을 재귀로 펼쳐(토글 등) 들여쓰기 텍스트로 모은다. 상한 도달 시 중단."""
    for block in blocks:
        if counter["n"] >= MAX_BLOCKS:
            lines.append("…(이하 생략: 블록 상한 도달)")
            return
        counter["n"] += 1
        text = block_line(block)
        if text:
            lines.append("  " * indent + text)
        if block.get("has_children") and depth < MAX_DEPTH:
            kids = fetch_all_blocks(client, block["id"])
            _collect_text(client, kids, depth + 1, counter, lines, indent + 1)


def render_sections(client: Client, selected: list[dict]) -> str:
    """선택된 주차들을 토글까지 펼쳐 하나의 텍스트로."""
    counter = {"n": 0}
    out: list[str] = []
    for section in selected:
        out.append(f"### {section['title']}")
        lines: list[str] = []
        _collect_text(client, section["body"], 0, counter, lines, 0)
        out.append("\n".join(lines))
        out.append("")
    return "\n".join(out).strip()


def fetch_member_page_content(
    notion_api_key: str,
    page_url: str,
    read_start: date,
    read_end: date,
) -> str:
    """회원 페이지에서 읽기 창에 드는 주차의 내용을 토글까지 펼쳐 반환.

    창에 드는 주차가 없으면 빈 문자열(호출부가 '노션 없음'으로 처리).
    """
    client = Client(auth=notion_api_key)
    page_id = extract_page_id(page_url)
    try:
        top = fetch_all_blocks(client, page_id)
    except APIResponseError as e:
        if e.status in (403, 404):
            raise PageNotFoundError(
                f"페이지 접근 실패 (HTTP {e.status}). "
                "노션 통합(integration)이 해당 페이지에 공유되어 있는지 확인하세요."
            ) from e
        raise NotionFetchError(f"노션 API 오류 (HTTP {e.status}): {e.body}") from e
    except Exception as exc:
        raise NotionFetchError(f"노션 API 오류: {exc}") from exc

    sections = split_week_sections(top)
    selected = select_sections(sections, read_start, read_end)
    if not selected:
        return ""
    return render_sections(client, selected)
