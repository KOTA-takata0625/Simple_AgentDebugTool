# agentdebuglog_parsetool

AI実行ログ(JSONL)を日付単位で整理し、ブラウザで閲覧するためのツールです。

## クイックスタート

前提:

- Linux
- Python 3.8+

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

## 詳細ドキュメント

処理説明は以下を参照してください。

- `src_parse/README.md`
- `src_view/README.md`
