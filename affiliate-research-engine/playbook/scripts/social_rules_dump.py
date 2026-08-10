#!/usr/bin/env python3
"""
social_rules_dump.py
X と Threads の**今のルールを、実ファイルから抜き出して**1枚にする。読むだけ。

書き写すと必ずズレるので、プロンプトは原本から切り出して貼る。

  python social_rules_dump.py
出力: workspace/social/SOCIAL_RULES_CURRENT.md
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
JST = timezone(timedelta(hours=9))
OUT = ROOT / "workspace/social"
WF = REPO / ".github/workflows"


def slice_between(path, start, end):
    s = Path(path).read_text(encoding="utf-8")
    i = s.index(start)
    j = s.index(end, i)
    return s[i:j].rstrip()


def main():
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    x_poster = slice_between(WF / "x-poster.yml",
                             "          # ── 頻度パラメータ",
                             "          import anthropic, tweepy")
    x_promo_rules = slice_between(ROOT / "scripts/x_promo.py",
                                  'RULES = """', '\n\n\ndef get_post')
    th_rules = slice_between(ROOT / "scripts/threads_builder.py",
                             'RULES = """', '\n\n\ndef get_post')
    th_review = slice_between(ROOT / "scripts/threads_builder.py",
                              "def review(t1, t2, title):", "\ndef main():")
    drafter = slice_between(WF / "daily-article-drafter.yml",
                            '          prompt = (\n              "あなたは田中さくら',
                            "          ai = anthropic.Anthropic")
    cannon = slice_between(WF / "threads-note-cannon.yml",
                           '          claude -p "田中さくらのnote原稿',
                           "            --allowedTools")

    L = f"""# X・Threads の今の生成ルール（{stamp}）

**原本から切り出して貼っている。** 書き写していないので、ここと実ファイルは同じ。
認証情報の値は出さない。**どこに置いてあるか**だけ書く。

---

## 0. 一覧

| 経路 | プラットフォーム | 実行 | 生成 | 投稿 | 実ファイル |
|---|---|---|---|---|---|
| 自動つぶやき | X | 1日5スロット・cron | claude-haiku-4-5 | **自動で投稿する** | `.github/workflows/x-poster.yml` |
| 記事の告知 | X | 手動 | claude-opus-4-8 | `DRY_RUN=false` のときだけ | `scripts/x_promo.py` / `.github/workflows/x-promo.yml` |
| 記事と同時 | Threads | 3日ごと cron | claude-haiku-4-5 | **しない**（メモを作るだけ）| `.github/workflows/daily-article-drafter.yml` |
| 作り直し | Threads | 手動 | claude-opus-4-8 | **しない** | `scripts/threads_builder.py` / `.github/workflows/threads-builder.yml` |
| note＋Threads | Threads | 手動（定期は停止）| claude -p | **しない** | `.github/workflows/threads-note-cannon.yml` |

**Threads へ自動投稿する口はどこにも無い。** Threads API は測定
（`scripts/threads_insights.py`）にしか使っていない。投稿は人が手で貼る。

## 認証情報の置き場（値は出さない）

| 名前 | 用途 | 設定 |
|---|---|---|
| `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | X投稿 | GitHub Secrets・設定あり |
| `REI_AFFSAKU` | 文面生成（Anthropic）| GitHub Secrets・設定あり |
| `WP_APP_PASSWORD` | 記事本文の取得・メモの下書き作成 | GitHub Secrets・設定あり |
| Threads の投稿用トークン | — | **無い。だから自動投稿できない** |

---

# 1. X — 自動つぶやき（`x-poster.yml`）

## 頻度・時刻・重複防止（原文）

```python
{x_poster}
```

### 要点

| 項目 | 値 |
|---|---|
| 予約時刻（JST）| 07:10 / 12:40 / 19:30 / 22:50 / 00:20 の5スロット |
| 実際に投稿する確率 | `POST_PROB = 0.55`（各スロット）|
| 最小間隔 | `GAP_MIN_H = 64` 時間（約2.7日）|
| 次回許可 | 前回から 64〜80 時間後のランダム |
| 取りこぼし対策 | `next_allowed` を20時間過ぎたら確率を無視して投稿 |
| 重複防止 | **文面の重複チェックは無い。** 見ているのは時刻だけ |
| 記事との紐付け | **無い。** 40%の確率で最新ドラフトのタイトルを「着想」に使うだけ |
| 失敗時の再試行 | **無い。** 例外が出たらそのスロットは落ちる |
| 状態の保存 | `workspace/x_state.json` に `last_post` / `next_allowed` / `last_text` |
| 文字数 | プロンプトで「最長90字」、コードで `LIMIT = 128` に丸める |
| 改行 | 「全体3〜4行」「2ブロック構成（前半→空行→後半）」 |
| 絵文字 | 2〜3個（2個寄り）。直前の半角スペースをコードで削る |
| ハッシュタグ・URL | **禁止**（プロンプトに明記）|

### 直書きの文言

- ペルソナ「田中さくら（27歳・営業事務・東京）…ワーホリに向けて」が
  **ワークフローに直書き**されている（CLAUDE.md の 2026-08-07 改訂を反映していない）
- 「実測で伸びた投稿」4本と「伸びなかった投稿」3本が本文ごと直書き
- テーマ候補8個・モード11個・長さ4種・絵文字候補30個も直書き

### 既知の壊れ

`x-poster.yml` の末尾に、**代入されない変数を読む行**がある。

```python
tail = tweet_full[len(tweet):len(tweet) + 2] if (tweet_full := (msg.content[0].text)) else ""
```

`tail` はどこにも使われていない。128字を超えたときだけ通る枝なので
普段は落ちないが、通ると何もしないコードが1行走るだけになる。

---

# 2. X — 記事の告知（`scripts/x_promo.py`）

## プロンプト（原文）

```text
{x_promo_rules}
```

### 要点

| 項目 | 値 |
|---|---|
| 起動 | `x-promo.yml` の手動実行のみ。`article_id` を渡す |
| 既定 | `dry_run: true`（**既定では投稿しない**）|
| 記事の状態 | `publish` でなければ中止する |
| 形 | 1投稿目＝本文 / 2投稿目（返信）＝URLだけ |
| URL | `?utm_source=x` を付ける。本文中のURLは正規表現で落とす |
| 文字数 | 60〜90字（プロンプト。**コードの上限チェックは無い**）|
| ハッシュタグ | 禁止 |
| 重複防止 | **無い** |
| 失敗時の再試行 | **無い** |
| 記録 | `workspace/x_promo/promo_<記事ID>.md` と `x_state.json` |

---

# 3. Threads — 記事と同時（`daily-article-drafter.yml`）

3日ごと 05:30 JST。記事をWordPressへ下書き投稿したあと、同じ本文から
Threadsの2連を作る。**投稿はしない。** ファイルとWordPressのメモを作る。

## プロンプト（原文）

```python
{drafter}
```

### 要点

| 項目 | 値 |
|---|---|
| モデル | `claude-haiku-4-5-20251001` / `max_tokens=800` |
| 形 | 1投稿目＝フック（リンクなし）/ 2投稿目＝中身＋末尾にURL |
| URL | 直前に作った記事の slug から組み立て、`?utm_source=threads` を付ける |
| 文字数 | 「300字以内目安」。1行20字前後、28字超は割る |
| 句点 | **使わない**（改行が句点の代わり）|
| 絵文字 | 2個まで |
| ハッシュタグ | 禁止 |
| 重複防止 | **無い**（同じ記事から何度でも作れる）|
| 失敗時の再試行 | **無い**（`threads_builder.py` にはある）|
| 保存先 | `workspace/threads/<日付>.md` ＋ WordPress の `【Threads用】<日付>` 下書き |

### 出力の後処理（コード）

- `——` を `、` に置換
- `https?://\\S+` を全部落とす（`example.com` を書いてきたため）
- 行頭が `▶` の行と、`無料体験` などで終わる行を落とす（CTAの書き写し対策）
- 絵文字の直前の半角スペースを落とす

---

# 4. Threads — 作り直し（`scripts/threads_builder.py`）

## プロンプト（原文）

```text
{th_rules}
```

## 出す前の検査（原文）

**この経路にだけ、合格しない原稿を外に出さない仕組みがある。**
落ちたら理由を渡して最大3回書き直す。

```python
{th_review}
```

### 既知の壊れ

`threads_builder.py` は、結果をファイルへ書くところで
**定義されていない変数 `kuten` を読む**。

```python
f"句点の混入: {{kuten}}個\\n", encoding="utf-8")
```

`kuten` はどこにも代入されていないので、生成が成功しても
**ファイル書き出しで `NameError` になって落ちる**。
`workspace/threads/built_*.md` が4本しか無く、いちばん新しいものが
2026-08-07で止まっているのは、これが理由の可能性が高い。

---

# 5. Threads — note とセット（`threads-note-cannon.yml`）

定期実行は 2026-08-04 に停止済み。手動のみ。

## プロンプト（原文）

```text
{cannon}
```

### ここだけ古い

このプロンプトは **2026-08-01 の勝ち型**を指している。
`daily-article-drafter.yml` と `threads_builder.py` は 2026-08-06〜07 に
作り直されたが、こちらは追随していない。食い違うのは次の3点。

| 項目 | cannon（古い）| 他の2つ（今）|
|---|---|---|
| 形 | 1投稿の塊 | スレッド2連 |
| 締め | 「続きはnoteに書いた」 | 「私が何を見て決めたかはブログに書いた」 |
| 対比構文 | **推奨**（『〜じゃなかった』で止める）| **禁止** |

---

# 6. 3経路の食い違い（同じことを3か所に書いている）

Threadsのルールは `daily-article-drafter.yml` と `threads_builder.py` に
**ほぼ同じ文章が二重に**書かれている。cannon は3つ目の別物。

| ルール | drafter | builder | cannon |
|---|---|---|---|
| スレッド2連 | あり | あり | **なし（1投稿）** |
| お手本の全文 | あり | あり | なし |
| 句点を使わない | あり | あり | **なし（句点で区切ると書いてある）** |
| 対比構文の禁止 | あり | あり | **逆（推奨）** |
| 出す前の検査 | **なし** | あり（3回書き直し）| なし |
| アイキャッチの項目 | あり | なし | あり（旧ちびキャラ様式）|

**片方だけ直すと、もう片方が古いまま残る。** 実際に cannon が取り残されている。
"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "SOCIAL_RULES_CURRENT.md").write_text(L, encoding="utf-8")
    print(f"→ {OUT}/SOCIAL_RULES_CURRENT.md ({len(L)}字)")


if __name__ == "__main__":
    main()
