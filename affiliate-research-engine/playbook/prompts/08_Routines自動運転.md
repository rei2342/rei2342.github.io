# 第8章 Claude Code Routines で完全自動運転 — 一度作れば寝てる間も動く5つ

> `/schedule`（Routines）= Anthropicのクラウド側で動くスケジュール実行。
> PCの電源が落ちていても回り続ける。最低3つはセットで動かす（第10章テク41）。
>
> **登録方法:** Claude Code で `/schedule` を実行し、`../routines/*.md` の各プロンプトを貼る。
> 各Routineが参照するフォルダ（`../workspace/`）とファイルはこのリポジトリに用意済み。

この章のプロンプト本体は、登録しやすいよう個別ファイルにも分けてある:
- テク31 → `../routines/daily-article-drafter.md`
- テク32 → `../routines/daily-sns-cannon.md`
- テク33 → `../routines/weekly-serp-watcher.md`
- テク34 → `../routines/monthly-pl-reporter.md`
- テク35 → `../routines/failure-detection-loop.md`

---

## 31. Daily Article Drafter — 毎朝1本のドラフトが机に置かれている

```
Claude Codeの /schedule で、以下のRoutineを作成してください。

【スケジュール】毎日朝6:00
【プロンプト】
①./workspace/keyword-queue/ から本日分のキーワードを1件取得
②そのキーワードでSERP上位10件の見出し構造を分析(第3章テク9)
③構造に基づき4000字のドラフトを生成(第6章テク23のNGリストを必ず併用)
④./workspace/drafts/YYYY-MM-DD.md として保存
⑤完成をSlack MCPで通知
```

## 32. Daily SNS Cannon — X投稿の自動生成と予約

```
Claude Codeの /schedule で、以下のRoutineを作成してください。

【スケジュール】毎日朝7:00
【プロンプト】
①./workspace/content-bank/ のバズ投稿(エンゲージメント率3%以上)を10件参照
②3つの構文パターンを選び、本日のテーマでX投稿を3本生成
③各投稿にnote記事への自然なCTAを差し込む(第4章テク15)
④予約投稿ツールにAPI送信
⑤完成リストをSlackに通知
```

## 33. Weekly SERP Watcher — 順位変動を週次で自動監視

```
Claude Codeの /schedule で、以下のRoutineを作成してください。

【スケジュール】毎週月曜朝9:00
【プロンプト】
①稼働中の全キーワード(./workspace/keywords.csv)の順位を取得
②前週比で5位以上下落したキーワードを抽出
③上位記事との差分(見出し構造/文字数/E-E-A-T要素)を分析
④優先度順にリライト候補としてレポート
⑤Slackに通知
```

## 34. Monthly P&L Reporter — 月次収益レポートを自動生成

```
Claude Codeの /schedule で、以下のRoutineを作成してください。

【スケジュール】毎月1日朝8:00
【プロンプト】
①Notion MCP で「案件管理」DBから前月の全データを取得
②発生額/確定額/承認率/案件別の貢献度を集計
③前月比/前年同月比のグラフを生成
④ハイライト3つ・課題3つ・来月の重点アクション3つを抽出
⑤./workspace/reports/YYYY-MM.md として保存し、Slackに通知
```

## 35. Failure Detection Loop — 反応が悪い記事を自動検知して改修案を出す

```
Claude Codeの /schedule で、以下のRoutineを作成してください。

【スケジュール】毎週金曜朝10:00
【プロンプト】
①アクセス解析から過去30日のPV/CVデータを取得
②過去90日比でPVが30%以上下落した記事を抽出
③各記事の原因仮説(SEO/トレンド/競合)・改修方向性3つ・工数見積をまとめる
④優先度順にSlackへ通知
```

---

### この章のゴール
ドラフト・SNS・順位監視・月次レポート・不調検知が勝手に動く。
あなたに残るのは「戦略を決める」「ドラフトを最後だけ磨く」「月次を見て次を決める」の3つだけ。
