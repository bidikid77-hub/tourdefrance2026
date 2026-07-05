#!/usr/bin/env python3
"""Fetch Tour de France stage results and jersey leaders from letour.fr rankings pages.

Updates tour-de-france-2026.json with:
- stage_winner
- yellow_jersey / gc_leader
- green_jersey
- polka_dot_jersey
- white_jersey
- team_classification_leader

Prints nothing when no update.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import urllib.request
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
JSON_PATH = BASE / "tour-de-france-2026.json"
GEN_PATH = BASE / "generate_ics.py"

UA = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}
RANKING_BASE = "https://www.letour.fr/en/rankings/stage-{stage}"
START_DATE = date(2026, 7, 4)
END_DATE = date(2026, 7, 26)
VN_TZ = timezone(timedelta(hours=7))

RANKING_FIELDS = {
    "ete": "stage_winner",
    "itg": "yellow_jersey",
    "ipg": "green_jersey",
    "img": "polka_dot_jersey",
    "ijg": "white_jersey",
    "etg": "team_classification_leader",
}
VALUE_FIELDS = {
    "ete": "stage_winner_time",
    "itg": "yellow_jersey_total_time",
    "ipg": "green_jersey_points",
    "img": "polka_dot_jersey_points",
    "ijg": "white_jersey_total_time",
    "etg": "team_classification_total_time",
}
EMOJI_FIELDS = {
    "stage_winner": "🏁",
    "yellow_jersey": "🟨",
    "green_jersey": "🟩",
    "polka_dot_jersey": "🔴⚪",
    "white_jersey": "⬜",
    "team_classification_leader": "👥",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def stage_number(row: dict) -> int | None:
    try:
        return int(str(row.get("stage", "")).strip())
    except Exception:
        return None


def stage_date_iso(row: dict) -> str | None:
    v = row.get("date_iso")
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    return None


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " | ", value)
    value = html_lib.unescape(value)
    return re.sub(r"\s+", " ", value).strip(" |\t\r\n")


def first_result(html: str, typ: str) -> tuple[str | None, str | None]:
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        block = m.group(1)
        if "rankingTables__row__profile--name" not in block and "break-line team" not in block:
            continue
        name_m = re.search(r'rankingTables__row__profile--name"[^>]*>\s*([^<]+)', block)
        if name_m:
            name = re.sub(r"\s+", " ", html_lib.unescape(name_m.group(1))).strip()
        else:
            team_m = re.search(r'<td class="break-line team"[^>]*>(.*?)</td>', block, re.S)
            name = clean_text(team_m.group(1)).replace(" | ", " ") if team_m else ""
        cells = re.findall(r"<td[^>]*>(.*?)</td>", block, re.S)
        texts = [clean_text(c) for c in cells]
        value = ""
        if typ in {"ete", "itg", "ijg", "etg"}:
            value = next((t for t in texts if re.search(r"\d{2}h\s*\d{2}'\s*\d{2}''", t)), "")
        elif typ in {"ipg", "img"}:
            value = next((t for t in texts if re.search(r"\d+\s*PT", t, re.I)), "")
        value = value.replace("''", "″").replace("'", "′")
        return (name or None), (value or None)
    return None, None


def first_name(html: str) -> str | None:
    name, _ = first_result(html, "itg")
    return name


def ajax_paths(page_html: str) -> dict[str, str]:
    paths: dict[str, str] = {}

    # Overall sub-tabs: ITG/IPG/IMG/IJG/ETG
    for path, typ in re.findall(
        r'data-tabs-ajax="([^"]+)"[^>]*data-type="(itg|ipg|img|ijg|etg)"',
        page_html,
    ):
        paths[typ] = html_lib.unescape(path).replace("\\/", "/")

    # Stage ranking ETE lives in data-ajax-stack JSON-ish attribute.
    for raw in re.findall(r"data-ajax-stack\s*=\s*({[^}]+})", page_html):
        raw = html_lib.unescape(raw).replace("\\/", "/")
        for typ, path in re.findall(r'"(ete|itg|ipg|img|ijg|etg)"\s*:\s*"([^"]+)"', raw):
            paths.setdefault(typ, path)

    return paths


def fetch_rankings(stage: int) -> dict[str, str]:
    page = fetch(RANKING_BASE.format(stage=stage))
    paths = ajax_paths(page)
    out: dict[str, str] = {}
    for typ, field in RANKING_FIELDS.items():
        path = paths.get(typ)
        if not path:
            continue
        try:
            html = fetch("https://www.letour.fr" + path)
        except Exception:
            continue
        name, value = first_result(html, typ)
        if name:
            out[field] = name
        if value:
            out[VALUE_FIELDS[typ]] = value
    # Fallback: visible page usually starts with general leader.
    if "yellow_jersey" not in out:
        name, value = first_result(page, "itg")
        if name:
            out["yellow_jersey"] = name
        if value:
            out["yellow_jersey_total_time"] = value
    if "gc_leader" not in out and out.get("yellow_jersey"):
        out["gc_leader"] = out["yellow_jersey"]
    return out


def main() -> int:
    today_vn = datetime.now(VN_TZ).date()
    if today_vn < START_DATE or today_vn > END_DATE:
        return 0

    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    changed = False
    messages: list[str] = []

    for row in rows:
        n = stage_number(row)
        ds = stage_date_iso(row)
        if not n or not ds:
            continue
        d = date.fromisoformat(ds)
        if d > today_vn:
            continue
        # Rest days have no stage ranking.
        if str(row.get("type", "")).lower() == "rest day":
            continue

        try:
            rankings = fetch_rankings(n)
        except Exception:
            continue
        if not rankings:
            continue

        row_changed = False
        for key, value in rankings.items():
            if row.get(key) != value:
                row[key] = value
                row_changed = True
        if rankings.get("stage_winner") and row.get("status") != "completed":
            row["status"] = "completed"
            row_changed = True
        if row_changed:
            changed = True
            messages.append(
                f"🏁 Chặng {n}: {row.get('stage_winner', '')} {row.get('stage_winner_time', '')} · "
                f"🟨 Áo vàng: {row.get('yellow_jersey') or row.get('gc_leader', '')} {row.get('yellow_jersey_total_time', '')}"
            )

    if not changed:
        return 0

    JSON_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Regenerate ICS if generator exists.
    if GEN_PATH.exists():
        import subprocess

        subprocess.run(["python3", str(GEN_PATH)], cwd=BASE, check=True)

    print("Cập nhật Tour de France 2026:")
    for msg in messages:
        print("- " + msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
