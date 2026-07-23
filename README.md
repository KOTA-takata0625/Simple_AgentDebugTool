# agentdebuglog_parsetool

AI実行ログ(JSONL)を日付単位で整理し、ブラウザで閲覧するためのツールです。

## クイックスタート

前提:

- Linux
- Python 3.8+

## Agent Debug Logs機能の有効化

このツールを使用するには、VS Codeで Agent Debug Logs機能を有効にする必要があります。

USER Setting (`settings.json`) に以下を追加してください:

```json
"github.copilot.chat.agentDebugLog.fileLogging.enabled": true
```

機能が有効になっている場合は、以下の方法で Agent Debug Logs を表示できます：

- Chat ビューの省略記号メニュー（...）から "Show Agent Debug Logs" を選択
- コマンドパレット（Ctrl+Shift+P）から "Developer: Open Agent Debug Logs" を実行

詳細は [VS Code 設定ドキュメント](https://code.visualstudio.com/docs/agents/agent-troubleshooting/chat-debug-view) を参照してください。

## セットアップ

セットアップ:

```bash
cd /path/to/agentdebuglog_parsetool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

起動:

```bash
./start_ai_logview.sh --date YYYY-MM-DD
```

補足:

- 引数省略時は当日の日付を使用します。
- `--host` / `--port` / `--python-bin` を指定可能です。
- `start_ai_logview.sh` 内の `WORKSPACE_STORAGE_DIR` は環境に合わせて調整してください。

ヘルプ:

```bash
./start_ai_logview.sh --help
```

## 出力例

正常に起動した場合、以下のような出力が表示されます:

```
$ ./start_ai_logview.sh --port <PORT_NUMBER>
[1/2] Build sessions index for date: <YYYY-MM-DD>
index written: <PATH_TO_WORKSPACE>/agentdebuglog_parsetool/data/sessions_index.json
<NUMBER> sessions
filtered: <PATH_TO_FILTERED_SESSION>/extracted_main.jsonl | date mismatch (<FILTERED_DATE> != <TARGET_DATE>)
[2/2] Start app
起動: http://127.0.0.1:<PORT_NUMBER>/
INFO:     Started server process [<PID>]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:<PORT_NUMBER> (Press CTRL+C to quit)
```

ブラウザで `http://127.0.0.1:<PORT_NUMBER>/` にアクセスして、ログを閲覧できます。

画面導線:

- `/` は日付選択ページです（直近30日を表示）。
- 日付ごとにセッション件数を表示します（例: `3件`）。
- 日付を選択すると `/?date=YYYY-MM-DD` へ遷移し、その日のセッション一覧を表示します。
- セッション一覧のヘッダにある「日付選択へ」から `/` に戻れます。

補足:

- `start_ai_logview.sh` で起動した場合、指定日と同じ日付は index データを使用します。
- それ以外の日付へ遷移した場合は live 収集で一覧を生成します。

## 詳細ドキュメント

処理説明は以下を参照してください。

- `src_parse/README.md`
- `src_view/README.md`

## バージョン管理

アプリのバージョンはルートの VERSION ファイルで管理します。

- 形式は X.Y 固定です。
- Y は小数点第一位のマイナー番号です。
- 例: 1.0, 1.1, 2.0

この値はアプリ画面のヘッダにも表示されます。
変更概要はルートの CHANGELOG.md で管理します。