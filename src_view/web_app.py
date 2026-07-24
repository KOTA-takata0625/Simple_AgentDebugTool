#!/usr/bin/env python3
"""
AI実行ログビューア
FastAPI エントリポイント（配線専任）
Usage: python3 web_app.py [--host 0.0.0.0] [--port 5001]
"""

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, Response

from html_page_renderer import e
from html_page_renderer import render_date_landing_page as ren_render_date_landing_page
from html_page_renderer import render_page as ren_render_page
from html_page_renderer import render_sessions_page as ren_render_sessions_page
from log_data_io import build_sessions_zip as io_build_sessions_zip
from log_data_io import ensure_extracted_main as io_ensure_extracted_main
from log_data_io import load_events as io_load_events
from session_log_processor import calc_credits as proc_calc_credits
from session_log_processor import extract_session_title as proc_extract_session_title
from session_log_processor import group_blocks as proc_group_blocks
from session_view_service import collect_session_summaries as svc_collect_session_summaries
from session_view_service import load_subagent_entries as svc_load_subagent_entries


VERSION_PATTERN = re.compile(r"^(?:v)?(\d+\.\d)$", re.IGNORECASE)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def load_app_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0"

    matched = VERSION_PATTERN.fullmatch(version)
    if not matched:
        return "0.0"

    # Normalize VERSION to X.Y because rendering adds the "v" prefix.
    return matched.group(1)

# ─────────────────────────────────────────────
# App Factory
# ─────────────────────────────────────────────

def create_app(
    finder_script: Optional[Path] = None,
) -> FastAPI:
    app_version = load_app_version()
    app = FastAPI(title=f"AI Log Viewer v{app_version}")
    finder_path = finder_script or (Path.home() / "find_debug_logs.sh")

    def _resolve_month_start(month_text: Optional[str]) -> datetime:
        if not month_text:
            now = datetime.now()
            return datetime(year=now.year, month=now.month, day=1)

        month_value = month_text.strip()
        if not MONTH_PATTERN.fullmatch(month_value):
            raise ValueError("month must be YYYY-MM")
        return datetime.strptime(month_value, "%Y-%m")

    def _count_for_date(target_date: str) -> tuple[int, str, float]:
        entries, _ = svc_collect_session_summaries(target_date, finder_path)
        credits_total = round(
            sum(float(item.get("credits", 0.0) or 0.0) for item in entries),
            1,
        )
        return len(entries), "live", credits_total

    def _build_month_calendar(month_text: Optional[str]) -> dict:
        month_start = _resolve_month_start(month_text)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        prev_month = month_start - timedelta(days=1)
        prev_month_start = prev_month.replace(day=1)
        days_in_month = (next_month - month_start).days

        cells: list[dict | None] = []
        leading_empty = month_start.weekday()
        for _ in range(leading_empty):
            cells.append(None)

        today_text = datetime.now().strftime("%Y-%m-%d")
        for day in range(1, days_in_month + 1):
            current = month_start.replace(day=day)
            date_text = current.strftime("%Y-%m-%d")
            count, source, credits_total = _count_for_date(date_text)
            cells.append(
                {
                    "date": date_text,
                    "day": day,
                    "count": count,
                    "credits_total": credits_total,
                    "source": source,
                    "is_today": date_text == today_text,
                }
            )

        while len(cells) % 7 != 0:
            cells.append(None)

        month_credits_total = round(
            sum(float(c.get("credits_total", 0.0) or 0.0) for c in cells if c is not None),
            1,
        )

        return {
            "month": month_start.strftime("%Y-%m"),
            "month_label": month_start.strftime("%Y年%m月"),
            "prev_month": prev_month_start.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
            "month_credits_total": month_credits_total,
            "cells": cells,
        }

    def _collect_entries_for_date(target_date: str) -> tuple[list, str]:
        entries, info = svc_collect_session_summaries(target_date, finder_path)
        return entries, f"{info} - source=live"

    def _build_zip_response(files: list[str]):
        zip_bytes, filename, included_count = io_build_sessions_zip(
            files,
            load_events_fn=io_load_events,
            extract_session_title_fn=proc_extract_session_title,
        )
        if included_count == 0:
            return HTMLResponse(content="有効なセッションが選択されていません。", status_code=400)

        content_disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": content_disposition},
        )

    @app.get("/", response_class=HTMLResponse)
    def root(
        date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
        month: Optional[str] = Query(default=None, description="YYYY-MM"),
    ):
        if not date:
            try:
                calendar_data = _build_month_calendar(month)
            except ValueError as ex:
                return HTMLResponse(content=f"invalid month: {e(ex)}", status_code=400)

            html = ren_render_date_landing_page(calendar_data, app_version=app_version)
            return HTMLResponse(content=html)

        target_date = date.strip()
        if not DATE_PATTERN.fullmatch(target_date):
            return HTMLResponse(content=f"invalid date format: {e(target_date)}", status_code=400)

        entries, info = _collect_entries_for_date(target_date)
        html = ren_render_sessions_page(target_date, entries, info, None, app_version=app_version)
        return HTMLResponse(content=html)

    @app.get("/view", response_class=HTMLResponse)
    def view(file: Optional[str] = Query(default=None, description="extracted_main.jsonl path")):
        if not file:
            return HTMLResponse(
                content=(
                    f"<h1>AI Log Viewer v{e(app_version)}</h1>"
                    "<p>表示対象の file クエリが未指定です。</p>"
                    '<p><a href="/">セッション一覧へ</a></p>'
                ),
                status_code=400,
            )
        target = Path(file).expanduser()
        if target.name == "extracted_main.jsonl":
            refreshed = io_ensure_extracted_main(target.parent)
            if refreshed is not None:
                target = refreshed
        if not target.exists():
            return HTMLResponse(content=f"file not found: {e(target)}", status_code=404)

        events = io_load_events(target)
        subagent_entries = svc_load_subagent_entries(target)
        session_title = proc_extract_session_title(events)
        blocks = proc_group_blocks(events)
        html = ren_render_page(
            blocks,
            session_title,
            subagent_entries,
            source_file=target,
            app_version=app_version,
            calc_credits_fn=proc_calc_credits,
        )
        return HTMLResponse(content=html)

    @app.get("/download/zip")
    def download_zip(
        file: Optional[str] = Query(default=None, description="session file path"),
        files: list[str] = Query(default=[]),
    ):
        requested: list[str] = []
        if file:
            requested.append(file)
        requested.extend(files)
        if not requested:
            return HTMLResponse(content="file または files パラメータが必要です。", status_code=400)
        return _build_zip_response(requested)

    return app


# ─────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI実行ログビューア")
    parser.add_argument("--host", default="0.0.0.0", help="バインドホスト (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5001, help="ポート番号 (default: 5001)")
    parser.add_argument(
        "--finder-script",
        default=str(Path.home() / "find_debug_logs.sh"),
        help="ライブ一覧モードで使用する日付検索スクリプトのパス",
    )
    args = parser.parse_args()

    finder_script = Path(args.finder_script).expanduser()

    app = create_app(finder_script=finder_script)
    print(f"起動: http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
