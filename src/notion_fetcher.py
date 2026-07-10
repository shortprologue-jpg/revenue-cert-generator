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


def extract_page_id(url: str) -> str:
    match = PAGE_ID_RE.search(url)
    if not match:
        raise ValueError(f"URL에서 page_id를 추출할 수 없습니다: {url}")
    return match.group(1).replace("-", "")


def fetch_all_blocks(client: Client, block_id: str, retries: int = 3) -> list[dict]:
    blocks = []
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


def parse_yymmdd(text: str) -> date | None:
    match = YYMMDD_RE.search(text)
    if not match:
        return None
    yy, mm, dd = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return date(2000 + yy, mm, dd)
    except ValueError:
        return None


def compute_cutoff_date(period_end: date) -> date:
    return period_end - timedelta(days=7)


def filter_blocks_by_cutoff(blocks: list[dict], cutoff: date) -> list[dict]:
    result: list[dict] = []
    current_section_included: bool | None = None

    for block in blocks:
        text = get_block_plain_text(block)
        parsed_date = parse_yymmdd(text)

        if parsed_date is not None:
            current_section_included = parsed_date <= cutoff
            if current_section_included:
                result.append(block)
        else:
            if current_section_included is True:
                result.append(block)
            elif current_section_included is None:
                result.append(block)

    return result


def blocks_to_text(blocks: list[dict]) -> str:
    lines: list[str] = []
    for block in blocks:
        text = get_block_plain_text(block)
        if text:
            lines.append(text)
    return "\n".join(lines)


def fetch_member_page_content(
    notion_api_key: str,
    page_url: str,
    cutoff: date,
) -> str:
    client = Client(auth=notion_api_key)
    page_id = extract_page_id(page_url)
    try:
        blocks = fetch_all_blocks(client, page_id)
    except APIResponseError as e:
        if e.status in (403, 404):
            raise PageNotFoundError(
                f"페이지 접근 실패 (HTTP {e.status}). "
                "노션 통합(integration)이 해당 페이지에 공유되어 있는지 확인하세요."
            ) from e
        raise NotionFetchError(f"노션 API 오류 (HTTP {e.status}): {e.body}") from e
    except Exception as exc:
        raise NotionFetchError(f"노션 API 오류: {exc}") from exc

    filtered = filter_blocks_by_cutoff(blocks, cutoff)
    return blocks_to_text(filtered)
