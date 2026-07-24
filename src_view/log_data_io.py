import json
import re
import subprocess
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zipfile import ZIP_DEFLATED, ZipFile


def _extracted_llm_request_has_missing_model(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict) or event.get("event_type") != "llm_request":
                    continue
                model = event.get("model")
                if model is None:
                    return True
                if isinstance(model, str) and model.strip().lower() in {"", "none"}:
                    return True
    except OSError:
        return True
    return False


def _extracted_llm_request_has_missing_attachments(path: Path) -> bool:
    """Return True when legacy extracted data lacks llm_request.attachments key."""
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict) or event.get("event_type") != "llm_request":
                    continue
                if "attachments" not in event:
                    return True
    except OSError:
        return True
    return False


def _should_rebuild_extracted(debug_dir: Path, extracted: Path, parser_script: Path) -> bool:
    main_jsonl = debug_dir / "main.jsonl"
    if not extracted.exists():
        return True
    if parser_script.exists() and parser_script.stat().st_mtime > extracted.stat().st_mtime:
        return True
    if main_jsonl.exists() and main_jsonl.stat().st_mtime > extracted.stat().st_mtime:
        return True
    if _extracted_llm_request_has_missing_model(extracted):
        return True
    return _extracted_llm_request_has_missing_attachments(extracted)


def load_events(path: Path) -> list:
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def load_subagent_entries(
    path: Path,
    *,
    load_events_fn: Callable[[Path], list],
    group_blocks_fn: Callable[[list], list],
    extract_session_title_fn: Callable[[list], dict],
    calc_credits_fn: Callable[[dict], float],
) -> list:
    """同一ディレクトリの extracted_runSubagent-*.jsonl を読み込む"""
    entries = []
    for i, sub_path in enumerate(sorted(path.parent.glob("extracted_runSubagent-*.jsonl"))):
        try:
            content = sub_path.read_text(encoding="utf-8")
        except Exception:
            content = "(failed to load subAgent jsonl)"

        events = load_events_fn(sub_path)
        blocks = group_blocks_fn(events)
        session_title = extract_session_title_fn(events)
        total_credits = round(sum(calc_credits_fn(b) for b in blocks), 1)
        line_count = sum(1 for ln in content.splitlines() if ln.strip())

        entries.append(
            {
                "id": f"subagent-{i}",
                "file_name": sub_path.name,
                "line_count": line_count,
                "content": content,
                "blocks": blocks,
                "session_title": session_title,
                "total_credits": total_credits,
            }
        )
    return entries


def ensure_extracted_main(debug_dir: Path) -> Optional[Path]:
    extracted = debug_dir / "extracted_main.jsonl"
    repo_root = Path(__file__).resolve().parents[1]
    parser_script = repo_root / "src_parse" / "extract_log_events.py"
    if not parser_script.exists():
        return None

    if extracted.exists() and not _should_rebuild_extracted(debug_dir, extracted, parser_script):
        return extracted

    if extracted.exists():
        try:
            extracted.unlink()
        except OSError:
            pass
    for sub in debug_dir.glob("extracted_runSubagent-*.jsonl"):
        if sub.is_file():
            try:
                sub.unlink()
            except OSError:
                pass

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


def _parse_session_datetime(dt_text: str) -> float:
    if not dt_text:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S JST", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_text, fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def load_sessions_index(index_path: Path) -> tuple[list, str, str]:
    if not index_path.exists():
        return [], "", f"index not found: {index_path}"

    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as ex:
        return [], "", f"index load failed: {ex}"

    raw_entries = data.get("sessions", []) if isinstance(data, dict) else []
    entries = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue

        try:
            blocks = int(item.get("blocks", 0) or 0)
            credits = float(item.get("credits", 0.0) or 0.0)
        except Exception:
            continue

        file_path = str(item.get("file", "")).strip()
        if not file_path:
            continue

        dt_text = str(item.get("datetime", "")).strip()
        entries.append(
            {
                "title": str(item.get("title", "")).strip() or Path(file_path).parent.name,
                "datetime": dt_text,
                "blocks": blocks,
                "credits": credits,
                "file": file_path,
                "sort_ts": _parse_session_datetime(dt_text),
            }
        )

    entries.sort(key=lambda x: x.get("sort_ts", 0.0), reverse=True)
    date_label = str(data.get("date", "")) if isinstance(data, dict) else ""
    info = str(data.get("info", f"{len(entries)} sessions")) if isinstance(data, dict) else f"{len(entries)} sessions"
    return entries, date_label, info


def _sanitize_zip_component(text: str, fallback: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return fallback
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
    return sanitized or fallback


def _extract_date_label(dt_text: str) -> str:
    if not dt_text:
        return "unknown-date"
    for fmt in ("%Y-%m-%d %H:%M:%S JST", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    head = dt_text.strip()[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", head):
        return head
    return "unknown-date"


def _unique_name(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    idx = 2
    while True:
        candidate = f"{base}__{idx}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        idx += 1


def build_sessions_zip(
    selected_files: list[str],
    *,
    load_events_fn: Callable[[Path], list],
    extract_session_title_fn: Callable[[list], dict],
) -> tuple[bytes, str, int]:
    """選択された extracted_main.jsonl 群を ZIP 化する。"""
    normalized_paths = []
    seen = set()
    for raw in selected_files:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text
        if key in seen:
            continue
        seen.add(key)
        normalized_paths.append(Path(text).expanduser())

    used_dirs: set[str] = set()
    included_count = 0
    buffer = BytesIO()

    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        for main_path in normalized_paths:
            if not main_path.exists() or not main_path.is_file():
                continue

            events = load_events_fn(main_path)
            title = extract_session_title_fn(events)
            title_text = _sanitize_zip_component((title or {}).get("content", ""), "untitled")
            date_label = _extract_date_label((title or {}).get("datetime", ""))
            base_dir = _unique_name(f"{date_label}__{title_text}", used_dirs)

            try:
                zf.writestr(f"{base_dir}/extracted_main.jsonl", main_path.read_bytes())
            except Exception:
                continue

            included_count += 1

            subagent_paths = sorted(main_path.parent.glob("extracted_runSubagent-*.jsonl"))
            for sub_path in subagent_paths:
                if not sub_path.is_file():
                    continue
                try:
                    zf.writestr(f"{base_dir}/{sub_path.name}", sub_path.read_bytes())
                except Exception:
                    continue

    filename = f"ai_log_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return buffer.getvalue(), filename, included_count
