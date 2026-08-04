# サイト外形チェック 2026-08-04 01:26

## 接続診断
```
--- 通常接続 ---
http_code=000 ssl_verify=1
--- 証明書検証を無効化 ---
http_code=503
--- 証明書の内容 ---
subject=CN = *.conohawing.com
issuer=C = BE, O = GlobalSign nv-sa, CN = GlobalSign GCC R3 DV TLS CA 2020
notBefore=Nov  5 04:02:51 2025 GMT
notAfter=Dec  7 04:02:50 2026 GMT
--- www 側 ---
http_code=000
```

## robots.txt
```
<!DOCTYPE html>
<html>
<head>
<title>Error</title>
<style>
html { color-scheme: light dark; }
body { width: 35em; margin: 0 auto;
font-family: Tahoma, Verdana, Arial, sans-serif; }
</style>
</head>
<body>
<h1>An error occurred.</h1>
<p>Sorry, the page you are looking for is currently unavailable.<br/>
Please try again later.</p>
<p>If you are the system administrator of this resource then you should check
the error log for details.</p>
<p><em>Faithfully yours, nginx.</em></p>
</body>
</html>
```

## サイトマップ候補のHTTPステータス
| URL | ステータス | 種類 |
|---|---|---|
| wp-sitemap.xml | 503 | `<!DOCTYPE html><html><head><title>Error</title><style>html {` |
| sitemap_index.xml | 503 | `<!DOCTYPE html><html><head><title>Error</title><style>html {` |
| sitemap.xml | 503 | `<!DOCTYPE html><html><head><title>Error</title><style>html {` |
| sitemap-index.xml | 503 | `<!DOCTYPE html><html><head><title>Error</title><style>html {` |
| sitemap.xml.gz | 503 | `<!DOCTYPE html><html><head><title>Error</title><style>html {` |
| wp-sitemap-posts-post-1.xml | 503 | `<!DOCTYPE html><html><head><title>Error</title><style>html {` |
| feed | 503 | `<!DOCTYPE html><html><head><title>Error</title><style>html {` |

## トップページの head 抜粋（SEOプラグイン判定）
```
```
