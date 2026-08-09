# 返し方と、受領後の処理（2026-08-09 17:34:40 JST）

## 返してもらう構成

```
masters/
  993.png
  995.png
  997.png
  999.png
  1001.png
  1003.png
```

これだけでよい。JPEGへの変換・リサイズ・文字入れは**しない**。
6枚そろってから渡してほしい（**1枚でも欠けると受領処理が止まる**）。

## 受領後に、こちらが実行すること

`masters/` を `eyecatch-generation-batch/ai-6/masters/` へ置き、次を1回走らせる。

```bash
python affiliate-research-engine/playbook/scripts/eyecatch_finish.py
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
python affiliate-research-engine/playbook/scripts/eyecatch_apply.py --approve
```

`--approve` を付けない限り、何が起きるかの一覧を出すだけで**サイトは触らない**。
付けたときの順番は次のとおり。

1. 全記事のバックアップ（現在の `featured_media` と画像URL）
2. メディアへアップロード（ファイル名は半角英数・altを設定）
3. `featured_media` を差し替え
4. **公開済みの993の画像を差し替え**
5. **予約5本を、元の予約日時のまま再予約へ戻す**
6. 公開画面・OGP・alt・メディアの対応を確認
7. ロールバック手順を `backups/` へ記録

`eyecatch_finish.py` は**WordPressへ一切送らない**。
サイトへ触るのは `eyecatch_apply.py --approve` だけ。
