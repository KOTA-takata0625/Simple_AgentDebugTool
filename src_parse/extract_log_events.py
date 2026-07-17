#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


TARGET_EVENT_TYPES = {
    "agent_response",
    "llm_request",
    "user_message",
}


def _get_attrs(event: dict[str, Any]) -> dict[str, Any]:
    attrs = event.get("attrs")
    return attrs if isinstance(attrs, dict) else {}


def _extract_type_and_name_only(value: Any) -> Any:
    if isinstance(value, list):
        extracted_items = []
        for item in value:
            extracted = _extract_type_and_name_only(item)
            if extracted is not None:
                extracted_items.append(extracted)
        return extracted_items or None

    if isinstance(value, dict):
        extracted: dict[str, Any] = {}
        if "type" in value:
            extracted["type"] = value["type"]
        if "name" in value:
            extracted["name"] = value["name"]
        if value.get("type") == "text" and "content" in value:
            extracted["content"] = value["content"]
        if "arguments" in value:
            extracted["arguments"] = value["arguments"]

        for key, nested_value in value.items():
            if key in {"type", "name", "content", "arguments"}:
                continue

            nested_extracted = _extract_type_and_name_only(nested_value)
            if nested_extracted is not None:
                extracted[key] = nested_extracted

        return extracted or None

    return None


def _extract_agent_response_payload(response: Any) -> Any:
    if not isinstance(response, str):
        return _extract_type_and_name_only(response)

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return response

    extracted = _extract_type_and_name_only(parsed)
    if extracted is None:
        return None

    return extracted


def extract_agent_response(event: dict[str, Any]) -> dict[str, Any]:
    attrs = _get_attrs(event)
    return {
        "event_type": "agent_response",
        "reasoning": attrs.get("reasoning"),
        "response": _extract_agent_response_payload(attrs.get("response")),
    }


def extract_llm_request(event: dict[str, Any]) -> dict[str, Any]:
    attrs = _get_attrs(event)
    model = attrs.get("model")
    if model is None:
        model = event.get("model")

    return {
        "event_type": "llm_request",
        "model": model,
        "copilotUsageNanoAiu": attrs.get("copilotUsageNanoAiu"),
        "inputTokens": attrs.get("inputTokens"),
        "outputTokens": attrs.get("outputTokens"),
        "cachedTokens": attrs.get("cachedTokens"),
    }


def extract_event(event: dict[str, Any]) -> Optional[dict[str, Any]]:
    event_type = event.get("type")
    if event_type not in TARGET_EVENT_TYPES:
        return None

    if event_type == "agent_response":
        return extract_agent_response(event)
    if event_type == "llm_request":
        return extract_llm_request(event)
    if event_type == "user_message":
        attrs = _get_attrs(event)
        return {
            "event_type": "user_message",
            "content": attrs.get("content"),
        }

    return None


def extract_title_from_file(title_path: Path) -> Optional[dict[str, Any]]:
    """Extract session title and start datetime from a title JSONL file (title-*.jsonl).

    Returns a dict with keys 'content' (str) and 'datetime' (str, ISO-like), or None.
    """
    ts_ms: Optional[int] = None
    title_content: Optional[str] = None

    with title_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            # session_start 行からタイムスタンプを取得
            if event.get("type") == "session_start" and ts_ms is None:
                ts_val = event.get("ts")
                if isinstance(ts_val, (int, float)):
                    ts_ms = int(ts_val)

            # agent_response 行からタイトル文字列を取得
            if event.get("type") == "agent_response" and title_content is None:
                attrs = event.get("attrs", {})
                response = attrs.get("response")
                if response is not None:
                    try:
                        parsed = json.loads(response) if isinstance(response, str) else response
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, list):
                        for msg in parsed:
                            for part in msg.get("parts", []):
                                if part.get("type") == "text" and "content" in part:
                                    title_content = part["content"]
                                    break

            if ts_ms is not None and title_content is not None:
                break

    if title_content is None:
        return None

    result: dict[str, Any] = {"content": title_content}
    if ts_ms is not None:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone()
        result["datetime"] = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    return result


def _find_title_file(input_path: Path) -> Optional[Path]:
    """Auto-detect title-*.jsonl in the same directory as the input file."""
    candidates = sorted(input_path.parent.glob("title-*.jsonl"))
    return candidates[0] if candidates else None


def process_jsonl(input_path: Path, output_path: Path, title: Optional[dict[str, Any]] = None) -> None:
    with input_path.open("r", encoding="utf-8") as infile, output_path.open(
        "w", encoding="utf-8"
    ) as outfile:
        if title is not None:
            outfile.write(json.dumps({"event_type": "session_title", **title}, ensure_ascii=False))
            outfile.write("\n")
        for line_no, raw_line in enumerate(infile, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError as err:
                print(f"line {line_no}: JSON parse error: {err}", file=sys.stderr)
                continue

            if not isinstance(event, dict):
                continue

            extracted = extract_event(event)
            if extracted is None:
                continue

            outfile.write(json.dumps(extracted, ensure_ascii=False))
            outfile.write("\n")


def _find_runsubagent_files(dir_path: Path) -> list[Path]:
    """Find runSubagent child-session logs under the given directory."""
    return sorted(dir_path.glob("runSubagent-*.jsonl"))


def _process_runsubagent_files(dir_path: Path) -> None:
    """Extract events from each runSubagent-*.jsonl into extracted_<filename>.jsonl."""
    for subagent_input in _find_runsubagent_files(dir_path):
        subagent_output = dir_path / f"extracted_{subagent_input.name}"
        process_jsonl(input_path=subagent_input, output_path=subagent_output, title=None)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract selected events from a JSONL log file."
    )
    parser.add_argument(
        "--dir",
        required=True,
        help=(
            "Directory containing main.jsonl and title-*.jsonl. "
            "Output is written to extracted_main.jsonl in the same directory."
        ),
    )
    parser.add_argument(
        "--no-title",
        action="store_true",
        help="Disable session title extraction even if a title file is found",
    )

    args = parser.parse_args()

    dir_path = Path(args.dir)
    if not dir_path.is_dir():
        print(f"Error: '{dir_path}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    input_path = dir_path / "main.jsonl"
    if not input_path.exists():
        print(f"Error: '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    output_path = dir_path / "extracted_main.jsonl"
    title_path = _find_title_file(input_path)

    title: Optional[dict[str, Any]] = None
    if not args.no_title:
        if title_path is not None and title_path.exists():
            title = extract_title_from_file(title_path)

    process_jsonl(input_path=input_path, output_path=output_path, title=title)
    _process_runsubagent_files(dir_path)


if __name__ == "__main__":
    main()
