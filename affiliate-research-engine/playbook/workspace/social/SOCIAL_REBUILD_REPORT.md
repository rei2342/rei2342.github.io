# SNS運用の入れ替え 完了報告（2026-08-09）

**投稿は1件もしていない。** 投稿済みの14件にも触れていない。

---

## 0. 先に、指示書の数え方について1点

指示書は「未投稿35件（X-PROMO 4 / TH-FILE 21 / TH-MEMO 10）」としていますが、
**棚卸しの実数は TH-FILE が20件**で、未投稿は34件です。
`35 + 14 = 49` になり、全体の48件と合いません。正しくは次のとおりです。

| 区分 | 件数 |
|---|---|
| X-PROMO | 4 |
| TH-FILE | **20** |
| TH-MEMO | 10 |
| **未投稿 合計** | **34** |
| 投稿済み（X 1 / Threads 13） | 14 |
| **全体** | **48** |

TH-FILE の内訳: 2026-08-02(1) / 08-04(3) / 08-07(2) / 08-08(2) /
SAMPLE(1) / built_315(3) / built_521(3) / built_526(3) / built_546(2) = 20。
以降の検算はすべて **34** で出しています。

---

## 1. 正本を1つにした（A）

`config/social/sakura-social-v1.yaml`（status: approved）。
人物・事実・文体・禁止・素材の分け方・X仕様・Threads仕様・状態遷移・
公開条件・段階解放・頻度・置き場を、ここだけに書いています。

`scripts/social_spec.py` がこれを読んでプロンプトへ変換します。
**アダプターにも直書きはありません**（テストで検査）。

## 2. 生成経路を作り直した（B）

| 前 | 後 |
|---|---|
| `x-poster.yml` がランダムテーマで生成して即投稿 | **承認済み在庫を1日1件だけ投稿**。生成しない |
| `x_promo.py` が本文＋URLだけの返信 | 廃止。**URLは同じ投稿の末尾** |
| Threadsが3経路（drafter / builder / cannon） | **1経路**（`social_generate.py`） |
| drafter が下書き段階でSNS文とWPメモを作る | **記事が publish になってから**作る。メモは作らない |
| `threads_builder.py` の未定義 `kuten` | ファイルごと廃止 |

削除: `threads-note-cannon.yml` / `threads-builder.yml` / `x-promo.yml` /
`scripts/threads_builder.py` / `scripts/x_promo.py`
新設: `social-generate.yml`（生成のみ）、`x-poster.yml`（投稿のみ）

## 3. 共通ゲート（C）

`scripts/social_gate.py`。記事側の `quality_rules.unverified_self_facts()` を
**そのまま呼びます**。SNSは主語を落とすので、印が無くても落とすものを
仕様の `persona.leak_patterns` から足しています。

| ゲート | 落とすもの |
|---|---|
| `article_published` | 記事が publish でない / modified_gmt が無い |
| `article_unchanged` | 生成時と投稿時で記事が変わっている |
| `fact_gate` | 未確認の一人称の事実・心理・年齢・点数・金額・期間・回数・台詞 |
| `broken_output` | example.com / （記事URLを貼る）/ `===THREADS_2===` |
| `style_gate` | URLだけの投稿・空・行数・空行・絵文字の数・ハッシュタグ・強制の「↓」 |
| `length_gate` | X 70〜140字（URL込み280以内）/ Threads 120〜260・160〜400 |
| `link_gate` | URLの位置・utm・記事URLとの一致・下書きURL・URLが複数 |
| `subset_gate` | 記事本文に無い数字 |
| `duplicate_gate` | 過去180日と完全一致・近似（3-gram Jaccard 0.85） |
| `cross_platform_gate` | XとThreadsが同じ文 |

**句点は落としません。** 短行の連打と定型フックは警告だけにしました。
絵文字は0個で通ります。

## 4. 在庫と履歴（D）

```
workspace/social/stock/x/<記事ID>-<変種>.yaml
workspace/social/stock/threads/<記事ID>-<変種>.yaml
workspace/social/history/x.jsonl
workspace/social/history/threads.jsonl
workspace/social/archive/<日付>/
```

状態は `generated → gated → awaiting_approval → approved → scheduled → posted`。
**決められた遷移以外は例外で止まります**（テストで確認）。

## 5. 承認と投稿（E）

- `social_post.py` は `state=approved` 以外を投稿しません
- 投稿の**直前にもう一度ゲート**を通します（承認後に記事が変わることがあるため）
- 二重投稿の鍵は `platform + article_id + content_hash`
- 失敗したら在庫を `stale` にして理由を残し、**作り直しも即投稿もしません**
- Threadsは投稿用トークンが無いので `--mark-posted` で手動記録

## 6. 試作5記事（F）

`workspace/social/review/REVIEW_2026-08-09.md` に、記事ごとの
X案・Threads案・使った素材・ゲート結果を並べています。
**投稿していません。全件 awaiting_approval で止まっています。**

| 記事 | X | Threads | 使った素材（X / Threads） |
|---|---|---|---|
| 521 TOEICリスニング | 189字 | 440字 | one_check / unique_artifact |
| 546 オンライン英会話 | 198字 | 425字 | 同上 |
| 526 費用と時間 | 180字 | 400字 | 同上 |
| 23 ワーホリ貯金 | 347字 | 606字 | 同上 |
| 310 無料アプリ | 180字 | 375字 | 同上 |

※ 字数はURLを含む在庫全体の長さです。ゲートが見る本文の長さは
X 70〜140、Threads 120〜260／160〜400 の範囲に収まっています。

**本文はAPIではなくセッション側で書きました。**
`social_generate.py` には `--source wp`（Anthropic）と
`--source local --drafts`（用意した原稿）の2経路があり、
**ゲート・在庫・状態遷移はどちらも同じもの**を通ります。
開発環境から sakura-eigo.com と Anthropic API へ出られないため、
今回は後者を使いました。API経路は実装済みで、まだ動かしていません。

## 7. テスト（G）

`scripts/test_social_spec.py`。**失敗0件。**

落とすことを確認したもの: 架空の年齢／点数／金額／期間、記事に無い数字、
`（記事URLを貼る）`、`===THREADS_2===`、example.com、下書きURL、
URLなし、utmなし、URLだけの投稿、記事が下書き、記事が改稿された、
同一本文、XとThreadsが同文、矢印で終わる1投稿目。

通すことを確認したもの: 句点のある自然なThreads文、絵文字0個、
正しいX投稿、XとThreadsが別文。

## 8. 検算（27）

| 項目 | 期待 | 実測 |
|---|---|---|
| 旧未投稿 = アーカイブ + 運用在庫 | 34 = 34 + 0 | **34 = 34 + 0** |
| 投稿済み | X 1 + Threads 13 = 14 | **14（1件も触っていない）** |
| 新規試作 | X 5 + Threads 5セット | **X 5 / Threads 5** |
| 5経路の直書きプロンプト残存 | 0 | **0**（3経路は削除、2経路は正本を読む） |
| WordPressメモの新規生成 | 0 | **0**（drafter から削除） |
| 投稿実行 | 0 | **0** |
| ゲート失敗（本番の在庫） | 0 | **0** |
| 意図的なNGテスト | 全部落ちる | **全部落ちた** |

## 9. やらなかったこと（H）

- 投稿済み14件を消していません。Threadsの13件は**冒頭40字しか取れない**ので、
  指示書の8件は「全文が取れたあとの優先確認対象」として残しています
- 試作5記事を投稿していません
- 未確認の体験を一般論へ言い換えて温存していません（**丸ごと外しました**）
- 古いストックを部分修正して運用へ戻していません
- Threadsの投稿用トークンを追加していません
- 表示回数だけで文体を固定していません（実測例の直書きは全部消しました）

## 10. 残っている宿題

1. **Threads投稿済み13件の全文**。APIでは取れません。Threadsの管理画面か
   データエクスポートから取れたら、指示書の8件を先に見ます
2. **WordPressの【Threads用】メモ 5件**（547・584・618・640・641）。
   リポジトリ側の在庫からは外しましたが、**サイト上の下書きは消していません**。
   消すかどうかは指示をお待ちします
3. **`daily-article-drafter.yml` のInstagramキャプション**に、
   旧ペルソナ「27歳・営業事務・東京」が直書きで残っています。
   今回の対象がXとThreadsだったので触っていません
4. **API経路の初回実行**。`social-generate.yml` はまだ動かしていません
   （動かすと実際に生成されるので、5記事の承認後が安全です）

## 11. 次にやること

```bash
# 1. 5記事を見る
workspace/social/review/REVIEW_2026-08-09.md

# 2. よければ承認する（1件ずつ）
python scripts/social_approve.py --approve X-521-a
python scripts/social_approve.py --reject TH-521-a --reason "記事の内容と違う"

# 3. Xへ出す（1日1件・承認済みだけ）
python scripts/social_post.py --platform x            # 予定を見るだけ
python scripts/social_post.py --platform x --approve  # 実際に出す

# 4. Threadsは手で貼ってから記録する
python scripts/social_post.py --mark-posted TH-521-a --posted-id 18xxxxxxxx
```

**承認するまで、何も世に出ません。**
