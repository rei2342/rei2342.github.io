# サイト外形チェック 2026-08-06 00:53

## 接続診断
```
--- 通常接続 ---
http_code=200 ssl_verify=0
--- 証明書検証を無効化 ---
http_code=200
--- 証明書の内容 ---
subject=CN = sakura-eigo.com
issuer=C = US, O = Let's Encrypt, CN = YR2
notBefore=Aug  4 00:35:53 2026 GMT
notAfter=Nov  2 00:35:52 2026 GMT
--- www 側 ---
http_code=301
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

## アクセス解析で使えそうなもの
```
--- REST APIの名前空間（統計プラグインが居ればここに出る） ---
oembed/1.0
akismet/v1
contact-form-7/v1
rankmath/v1
rankmath/v1/setupWizard
cocoon/v1
rankmath/v1/ca
rankmath/v1/an
rankmath/v1/in
rankmath/v1/status
mcp
wp/v2
wp-site-health/v1
wp-block-editor/v1
wp-abilities/v1

--- Jetpack統計が使えるか ---
jetpack/v4: 404
--- トップページに入っている解析タグ ---
      1 google-analytics
      1 googletagmanager
```

## トップページの head 抜粋（SEOプラグイン判定）
```
Rank Math
google-site-verification" content="0pIyGHA4AeIZq9eodvR2t-pASqbzlL9kA4FzGZ_78GU" /
rank-math
rankmath
```
