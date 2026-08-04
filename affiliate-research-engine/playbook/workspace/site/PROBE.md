# サイト外形チェック 2026-08-04 01:11

## 接続診断
```
--- 通常接続 ---
http_code=000 ssl_verify=20
--- 証明書検証を無効化 ---
http_code=200
--- 証明書の内容 ---
subject=CN = sakura-eigo.com
issuer=C = US, O = Let's Encrypt, CN = YR2
notBefore=Jun  4 03:01:37 2026 GMT
notAfter=Sep  2 03:01:36 2026 GMT
--- www 側 ---
http_code=000
```

## robots.txt
```
User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php

Sitemap: https://sakura-eigo.com/sitemap.xml
Sitemap: https://sakura-eigo.com/sitemap.html
```

## サイトマップ候補のHTTPステータス
| URL | ステータス | 種類 |
|---|---|---|
| wp-sitemap.xml | 200 | `<?xml version='1.0' encoding='UTF-8'?><?xml-stylesheet type=` |
| sitemap_index.xml | 200 | `<?xml version="1.0" encoding="UTF-8"?><?xml-stylesheet type=` |
| sitemap.xml | 200 | `<?xml version='1.0' encoding='UTF-8'?><?xml-stylesheet type=` |
| sitemap-index.xml | 404 | `<!doctype html><html lang="ja" prefix="og: https://ogp.me/ns` |
| sitemap.xml.gz | 200 | `<?xml version='1.0' encoding='UTF-8'?><?xml-stylesheet type=` |
| wp-sitemap-posts-post-1.xml | 301 | `` |
| feed | 301 | `` |

## トップページの head 抜粋（SEOプラグイン判定）
```
Rank Math
google-site-verification" content="0pIyGHA4AeIZq9eodvR2t-pASqbzlL9kA4FzGZ_78GU" /
rank-math
rankmath
```
