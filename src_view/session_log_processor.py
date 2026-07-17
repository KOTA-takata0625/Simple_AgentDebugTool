import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


def group_blocks(events: list) -> list:
    """イベントを表示ブロック単位にグループ化する"""

    def new_block(user_text: str = "") -> dict:
        return {
            "user_text": user_text,
            "pairs": [],
        }

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


def extract_session_title(events: list) -> dict:
    """先頭付近の session_title を抽出する"""
    for ev in events:
        if ev.get("event_type") == "session_title":
            return {
                "content": ev.get("content", ""),
                "datetime": ev.get("datetime", ""),
            }
    return {"content": "", "datetime": ""}


def calc_credits(block: dict) -> float:
    total = 0.0
    for pair in block.get("pairs", []):
        lr = pair.get("llm_request")
        if lr:
            nano = lr.get("copilotUsageNanoAiu") or 0
            total += nano / 1_000_000_000
    return round(total, 1)


def parse_session_datetime(dt_text: str) -> float:
    if not dt_text:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S JST", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_text, fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def collect_session_summaries(
    date_str: str,
    finder_script: Path,
    *,
    ensure_extracted_main_fn: Callable[[Path], Optional[Path]],
    load_events_fn: Callable[[Path], list],
    load_subagent_entries_fn: Callable[[Path], list],
    group_blocks_fn: Callable[[list], list],
    extract_session_title_fn: Callable[[list], dict],
    calc_credits_fn: Callable[[dict], float],
    parse_session_datetime_fn: Callable[[str], float],
) -> tuple[list, str]:
    if not finder_script.exists():
        return [], f"find script not found: {finder_script}"

    try:
        proc = subprocess.run(
            [str(finder_script), date_str],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as ex:
        stderr = (ex.stderr or "").strip()
        return [], f"session search failed: {stderr or ex}"
    except Exception as ex:
        return [], f"session search failed: {ex}"

    debug_dirs = []
    for ln in (proc.stdout or "").splitlines():
        s = ln.strip()
        if s.startswith("/"):
            p = Path(s)
            if p.is_dir():
                debug_dirs.append(p)

    entries = []
    skipped = 0
    for d in debug_dirs:
        extracted = ensure_extracted_main_fn(d)
        if extracted is None:
            skipped += 1
            continue

        try:
            events = load_events_fn(extracted)
            blocks = group_blocks_fn(events)
            session = extract_session_title_fn(events)
            main_total = round(sum(calc_credits_fn(b) for b in blocks), 1)
            sub_total = round(
                sum(float(x.get("total_credits", 0.0) or 0.0) for x in load_subagent_entries_fn(extracted)),
                1,
            )
            total_credits = round(main_total + sub_total, 1)
            title = (session.get("content") or "").strip() or d.name
            dt_text = (session.get("datetime") or "").strip()
            entries.append(
                {
                    "title": title,
                    "datetime": dt_text,
                    "blocks": len(blocks),
                    "credits": total_credits,
                    "file": str(extracted),
                    "sort_ts": parse_session_datetime_fn(dt_text),
                }
            )
        except Exception:
            skipped += 1

    entries.sort(key=lambda x: x.get("sort_ts", 0.0), reverse=True)
    info = f"{len(entries)} sessions"
    if skipped:
        info += f" (skipped {skipped})"
    return entries, info
