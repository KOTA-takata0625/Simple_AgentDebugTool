# agentdebuglog_parsetool

AI実行ログ（JSONL）を日付単位で整理し、ブラウザで閲覧するためのツールです。

## セットアップ

**前提環境**: Linux / Python 3.8 以上 / Agent Debug Logs 有効

```bash
cd /path/to/agentdebuglog_parsetool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

このツールを使用するには、VS Code で Agent Debug Logs 機能を有効にする必要があります。

`settings.json` に以下を追加してください:

```json
"github.copilot.chat.agentDebugLog.fileLogging.enabled": true
```

有効化後、以下のいずれかの方法でAgent Debug Logsの機能を使用できます。このツールではその機能の生ログを加工した上で表示します。

- Chat ビューの `...` メニュー → **Show Agent Debug Logs**
- コマンドパレット（`Ctrl+Shift+P`）→ **Developer: Open Agent Debug Logs**

詳細: [VS Code 設定ドキュメント](https://code.visualstudio.com/docs/agents/agent-troubleshooting/chat-debug-view)

---

## 起動と画面導線

### 起動

```bash
./start_ai_logview.sh
```

```bash
./start_ai_logview.sh -h
Usage: ./start_ai_logview.sh [--host HOST] [--port PORT]
```

### 起動時の出力例

```
$ ./start_ai_logview.sh
Start app: http://127.0.0.1:5001/
INFO:     Started server process [<PID>]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:5001 (Press CTRL+C to quit)
```

ブラウザで `http://127.0.0.1:5001/` にアクセスしてください。

### セキュリティ運用ガイド

- 既定は `--host 127.0.0.1`（ローカルホストのみ）で運用してください。
- `--host 0.0.0.0` で公開する場合は、Linux Firewall や Nginx 等を用いてアクセス元を制限することを推奨します。
- 共有用途でも、可能なら IP 制限と認証を併用してください。

## 詳細ドキュメント

各モジュールの処理詳細は以下を参照してください。

- [`src_parse/README.md`](src_parse/README.md) — ログのパース処理
- [`src_view/README.md`](src_view/README.md) — ビュー・Web アプリ処理

---