from functools import lru_cache
import html as html_lib
import json
import re
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote


CACHE_RATE_CAUTION_THRESHOLD = 40.0
CACHE_RATE_WARNING_THRESHOLD = 20.0
CACHE_RATE_CHECK_THRESHOLD = 60.0
OUTPUT_TOKEN_CHECK_THRESHOLD = 1000
OUTPUT_TOKEN_CAUTION_THRESHOLD = 4000
OUTPUT_TOKEN_WARNING_THRESHOLD = 8000
INPUT_GROWTH_CHECK_THRESHOLD = 3000
INPUT_GROWTH_CAUTION_THRESHOLD = 8000
INPUT_GROWTH_WARNING_THRESHOLD = 20000

TOOL_DISPLAY_LABELS: dict[str, list[str]] = {
    "grep_search": ["query"],
    "memory": ["command", "path"],
    "list_dir": ["path"],
    "apply_patch": ["Update File"],
    "read_file": ["filePath"],
    "file_search": ["query"],
    "create_file": ["filePath"],
}
MISSING_TOOL_VALUE = "(no value)"


def e(text: str) -> str:
    """HTML escape."""
    return html_lib.escape(str(text), quote=True)


def _consume_subagent_entry(render_ctx: dict) -> Optional[dict]:
    entries = render_ctx.get("subagent_entries", [])
    cursor = render_ctx.get("subagent_cursor", 0)
    if cursor >= len(entries):
        return None
    render_ctx["subagent_cursor"] = cursor + 1
    return entries[cursor]


def _normalize_tool_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    return " ".join(text.split())


def _extract_update_file_path(value: object) -> str:
    if not isinstance(value, str):
        return ""
    match = re.search(r"^\*\*\* Update File:\s*(.+?)\s*$", value, flags=re.MULTILINE)
    return "" if match is None else match.group(1).strip()


def _extract_mapped_tool_values(tool_name: str, parsed_args: object, raw_args: object) -> list[str]:
    normalized_tool_name = tool_name.rsplit(".", 1)[-1]
    labels = TOOL_DISPLAY_LABELS.get(normalized_tool_name)
    if not labels:
        return []

    values: list[str] = []
    args_dict = parsed_args if isinstance(parsed_args, dict) else {}
    raw_text = raw_args if isinstance(raw_args, str) else ""

    for label in labels:
        value_text = ""
        if label == "Update File":
            direct = args_dict.get("Update File") if isinstance(args_dict, dict) else None
            value_text = _normalize_tool_value(direct)
            if not value_text:
                input_text = args_dict.get("input") if isinstance(args_dict, dict) else ""
                value_text = _extract_update_file_path(input_text)
            if not value_text:
                value_text = _extract_update_file_path(raw_text)
        else:
            if isinstance(args_dict, dict) and label in args_dict:
                value_text = _normalize_tool_value(args_dict.get(label))

        values.append(value_text or MISSING_TOOL_VALUE)

    return values


def _prefixed_uid(render_ctx: dict, base: str) -> str:
    prefix = str(render_ctx.get("id_prefix", ""))
    return f"{prefix}{base}"


@lru_cache(maxsize=2)
def load_template_text(name: str) -> str:
    template_path = Path(__file__).resolve().parent / "templates" / name
    return template_path.read_text(encoding="utf-8")


def _severity_class_for_cache_rate(rate: float) -> str:
    if rate < CACHE_RATE_WARNING_THRESHOLD:
        return "metric-warning"
    if rate < CACHE_RATE_CAUTION_THRESHOLD:
        return "metric-caution"
    if rate < CACHE_RATE_CHECK_THRESHOLD:
        return "metric-check"
    return ""


def _severity_class_for_output_tokens(output_tokens: int) -> str:
    if output_tokens >= OUTPUT_TOKEN_WARNING_THRESHOLD:
        return "metric-warning"
    if output_tokens >= OUTPUT_TOKEN_CAUTION_THRESHOLD:
        return "metric-caution"
    if output_tokens >= OUTPUT_TOKEN_CHECK_THRESHOLD:
        return "metric-check"
    return ""


def _severity_class_for_input_growth(input_growth: int) -> str:
    if input_growth >= INPUT_GROWTH_WARNING_THRESHOLD:
        return "metric-warning"
    if input_growth >= INPUT_GROWTH_CAUTION_THRESHOLD:
        return "metric-caution"
    if input_growth >= INPUT_GROWTH_CHECK_THRESHOLD:
        return "metric-check"
    return ""


def _badge_class_for_input_growth(input_growth: int) -> str:
    severity_class = _severity_class_for_input_growth(input_growth)
    if severity_class:
        return severity_class
    if input_growth > 0:
        return "metric-muted"
    return ""


def _format_optional_number(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _format_optional_credits(nano_aiu: object) -> str:
    if nano_aiu is None:
        return "—"
    try:
        return f"{(int(nano_aiu) / 1_000_000_000):.2f}"
    except (TypeError, ValueError):
        return "—"


def _normalize_attachments(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        attachment_id = item.get("id")
        file_path = item.get("filePath")
        if attachment_id is None and file_path is None:
            continue

        normalized.append(
            {
                "id": "" if attachment_id is None else str(attachment_id),
                "filePath": "" if file_path is None else str(file_path),
            }
        )

    return normalized


def _render_attachments_card(lr: dict) -> str:
    attachments = _normalize_attachments(lr.get("attachments"))
    if not attachments:
        return ""

    items_html = []
    for item in attachments:
        attachment_id = e(item.get("id") or "(no id)")
        file_path = e(item.get("filePath") or "(no filePath)")
        items_html.append(
            """
<div class="attachment-item">
    <div class="attachment-id">"""
            + attachment_id
            + """</div>
    <div class="attachment-path">"""
            + file_path
            + """</div>
</div>"""
        )

    return (
        """
<div class="attachments-card">
    <div class="attachments-title">Attachments</div>
"""
        + "\n".join(items_html)
        + """
</div>"""
    )


def render_tool_call_part(
        part: dict,
        idx: int,
        render_ctx: dict,
        *,
        calc_credits_fn: Callable[[dict], float],
) -> str:
    name = e(part.get("name", ""))
    raw_name = str(part.get("name", ""))
    raw_args = part.get("arguments", "")
    parsed: object = raw_args
    try:
        parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        args_str = json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        args_str = str(raw_args)

    summary_values = _extract_mapped_tool_values(raw_name, parsed, raw_args)
    summary_html = ""
    if summary_values:
        summary_html = f'<span class="tool-summary">{e(" ".join(summary_values))}</span>'

    uid = _prefixed_uid(render_ctx, f"tc-{idx}-{name}")
    subagent_panel_html = ""

    if raw_name == "runSubagent" and render_ctx.get("enable_subagent_panel", True):
        entry = _consume_subagent_entry(render_ctx)
        panel_uid = f"{uid}-subagent-panel"
        btn_uid = f"{uid}-subagent-btn"

        if entry is not None:
            file_name = e(entry.get("file_name", ""))
            line_count = entry.get("line_count", 0)
            sub_blocks = entry.get("blocks", [])
            sub_total = float(entry.get("total_credits", 0.0) or 0.0)
            sub_count = len(sub_blocks)
            sub_title = e((entry.get("session_title") or {}).get("content", ""))

            if render_ctx.get("track_subagent_credits", False):
                current_block = render_ctx.get("current_block_idx")
                if current_block is not None:
                    block_map = render_ctx.setdefault("block_subagent_credits", {})
                    block_map[current_block] = block_map.get(current_block, 0.0) + sub_total

                current_pair = render_ctx.get("current_pair_key")
                if current_pair is not None:
                    pair_map = render_ctx.setdefault("pair_subagent_credits", {})
                    pair_map[current_pair] = pair_map.get(current_pair, 0.0) + sub_total

                render_ctx["consumed_subagent_total"] = render_ctx.get("consumed_subagent_total", 0.0) + sub_total

            sub_ctx = {
                "subagent_entries": [],
                "subagent_cursor": 0,
                "id_prefix": f"{entry.get('id', 'subagent')}-",
                "enable_subagent_panel": False,
                "track_subagent_credits": False,
                "block_subagent_credits": {},
                "pair_subagent_credits": {},
                "current_block_idx": None,
                "current_pair_key": None,
                "consumed_subagent_total": 0.0,
            }
            sub_blocks_html = "\n".join(
                render_block(b, i, sub_ctx, calc_credits_fn=calc_credits_fn)
                for i, b in enumerate(sub_blocks)
            )
            title_html = f' · <span class="subagent-title">{sub_title}</span>' if sub_title else ""
            subagent_panel_html = f"""
    <div class="subagent-action-row">
        <button class="subagent-toggle-btn" id="{btn_uid}" onclick="event.stopPropagation();toggleSubagentPanel('{panel_uid}', '{btn_uid}')">詳細を開く</button>
    </div>
    <div class="subagent-panel" id="{panel_uid}" style="display:none">
        <div class="subagent-panel-meta">subAgent JSONL: {file_name} ({line_count} lines){title_html}</div>
        <div class="subagent-panel-summary">{sub_count} blocks · {sub_total:.1f} total credits</div>
        <div class="subagent-rendered">{sub_blocks_html}</div>
    </div>"""
        else:
            subagent_panel_html = """
    <div class="subagent-action-row">
        <span class="subagent-missing">対応する subAgent JSONL が見つかりません</span>
    </div>"""

    return f"""
<div class="tool-call">
    <div class="tool-call-header" onclick="toggleDetail('{uid}')">
        <span class="tool-icon">⚙</span>
        <span class="tool-name">{name}</span>
        {summary_html}
        <span class="toggle-arrow" id="{uid}-arrow">▶</span>
    </div>
    <pre class="tool-args" id="{uid}" style="display:none">{e(args_str)}</pre>
    {subagent_panel_html}
</div>"""


def render_response_parts(parts: list, pair_idx: int, render_ctx: dict, *, calc_credits_fn: Callable[[dict], float]) -> str:
        html_parts = []
        tc_count = 0
        for part in parts:
                ptype = part.get("type")
                if ptype == "text":
                        content = part.get("content", "")
                        if content.strip():
                                html_parts.append(f'<div class="response-text">{e(content)}</div>')
                elif ptype == "tool_call":
                        html_parts.append(
                                render_tool_call_part(
                                        part,
                                        pair_idx * 100 + tc_count,
                                        render_ctx,
                                        calc_credits_fn=calc_credits_fn,
                                )
                        )
                        tc_count += 1
        return "\n".join(html_parts)


def render_agent_response(ar: dict, pair_idx: int, render_ctx: dict, *, calc_credits_fn: Callable[[dict], float]) -> str:
        reasoning = ar.get("reasoning", "")
        response = ar.get("response", [])
        uid = _prefixed_uid(render_ctx, f"reasoning-{pair_idx}")

        parts_html = []
        for item in response:
                item_parts = item.get("parts", []) if isinstance(item, dict) else []
                parts_html.append(render_response_parts(item_parts, pair_idx, render_ctx, calc_credits_fn=calc_credits_fn))

        reasoning_html = ""
        if reasoning:
                reasoning_html = f"""
<div class="reasoning-block">
    <div class="section-header" onclick="toggleDetail('{uid}')">
        <span class="section-icon">🧠</span>
        <span class="section-label">Reasoning</span>
        <span class="toggle-arrow" id="{uid}-arrow">▶</span>
    </div>
    <pre class="reasoning-body" id="{uid}" style="display:none">{e(reasoning)}</pre>
</div>"""

        response_html = ""
        combined = "\n".join(parts_html).strip()
        if combined:
                response_html = f'<div class="response-block">{combined}</div>'

        return reasoning_html + response_html


def render_llm_request(lr: dict, body_uid: str, subagent_credits: float = 0.0) -> str:
    raw_model = lr.get("model")
    model = e(raw_model or "—")
    nano = lr.get("copilotUsageNanoAiu")
    credits_display = _format_optional_credits(nano)
    input_tok = lr.get("inputTokens")
    output_tok = lr.get("outputTokens")
    cached_tok = lr.get("cachedTokens")
    input_growth = lr.get("input_growth")
    input_severity_class = ""
    output_severity_class = ""
    input_tok_value = None
    if input_tok is not None:
        try:
            input_tok_value = int(input_tok)
        except (TypeError, ValueError):
            input_tok_value = None

    if output_tok is not None:
        try:
            output_severity_class = _severity_class_for_output_tokens(int(output_tok))
        except (TypeError, ValueError):
            output_severity_class = ""

    cache_rate_html = ""
    if cached_tok is not None and input_tok_value is not None and input_tok_value > 0:
        rate = round(cached_tok / input_tok_value * 100, 1)
        cache_severity_class = _severity_class_for_cache_rate(rate)
        cache_rate_html = f'<span class="token-badge cache {cache_severity_class}">Cache {rate}%</span>'

    input_growth_html = ""
    if input_growth is not None:
        try:
            growth_val = int(input_growth)
            growth_severity_class = _severity_class_for_input_growth(growth_val)
            growth_badge_class = _badge_class_for_input_growth(growth_val)
            input_severity_class = growth_severity_class
            if growth_badge_class:
                input_growth_html = f'<span class="token-badge input-growth {growth_badge_class}">in +{growth_val:,}</span>'
        except (TypeError, ValueError):
            pass

    input_display = _format_optional_number(input_tok)
    cached_display = _format_optional_number(cached_tok)
    output_display = _format_optional_number(output_tok)
    cached_severity_class = "metric-warning" if cached_display == "—" else ""
    subagent_html = ""
    if subagent_credits > 0:
        subagent_html = f'<span class="subagent-inline">subAgent {subagent_credits:.2f} credits</span>'

    return f"""
<div class="llm-meta" onclick="toggleDetail('{body_uid}')" title="クリックで展開 / 折りたたみ">
    <div class="llm-meta-row">
        <span class="model-name">{model}</span>
        <span class="credits-inline">{credits_display} credits</span>
        <span class="token-badge input {input_severity_class}">in {input_display}</span>
        {input_growth_html}
        <span class="token-badge cached {cached_severity_class}">cached {cached_display}</span>
        <span class="token-badge output {output_severity_class}">out {output_display}</span>
        {cache_rate_html}
        {subagent_html}
        <span class="toggle-arrow" id="{body_uid}-arrow">▶</span>
    </div>
</div>"""


def render_block(
        block: dict,
        block_idx: int,
        render_ctx: dict,
        *,
        calc_credits_fn: Callable[[dict], float],
) -> str:
    content = block.get("user_text", "")

    track_sub = render_ctx.get("track_subagent_credits", False)
    if track_sub:
        render_ctx["current_block_idx"] = block_idx

    pairs_html = []
    for i, pair in enumerate(block["pairs"]):
        lr = pair.get("llm_request")
        ar = pair.get("agent_response")
        uid = _prefixed_uid(render_ctx, f"pair-body-{block_idx}-{i}")

        if track_sub:
            render_ctx["current_pair_key"] = (block_idx, i)

        ar_html = ""
        if ar:
            inner = render_agent_response(ar, block_idx * 1000 + i, render_ctx, calc_credits_fn=calc_credits_fn)
            ar_html = f'<div class="pair-body" id="{uid}" style="display:none">{inner}</div>'

        pair_sub_credits = 0.0
        if track_sub:
            pair_sub_credits = float(render_ctx.get("pair_subagent_credits", {}).get((block_idx, i), 0.0) or 0.0)
            render_ctx["current_pair_key"] = None

        lr_html = render_llm_request(lr, uid, pair_sub_credits) if lr else ""

        pairs_html.append(f"""
<div class="pair-card">
    {lr_html}
    {ar_html}
</div>""")

    if track_sub:
        render_ctx["current_block_idx"] = None

    main_credits = calc_credits_fn(block)
    sub_credits = 0.0
    if track_sub:
        sub_credits = float(render_ctx.get("block_subagent_credits", {}).get(block_idx, 0.0) or 0.0)
    total_credits = round(main_credits + sub_credits, 1)

    block_input_growth_html = ""
    block_input_growth = block.get("input_growth")
    if block_input_growth is not None:
        try:
            growth_val = int(block_input_growth)
            growth_class = _badge_class_for_input_growth(growth_val)
            if growth_class:
                block_input_growth_html = (
                    f'<span class="token-badge input-growth {growth_class} block-input-growth">'
                    f'in +{growth_val:,}'
                    "</span>"
                )
        except (TypeError, ValueError):
            pass

    pairs_combined = "\n".join(pairs_html)

    msg_text = e(content.strip())
    block_attachments = {"attachments": block.get("user_request_attachments", [])}
    attachments_html = _render_attachments_card(block_attachments)

    user_card_html = ""
    if msg_text or attachments_html:
        user_card_html = f"""
    <div class="user-message-card">
    <pre class="user-message-text">{msg_text}</pre>
    {attachments_html}
    </div>"""

    return f"""
<section class="block" id="block-{block_idx}">
    <div class="block-header">
    <span class="total-credits">Total Credits {total_credits:.1f}</span>
    {block_input_growth_html}
    </div>
    {user_card_html}
    {pairs_combined}
</section>"""


def render_page(
        blocks: list,
        session_title: dict | None = None,
        subagent_entries: Optional[list] = None,
    source_file: Optional[Path] = None,
    app_version: str = "0.0",
        *,
        calc_credits_fn: Callable[[dict], float],
) -> str:
        render_ctx = {
                "subagent_entries": subagent_entries or [],
                "subagent_cursor": 0,
                "id_prefix": "",
                "enable_subagent_panel": True,
                "track_subagent_credits": True,
                "block_subagent_credits": {},
                "pair_subagent_credits": {},
                "current_block_idx": None,
                "current_pair_key": None,
                "consumed_subagent_total": 0.0,
        }
        blocks_html = "\n".join(render_block(b, i, render_ctx, calc_credits_fn=calc_credits_fn) for i, b in enumerate(blocks))
        total_all = round(
                sum(calc_credits_fn(b) for b in blocks) + float(render_ctx.get("consumed_subagent_total", 0.0) or 0.0),
                1,
        )
        block_count = len(blocks)
        session_title = session_title or {"content": "", "datetime": ""}
        title_content = e(session_title.get("content", ""))
        title_datetime = e(session_title.get("datetime", ""))
        session_html = ""
        if title_content:
                session_html = f'<span class="session-title">{title_content}</span>'
                if title_datetime:
                        session_html += f'<span class="session-datetime">{title_datetime}</span>'

        action_html = ""
        if source_file is not None:
            zip_href = f"/download/zip?file={quote(str(source_file))}"
            action_html = f'<a class="app-action" href="{zip_href}">このセッションをZIP</a>'

        title_button_html = '<a class="app-title app-title-link" href="/">AI Log Viewer</a>'
        reload_button_html = '<button class="app-action app-reload-btn" type="button" onclick="window.location.reload()">更新</button>'
        version_html = f'<span class="app-version">v{e(app_version)}</span>'

        styles_css = load_template_text("styles.css")
        scripts_js = load_template_text("scripts.js")

        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Log Viewer</title>
<style>
{styles_css}
</style>
</head>
<body>

<header class="app-header">
    {title_button_html}
    {reload_button_html}
    {version_html}
    {session_html}
    {action_html}
    <span class="app-summary">{block_count} blocks · {total_all:.1f} total credits</span>
</header>

<main class="main">
{blocks_html}
</main>

<script>
{scripts_js}
</script>
</body>
</html>"""


def render_sessions_page(
    date_str: str,
    entries: list,
    info: str,
    default_file: Optional[Path],
    app_version: str = "0.0",
) -> str:
        rows = []
        for item in entries:
                file_path = str(item["file"])
                href = f"/view?file={quote(file_path)}"
                zip_href = f"/download/zip?file={quote(file_path)}"
                row = (
                        f'<div class="session-row">'
                        f'<label class="session-row-check" title="このセッションを選択">'
                        f'<input class="session-select" type="checkbox" name="files" value="{e(file_path)}">'
                        f"</label>"
                        f'<a class="session-row-main" href="{href}">'
                        f'<span class="session-row-title">{e(item["title"])}</span>'
                        f'<span class="session-row-date">{e(item["datetime"] or "—")}</span>'
                        f"</a>"
                        f'<span class="session-row-metrics">{item["blocks"]} blocks · {item["credits"]:.1f} total credits</span>'
                        f'<a class="session-row-download" href="{zip_href}">ZIP</a>'
                        f"</div>"
                )
                rows.append(row)

        rows_html = "\n".join(rows) if rows else '<div class="empty">表示対象がありません</div>'
        action_items = ['<button class="action-btn reload-btn" type="button" onclick="window.location.reload()">更新</button>']
        action_items.append('<a href="/">日付選択へ</a>')
        if default_file is not None:
            default_href = f"/view?file={quote(str(default_file))}"
            action_items.append(f'<a href="{default_href}">既定ログを開く</a>')
        action_html = f'<span class="actions">{"".join(action_items)}</span>'

        list_html = rows_html
        if rows:
                list_html = f"""
<section class="bulk-actions" id="bulk-download-section">
    <div class="bulk-bar">
        <label class="check-all">
            <input type="checkbox" id="select-all-sessions">
            <span>すべて選択</span>
        </label>
        <button id="download-selected-btn" type="button" disabled>選択をZIPダウンロード</button>
        <span class="selected-count" id="selected-count">0件選択</span>
    </div>
    <section class="list">{rows_html}</section>
</section>
<script>
(() => {{
  const section = document.getElementById('bulk-download-section');
  const selectAll = document.getElementById('select-all-sessions');
  const button = document.getElementById('download-selected-btn');
  const countLabel = document.getElementById('selected-count');
  const items = Array.from(document.querySelectorAll('.session-select'));

  if (!section || !selectAll || !button || !countLabel || items.length === 0) return;

  const refresh = () => {{
    const checkedCount = items.filter((el) => el.checked).length;
    button.disabled = checkedCount === 0;
    countLabel.textContent = `${{checkedCount}}件選択`;
    selectAll.checked = checkedCount === items.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < items.length;
  }};

  selectAll.addEventListener('change', () => {{
    items.forEach((el) => {{
      el.checked = selectAll.checked;
    }});
    refresh();
  }});

  items.forEach((el) => {{
    el.addEventListener('change', refresh);
  }});

    button.addEventListener('click', () => {{
        const selected = items.filter((el) => el.checked).map((el) => el.value);
        if (selected.length === 0) {{
            alert('少なくとも1件選択してください。');
            return;
        }}

        const params = new URLSearchParams();
        selected.forEach((value) => params.append('files', value));
    button.disabled = true;
    button.textContent = 'ZIP作成中...';
        window.location.href = `/download/zip?${{params.toString()}}`;
    }});

  refresh();
}})();
</script>"""

        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Log Sessions</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    font-family: "Segoe UI", "Noto Sans JP", system-ui, sans-serif;
    background: #f5f5f5;
    color: #343a40;
}}
.wrap {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 20px 16px 32px;
}}
.head {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 14px;
}}
.title {{
    font-size: 22px;
    font-weight: 800;
    color: #1c7ed6;
    text-decoration: none;
    border: 1px solid #a5d8ff;
    background: #e7f5ff;
    border-radius: 999px;
    padding: 4px 10px;
}}
.version {{
    font-size: 12px;
    font-weight: 700;
    color: #495057;
    border: 1px solid #ced4da;
    background: #ffffff;
    border-radius: 999px;
    padding: 3px 8px;
}}
.meta {{
    color: #6c757d;
    font-size: 13px;
}}
.actions a {{
    font-size: 13px;
    color: #0b7285;
    text-decoration: none;
    border: 1px solid #99e9f2;
    background: #e3fafc;
    border-radius: 999px;
    padding: 4px 10px;
}}
.actions {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
}}
.action-btn.reload-btn {{
    font-size: 13px;
    font-weight: 700;
    color: #0b7285;
    border: 1px solid #99e9f2;
    background: #e3fafc;
    border-radius: 999px;
    padding: 4px 10px;
    cursor: pointer;
    font-family: inherit;
}}
.bulk-actions {{
    display: grid;
    gap: 10px;
}}
.bulk-bar {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    background: #ffffff;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 10px 12px;
}}
.check-all {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    color: #343a40;
    user-select: none;
}}
#download-selected-btn {{
    border: 1px solid #0b7285;
    background: #e3fafc;
    color: #0b7285;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 700;
    padding: 6px 12px;
    cursor: pointer;
}}
#download-selected-btn:disabled {{
    opacity: 0.55;
    cursor: not-allowed;
}}
.selected-count {{
    color: #495057;
    font-size: 13px;
}}
.list {{
    display: grid;
    gap: 10px;
}}
.session-row {{
    display: grid;
    grid-template-columns: 42px minmax(260px, 1.7fr) minmax(170px, 1fr) 72px;
    gap: 10px;
    padding: 12px 14px;
    background: #ffffff;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    align-items: center;
}}
.session-row:hover {{
    border-color: #74c0fc;
    background: #f8fbff;
}}
.session-row-check {{
    display: flex;
    justify-content: center;
}}
.session-select {{
    width: 16px;
    height: 16px;
    cursor: pointer;
}}
.session-row-main {{
    display: grid;
    gap: 4px;
    color: inherit;
    text-decoration: none;
}}
.session-row-main:hover .session-row-title {{
    color: #1864ab;
}}
.session-row-title {{
    font-weight: 700;
    color: #212529;
    word-break: break-word;
}}
.session-row-date {{
    font-size: 13px;
    color: #495057;
}}
.session-row-metrics {{
    font-size: 13px;
    color: #495057;
}}
.session-row-download {{
    justify-self: end;
    font-size: 12px;
    font-weight: 700;
    color: #0b7285;
    text-decoration: none;
    border: 1px solid #99e9f2;
    background: #e3fafc;
    border-radius: 999px;
    padding: 4px 10px;
}}
.empty {{
    padding: 20px;
    border: 1px dashed #ced4da;
    background: #fff;
    border-radius: 8px;
    color: #868e96;
}}
@media (max-width: 900px) {{
    .session-row {{
        grid-template-columns: 32px 1fr;
        gap: 8px;
    }}
    .session-row-metrics {{
        grid-column: 2;
        text-align: left;
    }}
    .session-row-download {{
        grid-column: 2;
        justify-self: start;
    }}
}}
</style>
</head>
<body>
    <main class="wrap">
        <div class="head">
            <a class="title" href="/">AI Log Viewer</a>
            <span class="version">v{e(app_version)}</span>
            <span class="meta">date: {e(date_str)} · {e(info)}</span>
            {action_html}
        </div>
        {list_html}
    </main>
</body>
</html>"""


def render_date_landing_page(
    calendar_data: dict,
    app_version: str = "0.0",
) -> str:
    month_label = e(calendar_data.get("month_label", ""))
    prev_month = str(calendar_data.get("prev_month", "")).strip()
    next_month = str(calendar_data.get("next_month", "")).strip()
    cells = calendar_data.get("cells", [])

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_html = "".join(f'<div class="weekday">{d}</div>' for d in weekdays)

    cell_html_parts = []
    for cell in cells:
        if cell is None:
            cell_html_parts.append('<div class="cal-cell cal-empty"></div>')
            continue

        date_text = str(cell.get("date", "")).strip()
        day_num = int(cell.get("day", 0) or 0)
        count = int(cell.get("count", 0) or 0)
        credits_total = float(cell.get("credits_total", 0.0) or 0.0)
        source = str(cell.get("source", "live")).strip() or "live"
        today_class = " is-today" if cell.get("is_today") else ""

        body_html = (
            f'<span class="day-number">{day_num}</span>'
            f'<span class="day-count">{count}件</span>'
            f'<span class="day-credits">{credits_total:.1f} AIU</span>'
            f'<span class="day-source">{e(source)}</span>'
        )

        if count > 0:
            href = f"/?date={quote(date_text)}"
            cell_html_parts.append(
                f'<a class="cal-cell is-active{today_class}" href="{href}" title="{e(date_text)}">'
                f"{body_html}"
                f"</a>"
            )
        else:
            cell_html_parts.append(
                f'<div class="cal-cell is-disabled{today_class}" title="{e(date_text)} (0件)">'
                f"{body_html}"
                f"</div>"
            )

    cells_html = "\n".join(cell_html_parts) if cell_html_parts else '<div class="empty">表示できる日付がありません</div>'
    prev_href = f"/?month={quote(prev_month)}" if prev_month else "/"
    next_href = f"/?month={quote(next_month)}" if next_month else "/"
    month_credits_total = float(calendar_data.get("month_credits_total", 0.0) or 0.0)
    month_credits_html = f'<span class="month-credits-total">{month_credits_total:.1f} AIU / 月</span>'
    reload_button_html = '<button class="action-btn reload-btn" type="button" onclick="window.location.reload()">更新</button>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Log Dates</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    font-family: "Segoe UI", "Noto Sans JP", system-ui, sans-serif;
    background: #f5f5f5;
    color: #343a40;
}}
.wrap {{
    max-width: 900px;
    margin: 0 auto;
    padding: 20px 16px 32px;
}}
.head {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 14px;
}}
.title {{
    font-size: 22px;
    font-weight: 800;
    color: #1c7ed6;
    text-decoration: none;
    border: 1px solid #a5d8ff;
    background: #e7f5ff;
    border-radius: 999px;
    padding: 4px 10px;
}}
.version {{
    font-size: 12px;
    font-weight: 700;
    color: #495057;
    border: 1px solid #ced4da;
    background: #ffffff;
    border-radius: 999px;
    padding: 3px 8px;
}}
.meta {{
    color: #6c757d;
    font-size: 13px;
}}
.action-btn.reload-btn {{
    font-size: 13px;
    font-weight: 700;
    color: #0b7285;
    border: 1px solid #99e9f2;
    background: #e3fafc;
    border-radius: 999px;
    padding: 4px 10px;
    cursor: pointer;
    font-family: inherit;
}}
.month-nav {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 12px;
}}
.month-link {{
    color: #0b7285;
    text-decoration: none;
    border: 1px solid #99e9f2;
    background: #e3fafc;
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 13px;
    font-weight: 700;
}}
.month-label {{
    color: #343a40;
    font-weight: 800;
}}
.month-center {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
}}
.month-credits-total {{
    color: #1c7ed6;
    font-size: 13px;
    font-weight: 700;
}}
.calendar {{
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 10px;
}}
.weekday {{
    text-align: center;
    color: #495057;
    font-size: 12px;
    font-weight: 700;
    padding: 4px 0;
}}
.cal-cell {{
    min-height: 92px;
    border: 1px solid #dee2e6;
    border-radius: 10px;
    background: #ffffff;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}}
.cal-empty {{
    border-style: dashed;
    background: #f8f9fa;
}}
.cal-cell.is-active {{
    text-decoration: none;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
}}
.cal-cell.is-active:hover {{
    border-color: #74c0fc;
    background: #f8fbff;
}}
.cal-cell.is-disabled {{
    background: #f1f3f5;
    border-color: #dee2e6;
    opacity: 0.8;
}}
.cal-cell.is-today {{
    box-shadow: inset 0 0 0 2px #74c0fc;
}}
.day-number {{
    color: #212529;
    font-size: 16px;
    font-weight: 700;
}}
.day-count {{
    width: fit-content;
    color: #343a40;
    font-size: 12px;
    border: 1px solid #ced4da;
    background: #ffffff;
    border-radius: 999px;
    padding: 4px 8px;
}}
.day-credits {{
    color: #495057;
    font-size: 12px;
    font-weight: 700;
}}
.day-source {{
    color: #6c757d;
    font-size: 11px;
}}
.note {{
    margin-top: 12px;
    color: #868e96;
    font-size: 12px;
}}
.empty {{
    grid-column: 1 / -1;
    padding: 20px;
    border: 1px dashed #ced4da;
    background: #fff;
    border-radius: 8px;
    color: #868e96;
}}
@media (max-width: 700px) {{
    .calendar {{
        gap: 6px;
    }}
    .cal-cell {{
        min-height: 78px;
        padding: 8px;
    }}
    .day-number {{
        font-size: 14px;
    }}
    .day-count,
    .day-credits {{
        font-size: 11px;
    }}
    .day-source {{
        display: none;
    }}
}}
</style>
</head>
<body>
    <main class="wrap">
        <div class="head">
            <a class="title" href="/">AI Log Viewer</a>
            {reload_button_html}
            <span class="version">v{e(app_version)}</span>
            <span class="meta">件数+AI credit（AIU）つきカレンダー（0件は選択不可）</span>
        </div>
        <div class="month-nav">
            <a class="month-link" href="{prev_href}">前月</a>
            <div class="month-center">
                <span class="month-label">{month_label}</span>
                {month_credits_html}
            </div>
            <a class="month-link" href="{next_href}">翌月</a>
        </div>
        <section class="calendar">
            {weekday_html}
            {cells_html}
        </section>
        <p class="note">※ 0件の日付はグレーアウトされ、クリックできません。</p>
    </main>
</body>
</html>"""
