# src_view 責務メモ

このディレクトリは、抽出済みログの読み込み・加工・表示(Web)を担当します。

## ファイル別の責務

### web_app.py
- 役割: FastAPIエントリポイント(配線専任)
- 主な入力:
  - クエリパラメータ(`/`, `/view`, `/download/zip`)
  - `sessions_index.json`(indexモード時)
- 主な出力:
  - セッション一覧HTML
  - セッション詳細HTML
  - ZIPダウンロードレスポンス
- 主な責務:
  - ルーティング定義
  - 各層(`log_data_io`/`session_log_processor`/`session_view_service`/`html_page_renderer`)の呼び出し配線
  - レスポンス組み立て

### session_view_service.py
- 役割: 画面向けユースケースの組み立て
- 主な責務:
  - 依存関数を束ねた `collect_session_summaries` の提供
  - サブエージェント一覧読み込みの窓口提供

### log_data_io.py
- 役割: ファイルI/Oと外部プロセス連携
- 主な責務:
  - JSONL読み込み
  - `extracted_runSubagent-*.jsonl` の読み込みと整形
  - `extract_log_events.py` 呼び出しによる抽出ファイル生成補助
  - index JSON読み込み
  - 選択セッション一式のZIP生成

### session_log_processor.py
- 役割: ログイベントのドメイン処理(純粋ロジック寄り)
- 主な責務:
  - イベント列を会話ブロックへグルーピング
  - セッションタイトル抽出
  - クレジット計算
  - 日時解析
  - 日付指定セッション一覧の収集・集計

### html_page_renderer.py
- 役割: 詳細画面/一覧画面のHTML文字列生成
- 主な責務:
  - エスケープやテンプレート読み込み
  - LLMリクエスト/レスポンス/ツール呼び出しの描画
  - サブエージェント詳細パネル描画
  - ページ全体HTMLの構築

### templates/
- 役割: 画面テンプレート資材の配置場所
- 主な内容:
  - `styles.css`: ビューア画面のスタイル定義
  - `scripts.js`: 画面操作(折りたたみ/展開など)のクライアントスクリプト
- 利用箇所:
  - `html_page_renderer.py` の `load_template_text(...)` から読み込まれ、`<style>` / `<script>` としてページHTMLに埋め込まれる

## 責務境界
- `src_view` は「抽出済みデータの表示と配信」を担当
- 生ログからの抽出・整形そのものは `src_parse` 側で担当
