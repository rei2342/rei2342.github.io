# 生成手順（文字カード型20本の差し替え・2026-08-09 19:37:39 JST）

さくら（sakura-eigo.com）のアイキャッチ用に、**文字なしのマスター画像を20枚**作る。
文字はこちらで後から合成する。**画像の中に文字を描かない。**

## 手順

1. **参照画像と、その記事のプロンプトを同時に入力する**
   （`references/` の指定ファイルと `prompts/<記事ID>.md` のプロンプト）
2. **1記事につき、文字なしマスターを1枚生成する**
3. **1920×1080 の PNG で保存する**（16:9）
4. **ファイル名を `<記事ID>.png` にする**（例 `546.png`）
5. **20枚を `masters/` フォルダにまとめて返す**
6. **文字・数字・ロゴが出た画像は返さない。** 作り直す
7. **人物ありの画像は、521と同一人物に見えるか確認する。**
   別人に見えたら作り直す
8. **左半分に重要な人物・小物を置かない。**
   あとから日本語を載せるので、左は静かに空ける

## 2回に分ける

品質を確かめやすいよう、**batch_1 を先に返してほしい**。

| 束 | 記事ID |
|---|---|
| batch_1 | 546 526 521 304 301 294 235 149 137 23 |
| batch_2 | 310 292 283 282 281 150 117 33 32 28 |

batch_1 を見て画風が合っていることを確かめてから batch_2 に入る。

## 20枚の一覧

| 記事ID | 束 | 人物 | プロンプト | 渡す参照 |
|---|---|---|---|---|
| 546 | 1 | あり | `prompts/546.md` | 521.jpg 273.jpg 297.jpg |
| 526 | 1 | なし | `prompts/526.md` | 297.jpg |
| 521 | 1 | なし | `prompts/521.md` | 297.jpg |
| 304 | 1 | なし | `prompts/304.md` | 297.jpg |
| 301 | 1 | あり | `prompts/301.md` | 521.jpg 273.jpg 297.jpg |
| 294 | 1 | あり | `prompts/294.md` | 521.jpg 273.jpg 297.jpg |
| 235 | 1 | なし | `prompts/235.md` | 297.jpg |
| 149 | 1 | なし | `prompts/149.md` | 297.jpg |
| 137 | 1 | なし | `prompts/137.md` | 297.jpg |
| 23 | 1 | なし | `prompts/23.md` | 297.jpg |
| 310 | 2 | なし | `prompts/310.md` | 297.jpg |
| 292 | 2 | あり | `prompts/292.md` | 521.jpg 273.jpg 297.jpg |
| 283 | 2 | なし | `prompts/283.md` | 297.jpg |
| 282 | 2 | あり | `prompts/282.md` | 521.jpg 273.jpg 297.jpg |
| 281 | 2 | なし | `prompts/281.md` | 297.jpg |
| 150 | 2 | あり | `prompts/150.md` | 521.jpg 273.jpg 297.jpg |
| 117 | 2 | あり | `prompts/117.md` | 521.jpg 273.jpg 297.jpg |
| 33 | 2 | あり | `prompts/33.md` | 521.jpg 273.jpg 297.jpg |
| 32 | 2 | なし | `prompts/32.md` | 297.jpg |
| 28 | 2 | あり | `prompts/28.md` | 521.jpg 273.jpg 297.jpg |

## 参照画像の使い分け（3枚を均等に混ぜない）

| 優先 | ファイル | 採る | 採らない |
|---|---|---|---|
| 1 | `references/521.jpg` | **顔・年齢感・頭身** | まとめ髪・電車の場面 |
| 2 | `references/273.jpg` | 長い茶髪・桜クリップ | 顔の角度 |
| 3 | `references/297.jpg` | 水彩の塗り・光・空気感 | **顔・大きな目・ちび頭身・ピンクのパーカー** |

**人物なしの記事（526 521 304 235 149 137 23 310 283 281 32）には 521 と 273 を渡さない。**

## 場面の使い回しをしない

20本すべてで場面・小物・カメラ距離が違う。各プロンプトの
「他と何が違うか」に、その1枚だけの要素が書いてある。
**同じ机・同じノート・同じマグ・同じ頬杖・同じ右向きの上半身を繰り返さない。**

## 全20枚に共通で入っている禁止文

```text
No letters, no words, no numbers, no logos, no watermarks.
Do not render any interface text, application logo, brand name, score, price, date, duration, or numerical label.
Keep the entire left half visually quiet and uncluttered for later Japanese typography.
Do not depict Sakura using a service unless that usage is verified.
```

## 仕様の原本

`sakura-v1.yaml`（status: approved）。
プロンプトはこの仕様から機械的に組み立てている。
プロンプトと仕様が食い違って見えたら、**プロンプトのほうを正とし、こちらへ知らせてほしい**。
