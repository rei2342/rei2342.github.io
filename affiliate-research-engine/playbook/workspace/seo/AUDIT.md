# 技術SEO監査 2026-08-08 18:03:36 JST

**設定は変えていない。読んだだけ。**


---

## 見つかった問題

critical 0 / high 1 / medium 0 / low 1

| 重要度 | 問題 | 影響URL数 | 修正案 |
|---|---|---|---|
| low | descriptionが重複している | 3 | 記事ごとに書く |
| high | 記事の大半が内部リンクで繋がっていない | 49 | 監査済みの記事から順に相互リンクを足す |
## 1. 検索エンジン表示設定

- REST API からは取得できなかった。**管理画面 → 設定 → 表示設定 → 検索エンジンでの表示** を目視で確認する

## 2. robots.txt

```
User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php

Sitemap: https://sakura-eigo.com/sitemap.xml
Sitemap: https://sakura-eigo.com/sitemap.html

```
- 記載されたサイトマップ: ['https://sakura-eigo.com/sitemap.xml', 'https://sakura-eigo.com/sitemap.html']

## 3. XMLサイトマップ

- https://sakura-eigo.com/sitemap_index.xml → https://sakura-eigo.com/sitemap_index.xml（657バイト）
- https://sakura-eigo.com/wp-sitemap.xml → https://sakura-eigo.com/wp-sitemap.xml（694バイト）
- https://sakura-eigo.com/sitemap.xml → https://sakura-eigo.com/sitemap.xml（1080バイト）
- サイトマップに載っているURL: **56件**

## 4. 公開記事 49本とサイトマップの突き合わせ

- サイトマップに**載っていない**公開記事: **0本**

## 5. 記事ごとの状態

- HTTP が 200 でない記事: **0本**
- noindex が付いている記事: **0本**
- canonical が自分以外を指す記事: **0本**

- 重複タイトル: **0組**
- 重複description: **1組**

## 6. URLの統一

- http://sakura-eigo.com/ → 200 ✅ http://sakura-eigo.com/ → https://sakura-eigo.com/
- https://www.sakura-eigo.com/ → 200 ✅ https://www.sakura-eigo.com/ → https://sakura-eigo.com/
- http://www.sakura-eigo.com/ → 200 ✅ http://www.sakura-eigo.com/ → https://www.sakura-eigo.com/ → https://sakura-eigo.com/

## 7. アーカイブ・添付ファイルページ

- カテゴリ一覧 `https://sakura-eigo.com/category/` … 404
- タグ一覧 `https://sakura-eigo.com/tag/` … 404
- 日付アーカイブ `https://sakura-eigo.com/2026/08/` … 200
- 著者アーカイブ `https://sakura-eigo.com/author/rei/` … 404

## 8. 内部リンクと孤立記事

- 記事間の内部リンク: **0本**
- どこからもリンクされていない記事（孤立）: **49本 / 49本**

## 9. 構造化データ

- サンプル記事の @type: ['Article', 'BlogPosting', 'ImageObject', 'Person', 'WebPage', 'WebSite']
