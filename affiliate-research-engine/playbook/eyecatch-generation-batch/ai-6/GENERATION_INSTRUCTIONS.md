# 生成手順（AI英語学習6本・2026-08-09 19:37:39 JST）

さくら（sakura-eigo.com）のアイキャッチ用に、**文字なしのマスター画像を6枚**作る。
文字はこちらで後から合成する。**画像の中に文字を描かない。**

## 手順

1. **参照画像と、その記事のプロンプトを同時に入力する**
   （`references/` の指定ファイルと `prompts/<記事ID>.md` のプロンプト）
2. **1記事につき、文字なしマスターを1枚生成する**
3. **1920×1080 の PNG で保存する**（16:9）
4. **ファイル名を `<記事ID>.png` にする**（例 `1003.png`）
5. **6枚を `masters/` フォルダにまとめて返す**
6. **文字・数字・ロゴが出た画像は返さない。** 作り直す
7. **人物ありの画像は、521と同一人物に見えるか確認する。**
   別人に見えたら作り直す
8. **左半分に重要な人物・小物を置かない。**
   あとから日本語を載せるので、左は静かに空ける

## 6枚の一覧

| 記事ID | 束 | 人物 | プロンプト | 渡す参照 |
|---|---|---|---|---|
| 1003 | 1 | なし | `prompts/1003.md` | 297.jpg |
| 1001 | 1 | あり | `prompts/1001.md` | 521.jpg 273.jpg 297.jpg |
| 999 | 1 | あり | `prompts/999.md` | 521.jpg 273.jpg 297.jpg |
| 997 | 1 | あり | `prompts/997.md` | 521.jpg 273.jpg 297.jpg |
| 995 | 1 | なし | `prompts/995.md` | 297.jpg |
| 993 | 1 | なし | `prompts/993.md` | 297.jpg |

## 参照画像の使い分け（3枚を均等に混ぜない）

| 優先 | ファイル | 採る | 採らない |
|---|---|---|---|
| 1 | `references/521.jpg` | **顔・年齢感・頭身** | まとめ髪・電車の場面 |
| 2 | `references/273.jpg` | 長い茶髪・桜クリップ | 顔の角度 |
| 3 | `references/297.jpg` | 水彩の塗り・光・空気感 | **顔・大きな目・ちび頭身・ピンクのパーカー** |

**人物なしの記事（1003 995 993）には 521 と 273 を渡さない。**

## 見本

- `previews/reference-comparison.jpg` … 参照3枚の比較。全体と顔の拡大、採るもの／採らないもの
- `previews/existing-ai6-contact-sheet.jpg` … 並びの見本。中身は既存画像の流用で、目指す完成形ではない

## 場面の使い回しをしない

6本すべてで場面・小物・カメラ距離が違う。各プロンプトの
「他と何が違うか」に、その1枚だけの要素が書いてある。
**同じ机・同じノート・同じマグ・同じ頬杖・同じ右向きの上半身を繰り返さない。**

## 全6枚に共通で入っている禁止文

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
