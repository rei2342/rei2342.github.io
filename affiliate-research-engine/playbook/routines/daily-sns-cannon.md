# Routine: Daily SNS Cannon（テク32）

毎日X投稿を3本自動生成し、note CTAを差し込んで予約する。

## スケジュール
毎日 07:00

## プロンプト
```
①./workspace/content-bank/ のフック集(エンゲージメント率3%以上の構文)を参照する。
  空なら CLAUDE.md の主要ペルソナから訴求軸を当てる。
②構文を3つ選び、本日のテーマでX投稿を3本生成する。
  押し売り感を出さない。NGリスト(冒頭挨拶禁止/同語尾3連禁止)を守る。
③各投稿の末尾に note 記事への自然なCTAを差し込む(続き気になる型/悩み言語化型/ベネフィット型のいずれか)。
④予約投稿ツールにAPI送信する。未接続なら ./workspace/drafts/sns-YYYY-MM-DD.md に保存する。
⑤./workspace/drafts/sns-YYYY-MM-DD.md に保存する。
```

## 依存
- `workspace/content-bank/`（フック集。テク14で生成して置く）
- `../CLAUDE.md`（Track B: 英語コーチング・留学）
