# src_view 責務メモ

このディレクトリは、抽出済みログの読み込み・加工・表示（Web）を担当します。

生ログの抽出・整形そのものは src_parse 側で実施し、src_view は表示と配信に専念します。

## 概要

- エントリポイントは web_app.py（FastAPI）
- 表示対象は主に extracted_main.jsonl（必要に応じて再抽出）
- 画面は次の 3 系統
  - 月カレンダー（/）
  - 日別セッション一覧（/?date=YYYY-MM-DD）
  - セッション詳細（/view?file=...）
- 単体セッション ZIP / 複数セッション ZIP を提供（/download/zip）

## 実行方法と前提

### 依存関係

- fastapi
- uvicorn[standard]

依存バージョンは requirements.txt を参照してください。

### 起動方法（推奨）

プロジェクトルートで実行:

~~~bash
./start_ai_logview.sh
~~~

ポート指定:

~~~bash
./start_ai_logview.sh --port 5001
~~~

### 起動方法（直接）

~~~bash
python3 src_view/web_app.py --host 127.0.0.1 --port 5001
~~~

finder-script を明示指定する場合:

~~~bash
python3 src_view/web_app.py \
  --host 127.0.0.1 \
  --port 5001 \
  --finder-script src_parse/find_debug_logs.sh
~~~

## HTTP エンドポイント

### GET /

- クエリ未指定:
  - 当月のカレンダーを表示
- month=YYYY-MM 指定:
  - 指定月のカレンダーを表示
- date=YYYY-MM-DD 指定:
  - 指定日のセッション一覧を表示
- バリデーション:
  - month の形式不正は 400
  - date の形式不正は 400

### GET /view

- 必須クエリ:
  - file（extracted_main.jsonl のパス）
- 動作:
  - file が extracted_main.jsonl の場合、必要に応じて再抽出を試行
  - ファイルが存在しない場合は 404
  - セッション詳細 HTML を返却
- 主な処理:
  - events 読み込み
  - subAgent エントリ読み込み
  - session_title 抽出
  - block グルーピング
  - HTML 描画

### GET /download/zip

- クエリ:
  - file=...（単体）
  - files=...（複数、繰り返し可）
- 動作:
  - 指定セッションを ZIP 化して返却
  - 有効な入力が 0 件の場合は 400

## 画面機能

### 1. 月カレンダー

- 日ごとの件数とクレジット合計（AIU）を表示
- 0 件の日は非活性（クリック不可）
- 前月/翌月ナビゲーション
- 当日ハイライト
- 更新ボタン（ブラウザ reload）

### 2. 日別セッション一覧

- セッション行に以下を表示
  - タイトル
  - datetime
  - block 数
  - total credits
- 各行で実行できる操作
  - 詳細画面へ遷移
  - 単体 ZIP
- 画面上部の一括操作
  - 全選択チェック
  - 選択件数表示
  - 複数セッション ZIP ダウンロード
- 更新ボタン（ブラウザ reload）

### 3. セッション詳細

- 1 user_message 単位で block を表示
- 各 block に Total Credits を表示
- llm_request のメタ情報を表示
  - model
  - credits
  - in / cached / out tokens
  - cache rate
  - input growth
- agent_response の内容を表示
  - text
  - tool_call（引数折りたたみ）
  - reasoning（折りたたみ）
- runSubagent 呼び出しに対応する詳細パネルを表示
- Attachments（id, filePath）を user message 下部に表示
- 更新ボタン（ブラウザ reload）

## データ処理フロー

### 詳細表示（/view）の流れ

1. file クエリを Path 化
2. 必要なら ensure_extracted_main で再抽出
3. load_events で JSONL 行を読み込み（壊れた行はスキップ）
4. group_blocks でイベント列を表示 block に変換
5. extract_session_title で見出し情報を抽出
6. load_subagent_entries でサブエージェント抽出ログを集約
7. render_page で HTML を生成

### 一覧表示（/?date=...）の流れ

1. 日付指定を受け取る
2. finder_script によりライブ収集
3. collect_session_summaries で件数・メトリクスを集約
4. render_sessions_page で HTML を生成

## メトリクス表示としきい値

### cache rate

- 判定条件（低いほど悪化）
  - <20%: warning
  - <40%: caution
  - <60%: check

### output tokens

- 判定条件（多いほど悪化）
  - >=1000: check
  - >=4000: caution
  - >=8000: warning

### input growth

- 判定条件（増分が大きいほど悪化）
  - >=3000: check
  - >=8000: caution
  - >=20000: warning

注記:
- input growth は主に同一 user_message block 内の連続 llm_request 差分で算出
- block ヘッダにも増分バッジを表示

## サブエージェント（runSubagent）連携

- 各サブファイルについて以下を生成
  - blocks
  - session_title
  - total_credits
  - line_count
- 親セッションの tool_call（runSubagent）にパネルとして紐づけ表示
- subAgent credits は pair 単位・block 単位・session 合計に反映

## 検索モード（live）

- finder_script を subprocess 実行して対象日の候補ディレクトリを収集
- 各ディレクトリから extracted_main.jsonl を準備し、要約を算出
- 収集時にスキップ件数・日付フィルタ件数を info に反映

## エラーハンドリング

- month/date 形式不正は 400
- /view で file 未指定は 400
- /view で file 不在は 404
- /download/zip で file/files 未指定は 400
- extracted 再生成失敗時は ensure_extracted_main が None を返す
- JSONL の壊れた行は load_events 側で無視
- finder_script 実行失敗時は一覧 info に失敗理由を反映

## ファイル別の責務

### web_app.py

- 役割:
  - FastAPI エントリポイント（配線専任）
- 主な責務:
  - ルーティング（/, /view, /download/zip）
  - live 検索の配線
  - レスポンス組み立て
  - CLI 引数処理（host, port, finder-script）

### session_view_service.py

- 役割:
  - 画面向けユースケース組み立て（依存注入の薄い窓口）
- 主な責務:
  - collect_session_summaries の依存束ね
  - subAgent 一覧読み込み呼び出しの窓口

### log_data_io.py

- 役割:
  - ファイル I/O と外部プロセス連携
- 主な責務:
  - JSONL 読み込み
  - extracted_main 再生成判定と実行
  - サブエージェント抽出ログ読み込み
  - セッション一式 ZIP 生成

### session_log_processor.py

- 役割:
  - ログイベントのドメイン処理
- 主な責務:
  - イベント列の block 化
  - session_title 抽出
  - credits 計算
  - セッション日時解析
  - 日付指定セッション一覧の収集・集約

### html_page_renderer.py

- 役割:
  - HTML 文字列生成
- 主な責務:
  - 詳細/一覧/カレンダーの描画
  - メトリクスバッジとしきい値判定
  - tool_call の折りたたみ表示
  - subAgent パネル描画
  - templates 読み込み（LRU キャッシュ）

### templates/

- 役割:
  - UI 資材（CSS/JS）
- 主な内容:
  - styles.css: ビューア全体のスタイルと警告アニメーション
  - scripts.js: 折りたたみ制御、subAgent パネル制御

## 補足（運用メモ）

- 抽出結果が古い場合、表示時に再生成が走ることがあります
- セッション一覧の件数は source=live として表示されます
- ZIP にはセッション本体ログと関連するサブエージェント抽出ログが含まれます
