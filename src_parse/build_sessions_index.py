#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path


def load_events(path: Path) -> list:
    events = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def group_blocks(events: list) -> list:
    def new_block(user_text: str = "") -> dict:
        return {"user_text": user_text, "pairs": []}

    blocks = []
    current = None

    for ev in events:
        t = ev.get("event_type")

        if t == "session_title":
            continue

        if t == "user_message":
            if current is not None:
                blocks.append(current)
            current = new_block(user_text=ev.get("content", ""))
            continue

        if t == "llm_request":
            if current is None:
                current = new_block()
            current["pairs"].append({"llm_request": ev, "agent_response": None})
            continue

        if t == "agent_response":
            if current is None:
                current = new_block()

            if current["pairs"] and current["pairs"][-1].get("agent_response") is None:
                current["pairs"][-1]["agent_response"] = ev
            else:
                current["pairs"].append({"llm_request": None, "agent_response": ev})

    if current is not None:
        blocks.append(current)

    return blocks


def calc_credits(block: dict) -> float:
    total = 0.0
    for pair in block.get("pairs", []):
        lr = pair.get("llm_request")
        if lr:
            nano = lr.get("copilotUsageNanoAiu") or 0
            total += nano / 1_000_000_000
    return round(total, 1)


def extract_session_title(events: list) -> dict:
    for ev in events:
        if ev.get("event_type") == "session_title":
            return {
                "content": ev.get("content", ""),
                "datetime": ev.get("datetime", ""),
            }
    return {"content": "", "datetime": ""}


def parse_session_datetime(dt_text: str) -> float:
    if not dt_text:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S JST", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_text, fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def session_matches_date(dt_text: str, date_str: str) -> bool:
    if not dt_text:
        return False
    for fmt in ("%Y-%m-%d %H:%M:%S JST", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_text, fmt).strftime("%Y-%m-%d") == date_str
        except ValueError:
            continue
    return dt_text.startswith(f"{date_str} ")


def collect_debug_dirs(date_str: str, finder_script: Path) -> list[Path]:
    proc = subprocess.run(
        [str(finder_script), date_str],
        check=True,
        capture_output=True,
        text=True,
    )

    result = []
    for ln in (proc.stdout or "").splitlines():
        s = ln.strip()
        if s.startswith("/"):
            p = Path(s)
            if p.is_dir():
                result.append(p)
    return result


def ensure_extracted_main(debug_dir: Path, parser_script: Path) -> Path | None:
    extracted = debug_dir / "extracted_main.jsonl"

    # Rebuild extracted files from source logs to reflect latest main/runSubagent updates.
    if extracted.exists():
        extracted.unlink()
    for sub in debug_dir.glob("extracted_runSubagent-*.jsonl"):
        if sub.is_file():
            sub.unlink()

    try:
        subprocess.run(
            ["python3", str(parser_script), "--dir", str(debug_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None

    return extracted if extracted.exists() else None


def calc_subagent_total(extracted_main: Path) -> float:
    total = 0.0
    for sub in sorted(extracted_main.parent.glob("extracted_runSubagent-*.jsonl")):
        events = load_events(sub)
        blocks = group_blocks(events)
        total += sum(calc_credits(b) for b in blocks)
    return round(total, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sessions index from debug logs")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--finder-script", default=str(Path.home() / "find_debug_logs.sh"), help="Path to find_debug_logs.sh")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--ensure-extracted", action="store_true", help="Run extractor when extracted_main.jsonl does not exist")
    args = parser.parse_args()

    finder_script = Path(args.finder_script).expanduser()
    if not finder_script.exists():
        raise SystemExit(f"finder script not found: {finder_script}")

    repo_root = Path(__file__).resolve().parents[1]
    parser_script = repo_root / "src_parse" / "extract_log_events.py"

    debug_dirs = collect_debug_dirs(args.date, finder_script)

    sessions = []
    skipped = 0
    filtered = 0
    for debug_dir in debug_dirs:
        extracted = debug_dir / "extracted_main.jsonl"
        if args.ensure_extracted:
            extracted = ensure_extracted_main(debug_dir, parser_script) or extracted

        if not extracted.exists():
            skipped += 1
            continue

        try:
            events = load_events(extracted)
            blocks = group_blocks(events)
            session = extract_session_title(events)
            main_total = round(sum(calc_credits(b) for b in blocks), 1)
            sub_total = calc_subagent_total(extracted)
            total_credits = round(main_total + sub_total, 1)
            title = (session.get("content") or "").strip() or debug_dir.name
            dt_text = (session.get("datetime") or "").strip()

            if not session_matches_date(dt_text, args.date):
                filtered += 1
                continue

            sessions.append(
                {
                    "title": title,
                    "datetime": dt_text,
                    "blocks": len(blocks),
                    "credits": total_credits,
                    "file": str(extracted),
                    "debug_dir": str(debug_dir),
                    "sort_ts": parse_session_datetime(dt_text),
                }
            )
        except Exception:
            skipped += 1

    sessions.sort(key=lambda x: x.get("sort_ts", 0.0), reverse=True)
    for s in sessions:
        s.pop("sort_ts", None)

    out = {
        "date": args.date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "info": (
            f"{len(sessions)} sessions"
            + (f" (skipped {skipped})" if skipped else "")
            + (f" (filtered {filtered})" if filtered else "")
        ),
        "sessions": sessions,
    }

    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"index written: {out_path}")
    print(out["info"])


if __name__ == "__main__":
    main()
