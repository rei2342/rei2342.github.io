# トップページの固定化 2026-08-09 00:47:14 JST

モード: **LIVE（書いた）**

## 反映前のホーム表示設定（バックアップ済み）

- `show_on_front`: **page**
- `page_on_front`: **643**
- `page_for_posts`: **642**
- `posts_per_page`: **10**
- 固定ページ: 7件
- バックアップ: `workspace/backups/2026-08-09/frontpage.json`

## 1. TOEIC記事のカテゴリ割り当て（ページ生成より先に実行）

**主カテゴリを1つにする。**過剰に付けない。

| 記事 | 前 | 後 | 公開状態 |
|---|---|---|---|
| 304 | [10] | 変更なし（すでに割当済み） | publish |
| 521 | [10] | 変更なし（すでに割当済み） | publish |
| 32 | [10] | 変更なし（すでに割当済み） | publish |

再取得したカテゴリ件数: `toeic-score` = **3本** / `ai-english` = **0本**

## 3. 記事一覧ページ（トップより先に作る）

- slug `articles` … ✅ 更新（ID 642）
- URL: https://sakura-eigo.com/articles/

## 4. トップページ

- slug `start` … ✅ 更新（ID 643）

### カテゴリ導線（記事が0本のものはリンクにしない）

| カテゴリ | 記事数 | 扱い |
|---|---|---|
| 英語学習法 | 9 | リンクにする |
| TOEIC・スコア | 3 | リンクにする |
| 英会話サービス比較 | 3 | リンクにする |
| 英語コーチング | 3 | リンクにする |
| AI英語学習 | 0 | **準備中（リンクなし）** |
| 海外留学・ワーホリ | 22 | リンクにする |
| フィリピン・セブ留学 | 7 | リンクにする |
| 留学エージェント・費用 | 2 | リンクにする |

## 5. ホーム表示の切り替え

- `show_on_front` → `page` / `page_on_front` → 643 / `page_for_posts` → 642

→ ✅ 反映した

## 6. プロフィール固定ページ

- ID 8 / 旧設定の残存: **27歳・営業事務・5年後回し・30歳まで・来年こそ**
- バックアップ: `workspace/backups/2026-08-09/page8_profile.json`
- → ✅ 差し替えた

## 7. 公開URLの確認

| URL | HTTP | canonical | noindex | 判定 |
|---|---|---|---|---|
| https://sakura-eigo.com/ | 200 | https://sakura-eigo.com/ | なし |  |
| https://sakura-eigo.com/start/ | 200 | https://sakura-eigo.com/ | なし | ✅ ルートへ301 |
| https://sakura-eigo.com/articles/ | 200 | https://sakura-eigo.com/articles/ | なし |  |
| https://sakura-eigo.com/feed/ | 200 | （無し） | なし |  |
