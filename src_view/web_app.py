#!/usr/bin/env python3
"""
AI実行ログビューア
FastAPI エントリポイント（配線専任）
Usage: python3 web_app.py [--sessions-index path/to/sessions_index.json] [--host 0.0.0.0] [--port 5001]
"""

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, Response

from html_page_renderer import e
from html_page_renderer import render_page as ren_render_page
from html_page_renderer import render_sessions_page as ren_render_sessions_page
from log_data_io import build_sessions_zip as io_build_sessions_zip
from log_data_io import load_events as io_load_events
from log_data_io import load_sessions_index as io_load_sessions_index
from session_log_processor import calc_credits as proc_calc_credits
from session_log_processor import extract_session_title as proc_extract_session_title
from session_log_processor import group_blocks as proc_group_blocks
from session_view_service import collect_session_summaries as svc_collect_session_summaries
from session_view_service import load_subagent_entries as svc_load_subagent_entries


VERSION_PATTERN = re.compile(r"^\d+\.\d$")


def load_app_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0"

    return version if VERSION_PATTERN.fullmatch(version) else "0.0"

# ─────────────────────────────────────────────
# App Factory
# ─────────────────────────────────────────────

def create_app(
    sessions_index_path: Optional[Path] = None,
    finder_script: Optional[Path] = None,
) -> FastAPI:
    app_version = load_app_version()
    app = FastAPI(title=f"AI Log Viewer v{app_version}")
    finder_path = finder_script or (Path.home() / "find_debug_logs.sh")

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
    def sessions(date: Optional[str] = Query(default=None, description="YYYY-MM-DD")):
        if sessions_index_path is not None:
            entries, index_date, index_info = io_load_sessions_index(sessions_index_path)
            target_date = date or index_date or datetime.now().strftime("%Y-%m-%d")
            info = f"{index_info} - source=index"
            html = ren_render_sessions_page(target_date, entries, info, None, app_version=app_version)
            return HTMLResponse(content=html)

        target_date = date or datetime.now().strftime("%Y-%m-%d")
        entries, info = svc_collect_session_summaries(target_date, finder_path)
        info = f"{info} - source=live"
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
        "--sessions-index",
        default=None,
        help="セッション一覧JSON(index)のパス。指定時は / が index ベースで表示される",
    )
    parser.add_argument(
        "--finder-script",
        default=str(Path.home() / "find_debug_logs.sh"),
        help="ライブ一覧モードで使用する日付検索スクリプトのパス",
    )
    args = parser.parse_args()

    sessions_index_path = Path(args.sessions_index) if args.sessions_index else None
    finder_script = Path(args.finder_script).expanduser()

    app = create_app(sessions_index_path=sessions_index_path, finder_script=finder_script)
    print(f"起動: http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
