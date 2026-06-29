#!/usr/bin/env python3
"""Generate Tour de France 2026 ICS from tour-de-france-2026.json."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
JSON_PATH = BASE / "tour-de-france-2026.json"
ICS_PATH = BASE / "tour-de-france-2026.ics"


def esc(value: object) -> str:
    """Escape text for a single-line ICS field."""
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def stage_description(row: dict, stage: str) -> str:
    """Build DESCRIPTION. Uses compact Vietnamese race-info fields when available."""
    has_vi_detail = any(
        row.get(k)
        for k in [
            "date_vi",
            "start_time_vi",
            "distance_vi",
            "terrain_type_vi",
            "gradient_final_km_vi",
            "vertical_meters_vi",
            "departure_vi",
            "arrival_vi",
        ]
    )

    if has_vi_detail:
        lines = [row.get("race_info_title_vi") or "Thông tin cuộc đua"]
        fields = [
            ("Ngày", "date_vi"),
            ("Giờ bắt đầu", "start_time_vi"),
            ("Khoảng cách", "distance_vi"),
            ("Loại đường đua", "terrain_type_vi"),
            ("Độ dốc km cuối", "gradient_final_km_vi"),
            ("Độ cao chênh lệch", "vertical_meters_vi"),
            ("Điểm xuất phát", "departure_vi"),
            ("Điểm đến", "arrival_vi"),
        ]
        for label, key in fields:
            lines.append(f"{label}: {row.get(key, '')}")
    else:
        lines = [
            f"Điểm xuất phát: {row.get('start', '')}",
            f"Điểm đích: {row.get('finish', '')}",
            f"Cự ly chặng: {row.get('distance', '')}",
            f"Loại chặng: {row.get('type', '')}",
            f"Ngày: {row.get('date_iso', '')}",
            f"Lộ trình: {row.get('route', '')}",
        ]

    return "\n".join(lines)


def generate() -> None:
    rows = json.loads(JSON_PATH.read_text())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Nguyen Vu//Tour de France 2026//VI",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Tour de France 2026",
        "X-WR-TIMEZONE:Asia/Ho_Chi_Minh",
    ]
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for row in rows:
        stage = str(row.get("stage", "")).strip()
        date_iso = row.get("date_iso")
        if not date_iso:
            # Fallback for rows edited by hand on GitHub UI
            for src_key in ("date", "date_vi"):
                raw = str(row.get(src_key, "")).strip()
                if not raw:
                    continue
                # Accept YYYY-MM-DD or DD month YYYY / DD tháng M năm YYYY if present manually.
                try:
                    if raw.count("-") == 2 and len(raw) == 10:
                        date_iso = raw
                        break
                except Exception:
                    pass
            if not date_iso:
                raise KeyError(f"Missing date_iso for stage={stage!r}; add date_iso in tour-de-france-2026.json")
        dt = datetime.strptime(date_iso, "%Y-%m-%d")
        is_rest = stage == "-" or "rest" in row.get("type", "").lower() or "rest" in row.get("route", "").lower()
        summary = (
            f"Tour de France 2026 · Rest Day · {row.get('route', '')}"
            if is_rest
            else f"Tour de France 2026 · Chặng {stage} · {row.get('route', '')}"
        )
        uid = hashlib.sha1(
            f"tdf2026-{date_iso}-{stage}-{row.get('route', '')}".encode("utf-8")
        ).hexdigest() + "@nguyenvu"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{dt:%Y%m%d}",
            f"DTEND;VALUE=DATE:{(dt + timedelta(days=1)):%Y%m%d}",
            f"SUMMARY:{esc(summary)}",
            f"DESCRIPTION:{esc(stage_description(row, stage))}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    ICS_PATH.write_text("\r\n".join(lines) + "\r\n")
    print(f"Wrote {ICS_PATH} with {len(rows)} events")


if __name__ == "__main__":
    generate()
