# Changelog

このファイルは agentdebuglog_parsetool のバージョン履歴と変更概要を管理します。

## v1.1

- agent_response の response が途中で切れた JSON 文字列でも、末尾の文字列終端と括弧を補完して再パースできるように改善
- 上記の補完ロジックを title 抽出時にも適用し、不完全な title ログでも text part を拾いやすく改善
- アプリのバージョン管理をルートの VERSION ファイルへ集約
- セッション一覧画面とセッション詳細画面のヘッダにアプリ version を表示
- session の filtered 判定について、パスと理由を index 生成ログに出力し、後から確認しやすく改善

## v1.0

- 初期版
- JSONL の主要イベント抽出、セッション一覧表示、詳細表示、ZIP ダウンロードを提供