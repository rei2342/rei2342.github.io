# GA4を繋ぐのに要る作業（3つ・全部Google側の設定）

サイトにGA4のタグは既に入っている（2026-08-06のサイト外形チェックで確認済み）。
足りないのは「APIから読み出す権限」だけ。

## 1. APIを有効化する

プロジェクト **pelagic-media-504503-i9**（＝Search Consoleの鍵を作ったのと同じもの）で
2つ有効にする。ボタンを押すだけ。

- Google Analytics Data API
  https://console.developers.google.com/apis/api/analyticsdata.googleapis.com/overview?project=1067982443924
- Google Analytics Admin API（プロパティIDを自動で探すのに使う。3で手入力するなら省略可）
  https://console.developers.google.com/apis/api/analyticsadmin.googleapis.com/overview?project=1067982443924

## 2. サービスアカウントに閲覧権限を渡す

GA4 → 左下の **管理** → **プロパティのアクセス管理** → 右上の **＋** → ユーザーを追加

```
gsc-reader@pelagic-media-504503-i9.iam.gserviceaccount.com
```

役割は **閲覧者**。「メール通知」のチェックは外してよい（サービスアカウントは受け取れない）。

## 3.（任意）プロパティIDを固定する

Admin APIを有効にすれば自動で探すので不要。手入力する場合は
GA4 → 管理 → プロパティの詳細 に出る**9桁の数字**を、
GitHubの Settings → Secrets → Actions に `GA4_PROPERTY_ID` として登録する。

---

## 終わったら

Actions の「GA4のアクセスを取る」を手動実行する。
結果は `LATEST.md` に出る。見るのは **「着地ページ × 流入元」** の節。

- `sessionSource = threads` の行があれば、Threadsの投稿から記事に来ている
- 0件なら、投稿は見られていても記事までは来ていない

## 注意

- GA4は**タグを入れた時点より前は取れない**。8/5より前の数字は存在しない。
- 8/5 21時のThreads投稿がタグ設置より後なら計測されている。前なら取りこぼしている。
  どちらかは実行してみないと分からない。
- アフィリンクのクリック数はこの取得には入らない。GA4の拡張計測イベント（click）は
  リンク先ドメインをそのままでは集計できないため。ASP側の管理画面で見る。
