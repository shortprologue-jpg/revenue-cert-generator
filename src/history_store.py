"""
생성한 인증글 '보관함' 저장소 — 백엔드 2종을 같은 4함수 뒤에 숨긴다.

  - 로컬 파일(outputs/<회원>__<기간>.txt) : 기본. 이 노트북·로컬 실행용.
  - Supabase(Postgres `posts` 테이블)      : SUPABASE_URL/KEY 가 (환경변수 또는
    st.secrets 에) 있으면 자동 사용. 웹 배포(Streamlit Cloud)에서 재시작해도
    데이터가 안 날아가게 외부 창고에 둔다.

app.py 는 어느 백엔드인지 모른 채 list_posts/save_post/load_post/delete_post 만 부른다.
'식별자(path)'의 의미만 백엔드마다 다르다: 로컬=파일 경로(Path), Supabase=행 id(str).
회원+기간이 같으면 덮어쓰기 — 로컬은 같은 파일명, Supabase 는 upsert(on_conflict).
"""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

# 로컬 기본 저장 위치(프로젝트 루트/outputs). OneDrive 동기화 폴더라 두 노트북 공유.
DEFAULT_DIR = Path(__file__).parent.parent / "outputs"
_HEADER_MARK = "\n\n---\n\n"
_TABLE = "posts"


# =====================================================================
# 백엔드 선택 — SUPABASE_URL/KEY 가 환경변수 또는 st.secrets 에 있으면 Supabase.
# =====================================================================
def _secret(name: str, default: str = "") -> str:
    """환경변수 우선, 없으면 Streamlit secrets. 둘 다 없으면 default."""
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st  # 로컬 스크립트/테스트엔 streamlit 이 없을 수 있음
        return str(st.secrets.get(name, default) or default)
    except Exception:  # noqa: BLE001 — secrets 미설정/미임포트 = 로컬로 폴백
        return default


def _use_supabase() -> bool:
    return bool(_secret("SUPABASE_URL") and _secret("SUPABASE_KEY"))


_client = None


def _sb():
    """Supabase 클라이언트(지연 생성·모듈 1회 재사용). supabase 미설치면 여기서만 에러."""
    global _client
    if _client is None:
        from supabase import create_client
        _client = create_client(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))
    return _client


# =====================================================================
# 공통 헬퍼
# =====================================================================
def _slug(s: str) -> str:
    """파일명에 안전한 조각으로. 한글·영숫자·_ 만 남기고 나머지는 _ 로."""
    s = re.sub(r"[^\w가-힣]", "_", (s or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:40] or "미상"


def _label(member: str, period: str, created: str, fallback: str = "") -> str:
    """목록 라벨: '회원 · 기간 (MM/DD)'. 회원·기간 없으면 fallback."""
    when = ""
    if len(created or "") == 8:  # YYYYMMDD → MM/DD
        when = f" ({created[4:6]}/{created[6:8]})"
    core = " · ".join([x for x in (member, period) if x]) or fallback
    return f"{core}{when}"


def _item(member, period, revenue, created, path, mtime, fallback="") -> dict:
    """app.py 가 기대하는 목록 항목 형태(백엔드 공통)."""
    return {
        "path": path,
        "label": _label(member, period, created, fallback or str(path)),
        "member_name": member or "",
        "period": period or "",
        "revenue": revenue or "",
        "created": created or "",
        "mtime": mtime,
    }


# =====================================================================
# 로컬 파일 백엔드
# =====================================================================
def _dir(output_dir: Path | None = None) -> Path:
    d = output_dir or DEFAULT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _build_header(member: str, period: str, revenue: str, created: str) -> str:
    return (
        f"# BPT 수익화 인증글\n"
        f"생성일: {created}\n"
        f"회원: {member or '미상'}\n"
        f"기간: {period or ''}\n"
        f"매출: {revenue or ''}"
        f"{_HEADER_MARK}"
    )


def post_path(member: str, period: str, output_dir: Path | None = None) -> Path:
    """회원+기간으로 결정되는 저장 경로(같으면 항상 같은 파일 → 덮어쓰기)."""
    return _dir(output_dir) / f"{_slug(member)}__{_slug(period)}.txt"


def _parse(path: Path) -> dict:
    """저장 파일 → 메타 + 본문. 헤더가 없거나 옛 형식이어도 최대한 읽어낸다."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta = {"member_name": "", "period": "", "revenue": "", "created": ""}
    body = raw
    if _HEADER_MARK in raw:
        head, body = raw.split(_HEADER_MARK, 1)
        for line in head.splitlines():
            if line.startswith("회원:"):
                meta["member_name"] = line[3:].strip()
            elif line.startswith("기간:"):
                meta["period"] = line[3:].strip()
            elif line.startswith("매출:"):
                meta["revenue"] = line[3:].strip()
            elif line.startswith("생성일:"):
                meta["created"] = line[4:].strip()
    return {"meta": meta, "body": body}


def _local_list(output_dir: Path | None = None) -> list[dict]:
    d = _dir(output_dir)
    items = []
    for p in d.glob("*.txt"):
        if p.name.startswith("~") or p.name.endswith(".tmp"):
            continue
        try:
            parsed = _parse(p)
        except Exception:  # noqa: BLE001 — 개별 파일 문제는 목록에서 건너뜀
            continue
        m = parsed["meta"]
        items.append(_item(
            m["member_name"], m["period"], m["revenue"], m["created"],
            p, p.stat().st_mtime, fallback=p.stem,
        ))
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def _local_save(text, member, period, revenue, output_dir=None) -> Path:
    path = post_path(member, period, output_dir)
    created = date.today().strftime("%Y%m%d")
    content = _build_header(member, period, revenue, created) + (text or "")
    # 원자적 쓰기: 임시파일에 쓰고 교체 → 도중 실패해도 원본 안 깨짐.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    return path


def _local_load(path) -> tuple[str, dict]:
    parsed = _parse(Path(path))
    return parsed["body"], parsed["meta"]


def _local_delete(path) -> None:
    p = Path(path)
    if p.exists():
        p.unlink()


# =====================================================================
# Supabase(Postgres) 백엔드
#   테이블 posts(id, member, period, revenue, created, body) + UNIQUE(member, period).
#   created 는 YYYYMMDD 문자열(로컬과 동일) — 사전식 정렬이 곧 시간순이라 order 로 충분.
# =====================================================================
def _sb_list() -> list[dict]:
    rows = (
        _sb().table(_TABLE).select("*")
        .order("created", desc=True).order("id", desc=True)
        .execute().data
    ) or []
    return [
        _item(
            r.get("member", ""), r.get("period", ""), r.get("revenue", ""),
            r.get("created", ""), str(r.get("id")), r.get("created", ""),
            fallback=r.get("member", ""),
        )
        for r in rows
    ]


def _sb_save(text, member, period, revenue) -> str:
    created = date.today().strftime("%Y%m%d")
    res = _sb().table(_TABLE).upsert(
        {
            "member": member or "미상", "period": period or "",
            "revenue": revenue or "", "created": created, "body": text or "",
        },
        on_conflict="member,period",  # 회원+기간 같으면 덮어쓰기(로컬 파일명 규칙과 동일)
    ).execute()
    data = res.data or []
    return str(data[0]["id"]) if data else f"{member}__{period}"


def _sb_load(path) -> tuple[str, dict]:
    rows = _sb().table(_TABLE).select("*").eq("id", int(path)).execute().data or []
    if not rows:
        return "", {"member_name": "", "period": "", "revenue": "", "created": ""}
    r = rows[0]
    meta = {
        "member_name": r.get("member", ""), "period": r.get("period", ""),
        "revenue": r.get("revenue", ""), "created": r.get("created", ""),
    }
    return r.get("body", ""), meta


def _sb_delete(path) -> None:
    _sb().table(_TABLE).delete().eq("id", int(path)).execute()


# =====================================================================
# 공개 API — app.py 가 부르는 4함수 (+ post_path). 백엔드는 여기서 고른다.
# =====================================================================
def list_posts(output_dir: Path | None = None) -> list[dict]:
    """저장된 인증글 목록(최신순). 각 항목: path/label/member_name/period/revenue/created/mtime."""
    return _sb_list() if _use_supabase() else _local_list(output_dir)


def save_post(text, member, period, revenue, output_dir=None):
    """인증글 저장(회원+기간 같으면 덮어씀). 반환: 식별자(로컬=Path, Supabase=id 문자열)."""
    if _use_supabase():
        return _sb_save(text, member, period, revenue)
    return _local_save(text, member, period, revenue, output_dir)


def load_post(path) -> tuple[str, dict]:
    """식별자 → (본문, 메타). 메타 키: member_name/period/revenue/created."""
    return _sb_load(path) if _use_supabase() else _local_load(path)


def delete_post(path) -> None:
    """식별자로 삭제(없어도 조용히 통과)."""
    return _sb_delete(path) if _use_supabase() else _local_delete(path)
