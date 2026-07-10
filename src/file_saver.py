import re
from datetime import date
from pathlib import Path


def save_output(
    text: str,
    member_name: str,
    period: str,
    revenue: str,
    output_dir: Path | None = None,
) -> Path:
    out_dir = output_dir or Path(__file__).parent.parent / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    safe_name = re.sub(r"[^\w가-힣]", "_", member_name or "미상")[:20]
    safe_revenue = re.sub(r"[^\d]", "", revenue)[:10]
    base = f"{today}_{safe_name}_{safe_revenue}"

    path = out_dir / f"{base}.txt"
    counter = 1
    while path.exists():
        path = out_dir / f"{base}_{counter}.txt"
        counter += 1

    header = (
        f"# BPT 수익화 인증글\n"
        f"생성일: {today}\n"
        f"회원: {member_name or '미상'}\n"
        f"기간: {period}\n"
        f"매출: {revenue}\n\n"
        f"---\n\n"
    )
    path.write_text(header + text, encoding="utf-8")
    return path
