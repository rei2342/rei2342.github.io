# 仕様案の修正2点と、画像生成バッチ（2026-08-09）

**公開環境は何も変更していません。** WordPressへの画像設定・予約再開・
既存画像の差し替えは行っていません。`sakura-v1.yaml` は `status: proposal` のままです。

---

## 修正1. 人物の割り当てを直しました

ご指示のとおり 1001 と 1003 を入れ替えました。**役割から書き直しています**（
`with_person` のtrue/falseだけを反転させると、場面の説明と噛み合わなくなるため）。

| 記事 | 前 | 後 | 場面をどう変えたか |
|---|---|---|---|
| 993 ChatGPT手順 | なし | **なし** | 変更なし |
| 995 AI英会話 vs 人 | なし | **なし** | 変更なし |
| 997 学ぶ意味 | あり | **あり** | 変更なし |
| 999 発音矯正 | あり | **あり** | 変更なし |
| 1001 必要な英語力 | なし | **あり** | 床の俯瞰・手だけ → **床に座って選んでいる人物**。無地のカード4枚に手をかざし、視線を落とす |
| 1003 会議の文字起こし | あり | **なし** | 肩越しの人物 → **無人の会議机の俯瞰** |

人物あり3・なし3は変わっていません（`balance_hint` の3〜5枚に収まりますが、
決めたのは役割です）。

### 1003 で「使っているように見える描写」を外した箇所

ご指示の「さくらが英語会議や特定ツールを実際に使っているように見える描写を避ける」
を、場面の文章から機械的に外しました。

- 人物を消した（肩越しに画面をのぞく構図をやめた）
- **画面を1つも点けていない**（`no screen is switched on`）
- 波形は画面ではなく**手描きのカードに鉛筆で描いた線**にした
  （画面に出すと、そのツールが動いている絵になるため）
- ヘッドセットは**折りたたんで置いてある・未使用**
- カップは2つ置いて「まだ来ていない人」を示す（会議中にしない）
- **すべての物に商標を入れない**（`Every object is unbranded`）

同じ理由で、`character.forbidden` の
「any scene implying she personally used, subscribed to or paid for a named service」
は6本すべてのプロンプトに入っています。

---

## 修正2. 参照画像の優先順位をプロンプトへ明記しました

「3枚を均等に混ぜる」動きを止めるため、**指定された英文をそのまま**
`reference_assets.directive` に置き、両アダプターが `REFERENCES:` 段落として
出力するようにしました。段落の位置は Python / TypeScript で同じです。

### 人物ありの3本（997・999・1001）に入る文

```text
REFERENCES:
Use reference 521 as the primary identity reference for Sakura's face,
adult age impression, facial proportions, and body proportions.
Use reference 273 only for the long brown hairstyle and subtle sakura
hair accessory.
Use reference 297 only for watercolor texture, soft natural light, and
color treatment. Do not copy its face, oversized eyes, chibi proportions,
or pink hoodie.
```

### 人物なしの3本（993・995・1003）に入る文

```text
REFERENCES:
No person appears in this image.
Use reference 297 only for watercolor texture, soft natural light, and
color treatment. Do not copy its face, oversized eyes, chibi proportions,
or pink hoodie.
```

**人物がいない画像に「顔の参照は521」と書かない**ようにしました。
書くと、人物なしの指示と矛盾して人物が湧きます。

### 不合格の基準

`reference_assets.reject_rule` に置き、`manifest.yaml` と `README.md` の
両方へ太字で出しています。

> 人物の顔が521から離れていたら不合格にする。作り直す。
> 297の顔・大きな目・ちび頭身・ピンクのパーカーは引き継がない

`quality_checks` にも `face_matches_521` を入れました。人物ありの3本では
**機械では判定しないので `—`（人が見る）**にしてあります。自動で✅を付けると
基準が形骸化するためです。人物なしの3本は自動で✅です。

### テストに足した検査

`scripts/test_eyecatch_spec.py` に3つ追加し、**失敗0件**です。

1. `REFERENCES:` 段落が全6本に出るか
2. **521 の指定が、人物ありの記事にだけ出るか**（人物なしに出たら落とす）
3. 人物の割り当てが承認どおりか
   （`993:なし 995:なし 997:あり 999:あり 1001:あり 1003:なし` を表として保持）

3番は私の取り違えを防ぐために入れました。YAMLを触って割り当てがずれたら落ちます。

---

## 3. `eyecatch-generation-batch/ai-6/`

手で6回コピーする運用にせず、フォルダごと渡せるようにしました。

```
eyecatch-generation-batch/ai-6/
  references/   521.jpg  273.jpg  297.jpg
  prompts/      993.md 995.md 997.md 999.md 1001.md 1003.md
  masters/      ← ここへ生成した文字なしマスターを置く（<記事ID>.png）
  manifest.yaml 記事ID・プロンプト・人物有無・参照・完成ファイル名の対応表
  README.md     参照の使い分け表・手順・人物割り当て・守ること
```

`prompts/<記事ID>.md` は1本ずつ完結しています。

- 人物の**あり／なし**と、その理由
- **使う参照ファイル**（人物ありは3枚、人物なしは `references/297.jpg` だけ）
- 貼るプロンプト全文（`REFERENCES:` 段落を含む）
- 出力先 `masters/<記事ID>.png`（1920×1080・文字なし）と、完成ファイル名・alt
- 生成後にこちらで合成する文字（**画像AIには描かせない**）

再生成は `python playbook/scripts/eyecatch_batch.py` です。
**参照が1枚でも欠けていたら、プロンプトを書かずに止まります**
（2枚だけ渡すと顔の基準が無いまま生成されてしまうため）。

---

## 4. 生成後の処理は用意しましたが、動かしていません

`scripts/eyecatch_finish.py` を書いてあります。実行すると現状はこうなります。

```
マスターが足りない: 993 995 997 999 1001 1003
…/masters/ へ <記事ID>.png を置いてから、もう一度。
**仮画像は作らない。** ここで止める。
```

マスターが1枚でも欠けていたら**何も出力せず終了**します。
仮画像で先へ進む経路を作っていません。6枚そろえば、次を出します。

| ご指定の成果物 | 出力先 |
|---|---|
| 文字なしマスター6枚 | `masters/`（お渡しいただくもの） |
| ブログ用完成版6枚（1200×675・文字合成） | `out/<完成ファイル名>.jpg` |
| note用クロップ6枚（1200×628・文字なし） | `out/<完成ファイル名>-note.jpg` |
| 3種類を並べたコンタクトシート | `out/CONTACT.jpg` |
| 各画像の13項目検査結果 | `CHECKS.md` |
| 再生成が必要な画像と理由 | `CHECKS.md` の末尾 |

**このスクリプトは WordPress へ一切送りません。** 設定・予約再開・既存画像の
差し替えは、コンタクトシートの承認後に別で行います。

---

## 5. こちらで詰まっている点（正直に）

**イラストを生成する手段が私の側にありません。**
ここが唯一の手渡し地点です。`eyecatch-generation-batch/ai-6/` を画像生成AIへ渡し、
`masters/` に6枚のPNGが置かれた時点から、あとは自動で進められます。

なお、**既存の文字カード型20本には、まだプロンプトがありません**。
今回のAI6本で仕様が確定してから同じ流れで作るのが安全だと考えていますが、
先に着手するかはご指示に従います。

---

## 6. 変更したファイル

| ファイル | 変更 |
|---|---|
| `config/eyecatch/sakura-v1.yaml` | `reference_assets.directive`（with_person / without_person）と `reject_rule` を追加。`status: proposal` のまま |
| `config/eyecatch/articles-ai-cluster.yaml` | 1001をあり・1003をなしへ。場面と `person_reason` を書き直し |
| `scripts/eyecatch_spec.py` | `REFERENCES:` 段落を追加（YAMLから読む。直書きなし） |
| `config/eyecatch/adapters/eyecatchPrompt.ts` | 同じ位置に同じ段落を追加 |
| `scripts/test_eyecatch_spec.py` | 参照指定・521の出し分け・人物割り当ての3検査を追加 |
| `scripts/eyecatch_batch.py` | **新規**。バッチフォルダを組み立てる |
| `scripts/eyecatch_finish.py` | **新規**。マスターが無い間は止まる |

戻し方は `SPEC_V1_HANDOFF.md` の「11. ロールバック」と同じで、すべて新規ファイルか
新規キーの追加です。既存のワークフローからは呼んでいません。
