# COMMAND CENTER

Astra が出力した `config/accounts_master.json` だけを情報源にして、全媒体（WordPress / note / X / Threads / Instagram）の生成・配信・バズ追撃・収益監視を回すシステム。アカウント名や媒体構成はコードに書いていない。

## 起動

```bash
cd command-center
pip install -r requirements.txt && playwright install chromium
python main.py env-template          # マスターからアカウント別の config/.env を生成
# config/.env に各媒体のキーを入れる（生成は既定で Claude CLI＝サブスク枠。API キーは任意）
streamlit run dashboard/app.py       # または python main.py dashboard
```

## 流れ

1. **Astra の結果を入れる**: ダッシュボード 01 でJSONをアップロード → 差分を確認 → ワンクリックで反映（旧版は `config/history/` に退避）。CLI なら `python main.py import new.json --merge`
2. **実データで校正**: 02 でURLを確認して「クロールして同期」。WP REST / note 公開API / X・Threads・IG の公式API（トークンがない場合は公開ページ）から直近投稿を取り、文体を実測して `data/calibration/` に保存する
3. **生成**: 04 でテーマを入れて一括生成。そのアカウントが持っている媒体分だけ作る（AKIRA: note/X/Threads/IG、カオル: X のみ…）。生成物は検査（URLの捏造・別媒体用の広告コードの流用・PR表記の抜け・文字数・裏付けのない体験談）を通す
4. **承認 → 配信**: 承認した媒体だけ配信できる。`mode.dry_run: true`（既定）の間は外部に送らず、`data/outbox/` に保存するだけ
5. **バズ追撃**: `python main.py buzz --loop --live`。閾値（`settings.yaml buzz.thresholds`）を超えた投稿に、その投稿元の下書きの `buzz_followup` をリプライする。下書きがない投稿には自分の note/WP の URL をリプライする
6. **収益**: A8 / もしも / Amazon / note の管理画面から落とした CSV を 03 で取り込む（管理画面のスクレイピングはしない）

## 生成エンジン（settings.yaml `llm.backends`）

上から順に試し、鍵や CLI が無いものは飛ばし、残高不足・認証失敗などで落ちたら次へ進む。モデルが拒否したときは次へ回さず止める。

1. `claude_cli` … ローカルの Claude Code CLI を `claude -p --output-format json --json-schema` で呼ぶ。ログイン中のサブスク枠で動き、API クレジットを使わない。CLI は PATH → `~/.claude/local` → Claude デスクトップ同梱の順に探す（`llm.claude_cli_path` で固定も可）。子プロセスには `ANTHROPIC_*` を渡さない
2. `anthropic_api` … `ANTHROPIC_API_KEY`（従量課金）
3. `openai` … `OPENAI_API_KEY` があるとき
4. `gemini` … `GEMINI_API_KEY` があるとき

下書きの `llm_backend` に、どれで作ったかが残る。

## X / Instagram のログイン壁

API トークンが無いときは、次の順で取る（`crawl` の結果の `tried` に経路ごとの件数が残る）。

1. 専用ブラウザプロファイル … `python main.py browser-login x|instagram` で開いたウィンドウに人が一度だけログインする。以後 `crawl` はそのプロファイル（`data/browser_profiles/`）で読む。パスワードは保存しない。Chrome 本体のプロファイルや Cookie は読まない
2. ローカルの投稿ログ … `data/local_posts/<internal_key>/<platform>.jsonl`（`python main.py import-posts <account> <platform> <file>` で取り込む）と `settings.crawl.local_log_globs`。所有者を指定しないログは url / handle で本人の投稿だけに絞る
3. Nitter 系 RSS（X のみ。`settings.crawl.nitter_instances`。多くは停止中）
4. 公開ページ

## discover 候補の確定

人が確定した候補は `accounts_master.json` の `candidate_notes` に置く（`keep` = 自分の資産として保持、`ignore` = 除外。`alias_of` は正式アカウント）。`discover` はこれを読んで `resolved_candidates` に分け、未確定の候補だけを `unmatched_candidates` に出す。Astra のマスターを replace で取り込んでも `candidate_notes` は残る。

## 書き込みを有効にするには（3つすべてが必要）

| 条件 | 場所 |
|---|---|
| 媒体ごとの書き込み許可 | ダッシュボード 01 の「書込許可」、または `python main.py enable さくら x` |
| 認証情報 | `config/.env` の `KEY__INTERNAL_KEY`（例 `X_API_KEY__SAKURA_EIGO30`） |
| LIVE モード | `settings.yaml mode.dry_run: false` ＋ 配信時に LIVE を指定 |

マスターの `automation_contract.publish_or_send_authorized` は `false`。Astra の調査結果を書き込み許可としては扱わず、許可は必ず人が出す。

## アフィリンクの扱い

- 登録媒体URLと配信先URLが一致する案件だけを使う。A8 は `registered_media`、もしもは `settings.affiliate.moshimo_media_map`（未記入のため現状は使わない）で照合する
- `auto_publish_allowed: false` の案件は自動リプライに入れない。人が確認した案件は `auto_publish_overrides` に足す
- アフィリンクを入れるときは `PR` 表記を必ず付ける（ステマ規制）

## 構成

```
config/   accounts_master.json  settings.yaml  .env(.example)
core/     account_loader  account_crawler  content_generator  guards  llm  drafts  revenue  discovery  image_renderer
publishers/ wp_publisher  note_publisher(Playwright・下書きのみ)  x_publisher(API v2)  meta_publisher(Threads/IG)
automation/ buzz_hunter
dashboard/  app.py
main.py   tests/test_pipeline.py（オフラインのE2E。python tests/test_pipeline.py）
```
