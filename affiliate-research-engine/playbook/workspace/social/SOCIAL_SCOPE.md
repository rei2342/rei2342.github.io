# 数え方と検算（2026-08-09 20:12:57 JST）

## 単位

投稿1本を1件とする。スレッド2連は2件。
セット1ファイルを1件にすると、Xの1投稿とThreadsのスレッドが同じ重みになる。

## 検算

| 区分 | 件数 |
|---|---|
| X | 5 |
| Threads | 43 |
| **合計** | **48** |

X 5 ＋ Threads 43 ＝ 48。CSVの行数と一致する。

## 内訳

| 置き場 | 件数 |
|---|---|
| TH-FILE | 20 |
| TH-LIVE | 13 |
| TH-MEMO | 10 |
| X-LIVE | 1 |
| X-PROMO | 4 |

## 重複

完全一致 9組 / 包含 0組

### 完全一致（空白を除いて同一）

| A | B |
|---|---|
| TH-FILE-2026-08-07-1 | TH-MEMO-584-1 |
| TH-FILE-2026-08-07-2 | TH-MEMO-584-2 |
| TH-FILE-2026-08-08-1 | TH-MEMO-641-1 |
| TH-FILE-2026-08-08-2 | TH-MEMO-641-2 |
| TH-FILE-built_315-3 | TH-FILE-built_521-3 |
| TH-FILE-built_315-3 | TH-FILE-built_526-3 |
| TH-FILE-built_521-3 | TH-FILE-built_526-3 |
| TH-FILE-built_546-1 | TH-MEMO-547-1 |
| TH-FILE-built_546-2 | TH-MEMO-547-2 |

## この監査に含めなかったもの

| 対象 | 理由 |
|---|---|
| `workspace/instagram/` | Instagramは今回の対象外（XとThreadsのみ）|
| `outputs/`（Track A・転職） | 別人格・別アカウント |
| Xの投稿済み履歴 | **保存していない。** x_state.json に直近1本だけ。x-poster.yml は投稿本文を記録せず、次回許可時刻だけ書く |
| Threads投稿の全文 | Threads APIが本文を先頭だけ返す。実測13本は冒頭のみ |
