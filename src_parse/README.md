# src_parse 責務メモ

このディレクトリは、Copilot Chat の debug logs（JSONL）を表示・集計しやすい形式へ抽出・正規化する責務を持ちます。

生ログを直接 UI で扱うのではなく、src_parse で `extracted_*.jsonl` に変換したうえで、src_view 側が一覧化・可視化を行います。

## 概要

- 主な構成要素は次の 2 つ
  - `extract_log_events.py`
    - 生ログから必要イベントを抽出し、`extracted_main.jsonl` 等を生成
  - `find_debug_logs.sh`
    - workspaceStorage 配下の debug-logs ディレクトリを列挙
- src_parse は「抽出・整形」までを担当

## 実行方法と前提

### 依存関係

- Python 3
- Bash（`find_debug_logs.sh` 実行時）

`extract_log_events.py` は標準ライブラリのみで動作します。

### 1. 単体セッション抽出（通常導線）

プロジェクトルートで実行:

~~~bash
python3 src_parse/extract_log_events.py --dir /path/to/debug-logs/<session-id>
~~~

出力:

- `extracted_main.jsonl`
- `extracted_runSubagent-*.jsonl`（存在する場合）

### 2. debug-logs ディレクトリ列挙

~~~bash
export WORKSPACE_STORAGE_DIR="$HOME/.vscode-server/data/User/workspaceStorage"
src_parse/find_debug_logs.sh 2026-07-24
~~~

出力:

- `*/GitHub.copilot-chat/debug-logs/*` に一致した絶対パス（1 行 1 件）

## 入出力ファイル

### 入力（生ログ）

- `main.jsonl`
- `title-*.jsonl`（任意）
- `runSubagent-*.jsonl`（任意）

### 出力（抽出ログ）

- `extracted_main.jsonl`
- `extracted_runSubagent-*.jsonl`

## 責務

- イベント抽出
- 破損 JSON の耐性処理
- タイトル情報の先頭付与
- サブエージェント JSONL の抽出

## 抽出仕様（extract_log_events.py）

### CLI

~~~text
python3 src_parse/extract_log_events.py --dir <debug-log-dir> [--no-title]
~~~

- `--dir`（必須）
  - `main.jsonl` を含む debug-log ディレクトリ
- `--no-title`（任意）
  - `title-*.jsonl` が存在しても `session_title` を生成しない

### 抽出対象イベント

- `agent_response`
- `llm_request`
- `user_message`

上記以外のイベントは出力しません。

### 出力イベント形式

#### session_title（抽出時に先頭へ付与）

`title-*.jsonl` から取得できた場合にのみ、先頭へ 1 行追加されます。

~~~json
{"event_type":"session_title","content":"...","datetime":"2026-07-24 10:20:30 JST"}
~~~

#### user_message

~~~json
{"event_type":"user_message","content":"..."}
~~~

#### llm_request

~~~json
{
  "event_type": "llm_request",
  "model": "...",
  "attachments": [{"id": "...", "filePath": "..."}],
  "copilotUsageNanoAiu": 123456789,
  "inputTokens": 1000,
  "outputTokens": 200,
  "cachedTokens": 300
}
~~~

補足:

- model は複数候補パスから探索して抽出
- token / credit 値は数値化できる値のみ採用
- `attrs.userRequest` 内の `<attachment ...>` タグを解析して `attachments` を生成

#### agent_response

~~~json
{
  "event_type": "agent_response",
  "reasoning": "...",
  "response": [
    {"type": "text", "content": "..."},
    {"type": "tool_call", "name": "...", "arguments": {...}}
  ]
}
~~~

補足:

- `response` が JSON 文字列の場合はパースを試行
- JSON が途中で切れている場合、括弧・文字列終端を補って修復を試行
- 抽出後は `type` / `name`（`text` の場合は `content`、tool_call の場合は `arguments`）中心に縮約

### タイトル抽出仕様

- `title-*.jsonl` を同一ディレクトリから自動探索（名前順先頭を採用）
- 取得対象
  - `session_start` の `ts`（ミリ秒）
  - 最初の `agent_response` 内テキスト
- `ts` はローカルタイムゾーン時刻文字列へ変換して `datetime` に格納

### サブエージェント抽出

- 同一ディレクトリの `runSubagent-*.jsonl` を列挙
- 各ファイルを `extracted_runSubagent-*.jsonl` として個別出力
- サブエージェント側には `session_title` を付与しません

## ディレクトリ列挙仕様（find_debug_logs.sh）

### CLI

~~~text
src_parse/find_debug_logs.sh YYYY-MM-DD
~~~

### 入力

- 引数: `YYYY-MM-DD`（形式検証あり）
- 環境変数: `WORKSPACE_STORAGE_DIR`（未指定時は `$HOME/.vscode-server/data/User/workspaceStorage`）

### 出力

- `find` 条件 `*/GitHub.copilot-chat/debug-logs/*` に一致するディレクトリを sort して出力

重要:

- 本スクリプトは「日付形式の妥当性」は確認しますが、ディレクトリ自体を日付範囲で絞り込む実装にはなっていません。
- 実際の日付フィルタは呼び出し側（src_view 等）が実施します。

## クレジット計算（共通概念）

- 基本式
  - `llm_request.copilotUsageNanoAiu / 1,000,000,000`
- block credits
  - block 内の llm_request 合算（小数 1 桁丸め）
- session credits
  - main 側合計 + `extracted_runSubagent-*.jsonl` 側合計

## エラーハンドリング

### extract_log_events.py

- `--dir` がディレクトリでない: エラー終了
- `main.jsonl` が存在しない: エラー終了
- JSONL の壊れた行: 行番号付きで stderr 出力し、当該行をスキップ

### find_debug_logs.sh

- 引数不足または形式不正: エラー終了
- `WORKSPACE_STORAGE_DIR` が存在しない: エラー終了

## よくある注意点

1. `find_debug_logs.sh` は列挙専用

- 日付で絞り込んで見える挙動は、通常 src_view 側のフィルタによるものです。

2. `title-*.jsonl` が無い場合

- `session_title` が付かないため、呼び出し側はフォールバック（例: ディレクトリ名）を使います。

3. 抽出仕様更新時の再生成

- model や attachments の抽出仕様が変わった場合、既存 `extracted_*.jsonl` は古い形式の可能性があります。

## ファイル別責務

### extract_log_events.py

- 役割
  - 生ログから表示・集計用の最小イベントを抽出
- 主な責務
  - 対象イベント選別（`agent_response` / `llm_request` / `user_message`）
  - response の縮約
  - model/tokens/credits 抽出
  - attachment 解析・重複排除
  - title 情報抽出と `session_title` 付与
  - runSubagent ファイルの抽出

### find_debug_logs.sh

- 役割
  - workspaceStorage 配下の debug-logs ディレクトリ列挙
- 主な責務
  - 引数バリデーション
  - 探索パス確定
  - sort 済み絶対パス出力
