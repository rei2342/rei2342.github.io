# 返し方と、受領後の処理（文字カード型20本の差し替え・2026-08-09 19:37:39 JST）

## 返してもらう構成

```
masters/
  546.png
  526.png
  521.png
  304.png
  301.png
  294.png
  235.png
  149.png
  137.png
  23.png
  310.png
  292.png
  283.png
  282.png
  281.png
  150.png
  117.png
  33.png
  32.png
  28.png
```

これだけでよい。JPEGへの変換・リサイズ・文字入れは**しない**。
batch_1 の10枚がそろった時点で一度返してほしい。残りは確認のあとで構わない。（**枚数が足りないと受領処理は止まる**）。

## 受領後に、こちらが実行すること

`masters/` を `eyecatch-generation-batch/next-20/masters/` へ置き、次を1回走らせる。

```bash
python affiliate-research-engine/playbook/scripts/eyecatch_finish.py --batch next20
```

これで下の4つまで一度に出る。**追加の判断は要らない。**

| 段 | 中身 | 出力 |
|---|---|---|
| 1 | **文字合成** … 左のセーフエリアへリードと補助を載せ、1200×675 のJPEGにする | `out/<完成ファイル名>.jpg` |
| 2 | **note用クロップ** … 右寄せで 1200×628（1.91:1）に切る。**文字は載せない** | `out/<完成ファイル名>-note.jpg` |
| 3 | **13項目検査** … サイズ・比率・重さ・ファイル名・文字の有無・顔の一致など | `CHECKS.md` |
| 4 | **コンタクトシート** … マスター・ブログ用・note用の3種を並べる | `out/CONTACT.jpg` |

不合格になった画像だけを `CHECKS.md` の末尾に一覧化する（記事IDと落ちた項目）。
**機械で判定できない項目は自動で合格にせず、`—` として人が見る。**

## そのあと（承認後にだけ動かす）

```bash
python affiliate-research-engine/playbook/scripts/eyecatch_apply.py --batch next20 --approve
```

`--approve` を付けない限り、何が起きるかの一覧を出すだけで**サイトは触らない**。
付けたときの順番は次のとおり。

1. 全記事のバックアップ（今の `featured_media` と画像URL）
2. メディアへアップロード（ファイル名は半角英数・altを設定）
3. `featured_media` を差し替え
4. 公開画面・OGP・alt・メディアの対応を確認
5. ロールバック手順を `backups/` へ記録

**今の画像も、参照に使っている旧521・273・297も削除しない。**
差し替えは featured_media を向け替えるだけで、古いメディアはそのまま残す。

`eyecatch_finish.py` は**WordPressへ一切送らない**。
サイトへ触るのは `eyecatch_apply.py --approve` だけ。
