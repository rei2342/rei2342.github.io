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

## 眠っている A8 案件の解放とクッション導線（2026-11-08〜09）

- マスターの A8 参加中 116 件のうち、広告コードがあるのは 3 件だけだった。残り 113 件は「登録媒体URLの不一致」ではなく、広告コード未取得で止まっていた。
- a8mat の構造（管理画面で媒体001〜008を切り替えて実測）: `<案件側ブロック>+<媒体×案件ごとのコード>+<広告主番号×10の36進>+<素材>`。
  **媒体で変わるのは2番目のブロックだけ**。1番目のブロックで媒体を判定してはいけない（11/08 の版はこれを誤っていた）。
- 正本は管理画面の媒体別コード。ログイン済みChromeで `/program/create-link?programId=..&websiteId=001..008` を読み、`python main.py import-a8-codes <json>` で `data/affiliate/a8_console_codes.json` に取り込む（広告リンクはクリックしない）。
- WP で使う案件 = Astra の matched_affiliates ＋ そのWPの公開記事で本人が既に使っている案件。広告コードは必ずそのWPの媒体ID向けのものを使う。
- `python main.py affiliate-harvest` … 自前WPの公開記事のタグを集め、管理画面のコードと2番目のブロックで照合して媒体ずれを出す。
- `python main.py affiliate-audit` … 116 件の内訳・アカウント別のWP経由で使える案件数・媒体ずれ。
- クッション導線: SNS・note には広告リンクを渡さず、同じアカウントのWP記事へ送る（`affiliate.cushion_via_wordpress`）。
- `python main.py wp-draft <draft_id>` … 承認前の疎通テスト。status は常に draft。

## Muse 需要調査 → 悩み解決型の原稿（2026-11-09）

Meta の Muse で集めた「読者の生の悩み」と「AKIRA のストーリーズ書き起こし」を、generate のネタ元として最優先で使う。

1. **調査プロンプトを作る**: ダッシュボード `05 MUSE RESEARCH` でアカウントを選ぶと、そのアカウントの読者層・テーマに合わせた
   Muse 用プロンプト（直近30日の Threads/IG から悩みを CSV で20件）が出る。右上のアイコンでコピー。
   CLI なら `python main.py muse-prompt さくら`（ストーリーズは `--stories`）。
2. **取り込む**: Muse の返した表（CSV / TSV / Markdown表 / JSON）を画面に貼って保存するか、
   `data/muse_inbox/<account_key>__xxx.csv` に置く（サブフォルダ `data/muse_inbox/<account_key>/` でも、表の `account` 列でも可）。
   ファイル名に `stories` を含むものは本人のストーリーズ書き起こしとして扱う。`python main.py muse-ingest` で手動取り込みも可。
   列名は日本語（困っている場面／試してダメだったこと／未解決の疑問 …）でも英語（scene／tried_failed／open_question …）でも読む。
3. **生成**: `generate` は毎回 inbox を取り込み、未使用のシードを1つ（反応の大きい順 → 無ければストーリーズ）選んで使う。
   使ったシードは `data/muse/<account_key>/items.jsonl` で使用済みになる。
   `generate --all --muse-only` で未使用シードがあるアカウントだけ、`--no-muse` でシードを使わずに生成。

**悩み解決型ファネル**（シードの有無にかかわらず全原稿に適用）:
フック（場面・試してダメだったこと・未解決の疑問を読者の言葉で1行目に）→ 共感と原因 → 今日できる手順 → 解決策として案件・有料note・LINE を1〜2個 → CTA。
`pain_hook.hook_line` が X / Threads の1投稿目・WP の導入・note の1段落目に入っていなければ検査 error（生成時は1回だけ自動で作り直す）。

他人の投稿は場面として言い換えて使い、原文の引用・@ハンドル・URL は原稿に載せない（取り込み時に @ハンドルと URL を落とす）。
ストーリーズは本人が話した範囲だけを使い、話していない経歴・数字は足さない。
