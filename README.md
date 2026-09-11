# Psychology Blog — 人間の科学・テーマと研究データベース

**更新：2026-09-11。28分野・300テーマ。追加100テーマ、重要論文・指針の読解メモ68件。**

一般の読者が自分の生活と結びつけて読める、日本語ブログの調査用データです。完成記事や医療上の推奨ではありません。

## 今回の成果と確認範囲

出典台帳は106件（旧35資料＋今回の研究・指針68件＋訂正告知3件）。読解メモは139テーマに対応し、うち既存テーマ106件、新規テーマ33件です。

関連資料付きは169テーマ、個別の出典未登録は131テーマです。資料付きでも背景解説だけの場合があります。全300テーマの正式な確実性評価は未実施で、公開可能状態にはしていません。

検索は300回実行し、候補レコード1105件を保存しました。候補は未選別を含み、同一研究の別版もあり得ます。重要資料の読解は抄録中心で、全文の品質評価・解析再現とは異なります。

## 読みやすい入口

- [300テーマ一覧](docs/TOPICS_INDEX.md)
- [68件の重要論文・指針と生活へのつながり](docs/RESEARCH_NOTES.md)
- [分類・基本テーマ・派生記事の設計](docs/THEME_ARCHITECTURE.md)
- [調査件数・分野別の進捗](data/research/coverage.json)

## 分野別JSON

| 分野 | テーマ数 | 読解メモ付き |
|---|---:|---:|
| [睡眠・体内時計](data/topics/01_sleep.json) | 10 | 6 |
| [遺伝・環境・気質](data/topics/02_genetics.json) | 10 | 5 |
| [依存・報酬・禁煙](data/topics/03_addiction.json) | 10 | 5 |
| [習慣形成・行動変容](data/topics/04_habits.json) | 10 | 6 |
| [性格・自己理解](data/topics/05_personality.json) | 10 | 6 |
| [動機づけ・先延ばし](data/topics/06_motivation.json) | 10 | 8 |
| [学習・記憶・勉強法](data/topics/07_learning.json) | 10 | 6 |
| [注意・集中・仕事の効率](data/topics/08_attention.json) | 10 | 6 |
| [意思決定・認知バイアス](data/topics/09_decisions.json) | 10 | 1 |
| [感情・ストレス対処](data/topics/10_emotions.json) | 10 | 9 |
| [メンタルヘルス・心理療法](data/topics/11_mental_health.json) | 10 | 8 |
| [対人関係・コミュニケーション](data/topics/12_relationships.json) | 10 | 7 |
| [社会心理・集団・心理効果](data/topics/13_social.json) | 10 | 3 |
| [幸福・生活満足度](data/topics/14_wellbeing.json) | 10 | 5 |
| [運動・身体活動・回復](data/topics/15_exercise.json) | 10 | 7 |
| [食行動・栄養・心身](data/topics/16_nutrition.json) | 10 | 2 |
| [発達・子育て・思春期](data/topics/17_development.json) | 10 | 1 |
| [加齢・認知機能・介護](data/topics/18_aging.json) | 10 | 6 |
| [スマホ・SNS・デジタル生活](data/topics/19_digital.json) | 10 | 3 |
| [研究の読み方・再現性](data/topics/20_research_literacy.json) | 10 | 6 |
| [仕事・働き方・キャリア](data/topics/21_work.json) | 14 | 7 |
| [お金・買い物・消費心理](data/topics/22_money_consumption.json) | 14 | 3 |
| [恋愛・親密さ・パートナーシップ](data/topics/23_intimacy.json) | 12 | 2 |
| [身体感覚・ホルモン・健康行動](data/topics/24_health_psychology.json) | 12 | 2 |
| [生活環境・感覚・快適さ](data/topics/25_environment.json) | 12 | 5 |
| [好奇心・創造性・遊び](data/topics/26_creativity.json) | 12 | 4 |
| [言葉・会話・語学・思考](data/topics/27_language.json) | 12 | 3 |
| [人生の変化・喪失・適応](data/topics/28_life_transitions.json) | 12 | 7 |

## データ構成

`data/topics/` がテーマの正本です。出典は `data/sources.json`、主張と限界の予備整理は `data/research/briefs.json`、関連・派生関係は `data/topic_relations.json` に分離しています。候補と検索履歴は `data/literature/` にあります。

研究で実際に調べた対象・条件は `study_context`、説明のための生活場面は `daily_life_example` です。後者は実在人物の体験談や、直接検証済みの介入ではありません。

## 検証と統合出力

```bash
python scripts/validate.py --export build
python scripts/validate_research.py --export build
```

Python 3.9以降の標準ライブラリを使用。テーマ統合JSON、論文読解メモ、候補台帳、検索ログ、構造検証レポートを出力します。構造検証は科学的正しさの保証ではありません。

`research/` のPSVは今回の編集用原稿で、通常の更新対象は正本JSONです。一度限りの取り込みは一時的な読解用Artifactを入力にしましたが、保存後の正本・検証・統合出力にはそのArtifactは不要です。定期実行は設定していません。

## 未確認事項

重要論文68件は抄録中心の予備読解で、全テーマの正式なエビデンス評価ではない。
候補件数はデータベースのレコード数。プレプリントと刊行版など同一研究の別版を含み得る。
既存200テーマは概念検索済み。新規100テーマすべての個別検索は未実施。
Europe PMC中心の検索には収載分野の偏りがある。各検索の上位5件であり網羅的検索ではない。
検索の成功は関連文献が存在することや十分な根拠を得たことを意味しない。
索引上の訂正・関連論文は確認したが、全文・全追試・撤回情報の網羅的精査は未実施。
生活例は説明用の想定場面であり、実在人物の事例やその方法を直接検証した結果ではない。

出典の優先度と証拠の強さは別管理です。相関と因果、個人と集団、人と動物、短期と長期を分けます。遺伝率を個人の遺伝割合と解釈しません。治療・薬・依存症・睡眠制限などの記事は専門家の安全確認を必要とします。

[データ辞書](docs/DATA_DICTIONARY.md) / [収集方針](docs/METHODOLOGY.md)
