# トップページの固定化 2026-08-09 00:38:36 JST

モード: **DRY RUN（書いていない）**

## 反映前のホーム表示設定（バックアップ済み）

- `show_on_front`: **posts**
- `page_on_front`: **0**
- `page_for_posts`: **0**
- `posts_per_page`: **10**
- 固定ページ: 5件
- バックアップ: `workspace/backups/2026-08-09/frontpage.json`

## 1. 記事一覧ページ（先に作る）

- slug `articles` … 新規作成する（DRY RUN）（ID None）
- URL: https://sakura-eigo.com/articles/

## 2. トップページ

- slug `start` … 新規作成する（DRY RUN）（ID None）

### カテゴリ導線（記事が0本のものはリンクにしない）

| カテゴリ | slug | 記事数 | 扱い |
|---|---|---|---|
| 勉強法・続け方 | `english-study` | （カテゴリ無し） | **準備中と書くだけ。リンクにしない** |
| TOEIC・スコア | `toeic-score` | 0 | **準備中と書くだけ。リンクにしない** |
| サービスの選び方 | `eikaiwa-hikaku` | （カテゴリ無し） | **準備中と書くだけ。リンクにしない** |
| AI英語学習 | `ai-english` | 0 | **準備中と書くだけ。リンクにしない** |
| 留学・ワーホリ | `ryugaku-workingholiday` | （カテゴリ無し） | **準備中と書くだけ。リンクにしない** |

## 3. ホーム表示の切り替え

⚠️ ページIDが揃わないので**切り替えない**。
