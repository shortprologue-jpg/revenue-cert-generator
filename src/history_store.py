"""
생성한 인증글 '보관함' 저장소 (로컬 파일 백엔드).

- 저장 = outputs/<회원>__<기간>.txt (회원+기간이 같으면 덮어써서 한 항목으로 유지).
- 헤더에 회원·기간·매출·생성일을 남겨, 목록에서 그대로 파싱해 라벨을 만든다.
- 원자적 쓰기(임시파일 → os.replace)로 저장 중 손상 방지.

⭐ 설계 의도: 나중에 Streamlit Cloud + Supabase 로 옮길 때, app.py 는 그대로 두고
   이 모듈의 함수 4개(list/save/load/delete) 백엔드만 갈아끼우면 되게 UI/저장을 분리한다.
"""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

# 기본 저장 위치 (프로젝트 루트/outputs). OneDrive 동기화 폴더라 두 노트북에서 공유됨.
DEFAULT_DIR = Path(__file__).parent.parent / "outputs"
_HEADER_MARK = "\n\n---\n\n"


def _dir(output_dir: Path | None) -> Path:
    d = output_dir or DEFAULT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(s: str) -> str:
    """파일명에 안전한 조각으로. 한글·영숫자·_ 만 남기고 나머지는 _ 로."""
    s = re.sub(r"[^\w가-힣]", "_", (s or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:40] or "미상"


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
    """회원+기간으로 결정되는 저장 경로(같은 회원·기간이면 항상 같은 파일 → 덮어쓰기)."""
    return _dir(output_dir) / f"{_slug(member)}__{_slug(period)}.txt"


def save_post(
    text: str,
    member: str,
    period: str,
    revenue: str,
    output_dir: Path | None = None,
) -> Path:
    """인증글 저장(회원+기간 동일하면 덮어씀). 반환: 저장 경로."""
    path = post_path(member, period, output_dir)
    created = date.today().strftime("%Y%m%d")
    content = _build_header(member, period, revenue, created) + (text or "")

    # 원자적 쓰기: 임시파일에 쓰고 교체 → 도중 실패해도 원본 안 깨짐.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    return path


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


def _label(meta: dict, path: Path) -> str:
    """드롭다운에 보일 라벨: '회원 · 기간 (MM/DD)'. 메타 없으면 파일명으로."""
    member = meta.get("member_name") or ""
    period = meta.get("period") or ""
    created = meta.get("created") or ""
    when = ""
    if len(created) == 8:  # YYYYMMDD → MM/DD
        when = f" ({created[4:6]}/{created[6:8]})"
    core = " · ".join([x for x in (member, period) if x]) or path.stem
    return f"{core}{when}"


def list_posts(output_dir: Path | None = None) -> list[dict]:
    """저장된 인증글 목록. 최신(수정시각) 순.
    각 항목: {path, label, member_name, period, revenue, created, mtime}."""
    d = _dir(output_dir)
    items = []
    for p in d.glob("*.txt"):
        if p.name.startswith("~") or p.name.endswith(".tmp"):
            continue
        try:
            parsed = _parse(p)
        except Exception:  # noqa: BLE001 — 개별 파일 문제는 목록에서 건너뜀
            continue
        meta = parsed["meta"]
        items.append({
            "path": p,
            "label": _label(meta, p),
            "member_name": meta["member_name"],
            "period": meta["period"],
            "revenue": meta["revenue"],
            "created": meta["created"],
            "mtime": p.stat().st_mtime,
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def load_post(path: Path | str) -> tuple[str, dict]:
    """저장 파일 → (본문, 메타). 메타 키: member_name/period/revenue/created."""
    parsed = _parse(Path(path))
    return parsed["body"], parsed["meta"]


def delete_post(path: Path | str) -> None:
    """저장 파일 삭제(없어도 조용히 통과)."""
    p = Path(path)
    if p.exists():
        p.unlink()
