# アイキャッチ生成プロンプト（一時データ）

**ここのファイルは公開コンテンツではありません。** 画像制作専用の作業用データです。

- WordPressの本文へ入れない
- SEOタイトル・メタへ入れない
- SNS投稿文へ混ぜない
- 読者から見える場所へ出さない
- 公開処理の payload へ含めない

## いつ消すか

画像の**生成 → WordPressへ反映 → 検証**が全部通ったら、その記事のファイルを削除します。
**失敗した場合は削除しません。** 再実行の対象として残します。

## 作られ方

記事生成ワークフロー（`daily-article-drafter.yml`）が、記事本文・Threads投稿文と
並ぶ**3つ目の成果物**として `workspace/eyecatch-prompts/<記事IDまたはslug>.md` に出します。
手で作るときは `scripts/eyecatch_prompt.py` を使います。

```bash
POST=1003 SLUG=english-meeting-transcription-checklist \
TITLE="英語会議の文字起こしツールを選ぶ前に｜確認する5つのこと" \
LEAD="英語会議の
AI文字起こし" SUB="選ぶ前の5チェック" \
SCENE="Sakura at an office desk with a headset…" \
CATEGORY="AI英語学習" ALT="…" \
python affiliate-research-engine/playbook/scripts/eyecatch_prompt.py
```

## 公開ゲート

次が全部そろうまで、記事を**公開も予約もしません**。

画像生成済み / アップロード済み / featured_media 設定済み / alt 設定済み /
画像内の文字が本文と一致 / 未確認の主張なし / サムネイルで読める /
OGPで崩れない / 既存記事と判別できる / 文字カード型ではない

**仮画像を設定して公開するのは禁止です。** 画像を作れないときは記事を下書きで
止めて、このファイルを残します。文字だけの仮画像を自動生成して公開・予約しません
（`eyecatch_build.py` は既定で反映を止めてあります）。

## いま残っているもの

| ファイル | 記事 | 状態 |
|---|---|---|
| `993.md` | ChatGPTで英語学習を始める手順 | **公開済み。文字カード型のまま＝優先差し替え** |
| `995.md` | AI英会話とオンライン英会話の違い | 下書き（予約を停止） |
| `997.md` | AI翻訳があるのに英語を学ぶ意味 | 下書き（予約を停止） |
| `999.md` | AI発音矯正アプリの選び方 | 下書き（予約を停止） |
| `1001.md` | AI時代に必要な英語力はどこまでか | 下書き（予約を停止） |
| `1003.md` | 英語会議の文字起こしツールを選ぶ前に | 下書き（予約を停止） |

## 差し替えたあとの手順

1. 生成した画像をWordPressのメディアへアップロード（ファイル名は半角英数）
2. 記事の `featured_media` に設定し、`alt` を入れる
3. 上の公開ゲート10項目を確認する
4. 予約を戻す（元の予定日時は `backups/2026-08-09/ai_pause_<記事ID>.json`）
5. **このプロンプトのファイルを削除する**

予約を戻すコマンド:

```bash
python - <<'PY'
import json, requests
pid, day = "995", "2026-08-09"
d = json.load(open(f"affiliate-research-engine/playbook/workspace/"
                   f"backups/{day}/ai_pause_{pid}.json"))
requests.post(f"https://sakura-eigo.com/wp-json/wp/v2/posts/{pid}",
              auth=("rei.00pt2342@gmail.com", WP_APP_PASSWORD),
              json={"status": "future", "date": d["date"]}, timeout=60)
PY
```
