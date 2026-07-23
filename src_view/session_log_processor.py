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

    def block_input_total(block: dict) -> int:
        total = 0
        for pair in block.get("pairs", []):
            lr = pair.get("llm_request")
            if not lr:
                continue
            input_tokens = lr.get("inputTokens")
            if input_tokens is None:
                continue
            try:
                total += int(input_tokens)
            except (TypeError, ValueError):
                pass
        return total

    def finalize_block(block: dict, previous_total: int | None) -> int:
        current_total = block_input_total(block)
        block["input_tokens_total"] = current_total

        # ブロック内の最初と最後の inputTokens 差分を計算
        pairs_with_input = [
            p for p in block.get("pairs", [])
            if p.get("llm_request") and p["llm_request"].get("inputTokens") is not None
        ]
        if len(pairs_with_input) >= 2:
            try:
                first_val = int(pairs_with_input[0]["llm_request"]["inputTokens"])
                last_val = int(pairs_with_input[-1]["llm_request"]["inputTokens"])
                growth = last_val - first_val
                if growth > 0:
                    block["input_growth"] = growth
            except (TypeError, ValueError):
                pass

        return current_total

    blocks = []
    current = None
    previous_input_tokens = None
    previous_block_input_total = None

    for ev in events:
        t = ev.get("event_type")

        if t == "session_title":
            continue

        if t == "user_message":
            if current is not None:
                previous_block_input_total = finalize_block(current, previous_block_input_total)
                blocks.append(current)
            current = new_block(user_text=ev.get("content", ""))
            previous_input_tokens = None
            continue

        if t == "llm_request":
            if current is None:
                current = new_block()

            # Calculate request-level input token growth inside a single user message block.
            current_input_tokens = ev.get("inputTokens")
            if current_input_tokens is not None and previous_input_tokens is not None:
                try:
                    current_val = int(current_input_tokens)
                    previous_val = int(previous_input_tokens)
                    growth = current_val - previous_val
                    if growth > 0:
                        ev["input_growth"] = growth
                except (TypeError, ValueError):
                    pass

            # Update previous input tokens for next comparison.
            if current_input_tokens is not None:
                try:
                    previous_input_tokens = int(current_input_tokens)
                except (TypeError, ValueError):
                    pass

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
        previous_block_input_total = finalize_block(current, previous_block_input_total)
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


def calc_total_input_tokens(blocks: list) -> int:
    """Calculate total input tokens across all blocks."""
    total = 0
    for block in blocks:
        for pair in block.get("pairs", []):
            lr = pair.get("llm_request")
            if lr:
                input_tok = lr.get("inputTokens")
                if input_tok is not None:
                    try:
                        total += int(input_tok)
                    except (TypeError, ValueError):
                        pass
    return total


def parse_session_datetime(dt_text: str) -> float:
    if not dt_text:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S JST", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_text, fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def session_filter_reason(dt_text: str, date_str: str) -> str | None:
    if not dt_text:
        return "session_title.datetime is empty"
    for fmt in ("%Y-%m-%d %H:%M:%S JST", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed_date = datetime.strptime(dt_text, fmt).strftime("%Y-%m-%d")
            if parsed_date != date_str:
                return f"date mismatch ({parsed_date} != {date_str})"
            return None
        except ValueError:
            continue
    if dt_text.startswith(f"{date_str} "):
        return None
    return f"unparseable session_title.datetime: {dt_text}"


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
    filtered = 0
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

            main_jsonl = d / "main.jsonl"
            if main_jsonl.exists():
                session_date = datetime.fromtimestamp(main_jsonl.stat().st_mtime).strftime("%Y-%m-%d")
            else:
                session_date = datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d")

            if session_date != date_str:
                filtered += 1
                continue

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
    if filtered:
        info += f" (filtered {filtered})"
    return entries, info
