# サイト外形チェック 2026-08-07 03:22

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
--- 計測ID（どのGA4プロパティに送っているか）---
      2 G-YRE7RGDSQV

--- google が出てくる箇所（IDが取れないときの手がかり）---
    <!-- Global site tag (gtag.js) - Google Analytics -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-YRE7RGDSQV"></script>
<meta name="google-site-verification" content="0pIyGHA4AeIZq9eodvR2t-pASqbzlL9kA4FzGZ_78GU" />
<link rel="preconnect dns-prefetch" href="//www.googletagmanager.com">
<link rel="preconnect dns-prefetch" href="//www.google-analytics.com">
<link rel="preconnect dns-prefetch" href="//ajax.googleapis.com">
<link rel="preconnect dns-prefetch" href="//pagead2.googlesyndication.com">
<link rel="preconnect dns-prefetch" href="//googleads.g.doubleclick.net">
<link rel="preconnect dns-prefetch" href="//tpc.googlesyndication.com">
<link rel="preconnect dns-prefetch" href="//cse.google.com">
<link rel="preconnect dns-prefetch" href="//fonts.googleapis.com">
var cocoon_localize_script_options = {"is_lazy_load_enable":null,"is_fixed_mobile_buttons_enable":"","is_google_font_lazy_load_enable":""};

--- その他の解析ツール ---
```

## 記事のOGP（SNSのプレビュー画像）
```
対象: https://sakura-eigo.com/online-english-lessons-90-days-success/
<meta property="og:title" content="オンライン英会話が3日で終わっていた私が、予約をやめて続いた90日 - さくらの英語挑戦記" />
<meta property="og:description" content="3日、4日、2日。オンライン英会話を3回登録して、続いた日数はこれで打ち止めだった。無料体験に申し込んで、初回はちゃんと話して、次の日に予約画面を開いて、講師を探しているうちに面倒になって閉じる。営業事務の残業で夜が崩れ [&hellip;]" />
<meta property="og:image" content="https://sakura-eigo.com/wp-content/uploads/2026/08/ChatGPT-Image-2026年8月7日-11_04_03.png" />
<meta property="og:image:secure_url" content="https://sakura-eigo.com/wp-content/uploads/2026/08/ChatGPT-Image-2026年8月7日-11_04_03.png" />
<meta property="og:image:width" content="1672" />
<meta property="og:image:height" content="941" />
<meta property="og:image:alt" content="オンライン英会話が3日で終わっていた私が、予約をやめて続いた90日" />
<meta property="og:image:type" content="image/png" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:image" content="https://sakura-eigo.com/wp-content/uploads/2026/08/ChatGPT-Image-2026年8月7日-11_04_03.png" />
--- og:image が実際に取れるか ---
URL: https://sakura-eigo.com/wp-content/uploads/2026/08/ChatGPT-Image-2026年8月7日-11_04_03.png
status=200 type=image/png size=2080342
```

## トップページの head 抜粋（SEOプラグイン判定）
```
Rank Math
google-site-verification" content="0pIyGHA4AeIZq9eodvR2t-pASqbzlL9kA4FzGZ_78GU" /
rank-math
rankmath
```
