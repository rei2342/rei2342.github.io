# MCP セットアップ（第7章）

`mcp.example.json` をベースに、Claude Code の MCP 設定へ登録する。

## 手順
1. `mcp.example.json` を見て、使うサーバーだけを選ぶ。
2. `{{ }}` のAPIキーを取得して埋める（環境変数経由が安全）。
3. Claude Code に登録する。いちばん簡単なのは CLI:
   ```bash
   claude mcp add firecrawl -- npx -y firecrawl-mcp
   ```
   または プロジェクト直下に `.mcp.json` を置く（チームで共有する場合）。
4. `claude mcp list` で接続を確認する。

## 4つのMCPと取得先

| MCP | 用途 | 必要なもの |
|-----|------|-----------|
| Firecrawl | 競合LPをMarkdown化（テク27） | Firecrawl APIキー |
| Supadata | 動画トランスクリプト（テク28） | Supadata APIキー |
| Memory | 永続記憶（テク29） | なし（ローカルJSON） |
| Notion/Sheets | 案件管理・収益データ（テク30/テク34） | Notion Integration Token と DB共有 |
| Slack（任意） | Routinesの通知 | Slack Bot Token |

## 注意（重要）
- **パッケージ名とインストール方法は変わりやすい**。`mcp.example.json` のコマンドは雛形なので、
  各MCPの公式README（GitHub / 公式サイト）で最新の正確なインストール名を必ず確認すること。
- **APIキーはリポジトリにコミットしない**。`.mcp.json` に実キーを書くなら `.gitignore` に追加するか、
  環境変数で渡す。このリポジトリの `.gitignore` で `playbook/mcp/.mcp.json` は除外済み。
- Memory MCP の保存先は `playbook/workspace/memory.json`。`CLAUDE.md`（後述）と役割が重なるので、
  まずは `CLAUDE.md` だけで運用を始め、規模が増えたら Memory MCP を足すのがおすすめ。
