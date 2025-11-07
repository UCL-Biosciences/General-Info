#!/usr/bin/env python3
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EVENTS_DIR = REPO_ROOT / "events"
ARCHIVE_DIR = EVENTS_DIR / "archive"
README = REPO_ROOT / "README.md"
MARKER_START = "<!-- EVENTS:START -->"
MARKER_END = "<!-- EVENTS:END -->"
DEFAULT_TZ = ZoneInfo("Europe/London")
ARCHIVE_AGE_DAYS = 90

DATE_FMT_IN = ["%Y-%m-%d %H:%M", "%Y-%m-%d"]
DATE_FMT_OUT = "%Y-%m-%d"

def parse_start(dt_str: str, tz_str: str | None):
    tz = DEFAULT_TZ
    if tz_str:
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = DEFAULT_TZ
    last_err = None
    for fmt in DATE_FMT_IN:
        try:
            dt = datetime.strptime(dt_str, fmt)
            return dt.replace(tzinfo=tz)  # treat naive as local to tz
        except ValueError as e:
            last_err = e
    raise ValueError(f"Cannot parse start '{dt_str}': {last_err}")

def load_events():
    if not EVENTS_DIR.exists():
        return []
    events = []
    for path in EVENTS_DIR.glob("[0-9]*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        title = data.get("title")
        start_raw = data.get("start")
        tz_str = data.get("timezone")
        if not title or not start_raw:
            continue
        start = parse_start(str(start_raw), tz_str)
        events.append({
            "path": path,
            "title": title,
            "start": start,
            "date_str": start.strftime(DATE_FMT_OUT),
            "location": data.get("location", ""),
            "link": data.get("link") or data.get("registration_link") or "",
            "summary": data.get("summary", "") or "",
            "id": data.get("id", path.stem),
        })
    return events

def classify_events(events):
    now = datetime.now(DEFAULT_TZ)
    cutoff = now - timedelta(days=ARCHIVE_AGE_DAYS)
    upcoming, past_recent, to_archive = [], [], []
    for e in events:
        if e["start"] >= now:
            upcoming.append(e)
        elif e["start"] >= cutoff:
            past_recent.append(e)
        else:
            to_archive.append(e)
    upcoming.sort(key=lambda x: x["start"])
    past_recent.sort(key=lambda x: x["start"], reverse=True)
    return upcoming, past_recent, to_archive

def move_to_archive(items):
    if not items:
        return False
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    changed = False
    for e in items:
        src = e["path"]
        dst = ARCHIVE_DIR / src.name
        if not dst.exists():
            shutil.move(str(src), str(dst))
            changed = True
    return changed

def render_table(rows):
    header = "| Date | Title | Location | Description | Link |\n|------|-------|----------|-------------|------|"
    if not rows:
        return header + "\n| – | – | – | – | – |"
    lines = [header]
    for e in rows:
        desc = e["summary"].strip().replace("\n", " ")
        link_md = f"[link]({e['link']})" if e["link"] else ""
        lines.append(f"| {e['date_str']} | {e['title']} | {e['location']} | {desc} | {link_md} |")
    return "\n".join(lines)

def update_readme(upcoming, past_recent):
    content = README.read_text(encoding="utf-8")
    pattern = re.compile(rf"{re.escape(MARKER_START)}[\s\S]*?{re.escape(MARKER_END)}", re.M)
    if not pattern.search(content):
        raise RuntimeError("Markers not found in README.md")
    block = (
        f"{MARKER_START}\n\n"
        f"### Upcoming\n\n{render_table(upcoming)}\n\n"
        f"### Recent Past (last 90 days)\n\n{render_table(past_recent)}\n\n"
        f"{MARKER_END}"
    )
    new_content = pattern.sub(block, content)
    if new_content != content:
        README.write_text(new_content, encoding="utf-8")
        return True
    return False

def main():
    events = load_events()
    upcoming, past_recent, to_archive = classify_events(events)
    moved = move_to_archive(to_archive)
    updated = update_readme(upcoming, past_recent)
    print("changes" if (moved or updated) else "nochanges")

if __name__ == "__main__":
    main()
