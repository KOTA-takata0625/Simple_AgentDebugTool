# src_parse 責務メモ

このディレクトリは、AI実行ログ(JSONL)の抽出・集計用データ作成を担当します。

## ファイル別の責務

### build_sessions_index.py
- 役割: 指定日付のセッション一覧(index JSON)を生成する
- 主な入力:
  - `src_parse/find_debug_logs.sh` の検索結果(デバッグログディレクトリ群)
  - 各ディレクトリの `extracted_main.jsonl` / `extracted_runSubagent-*.jsonl`
- 主な出力:
  - `sessions_index.json` 相当のJSON
- 主な責務:
  - 日付対象ディレクトリ収集
  - 抽出ログの存在確認と必要に応じた再生成
  - セッション単位のタイトル/日時/ブロック数/クレジット集計
  - 日付フィルタ・時刻ソート・indexファイル書き出し

### extract_log_events.py
- 役割: 生ログから必要イベントだけを抽出し、軽量JSONLへ変換する
- 主な入力:
  - `--dir` で指定したディレクトリ配下の `main.jsonl`
  - (任意) `title-*.jsonl`
  - `runSubagent-*.jsonl`
- 主な出力:
  - `extracted_main.jsonl`
  - `extracted_runSubagent-*.jsonl`
- 主な責務:
  - `agent_response` / `llm_request` / `user_message` のみ抽出
  - `agent_response` の構造を表示に必要な項目へ縮約
  - タイトルログからセッションタイトル/開始日時を抽出して先頭イベント化
  - サブエージェントログも同様に抽出

### find_debug_logs.sh
- 役割: 指定日付の debug-logs ディレクトリを列挙する
- 主な入力:
  - 引数 `YYYY-MM-DD`
  - `WORKSPACE_STORAGE_DIR` (`start_ai_logview.sh` から export して渡す。)
- 主な出力:
  - 条件に一致した `GitHub.copilot-chat/debug-logs/*` ディレクトリの絶対パス一覧
- 主な責務:
  - 日付形式のバリデーション
  - 対象日 00:00:00 から翌日 00:00:00 未満の範囲でディレクトリ検索
  - ソート済み結果の標準出力

## 責務境界
- `src_parse` は「ログを表示しやすい形に整える」までを担当
- HTML生成やWeb配信は `src_view` 側で担当
