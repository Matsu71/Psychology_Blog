# Psychology Blog — 人間の科学・調査用データベース

**28分野・300テーマ。記事本文・サイトの制作前の調査段階です。**

## 第3回の更新（2026-09-11）

出典台帳は270件。今回124件を追加し、出典未登録は131テーマから0テーマになりました。登録だけで科学的結論を確認したことにはなりません。

今回の124件の確認メモは抄録102件、書誌のみ22件です。旧68件の読解メモを保持し、重要資料7件について本文の指定箇所も確認しました。正式なバイアス・確実性評価や独立した二重選別は未実施です。

今回の検索は510回。累計810回、候補レコード3018件です。候補は未選別を含み、レコード数と独立した研究数は異なります。

## 最初に開くファイル

- [テーマの有力度・次の調査順](docs/RANKINGS.md)
- [追加124件の書誌・結果・限界](docs/ROUND3_SOURCE_NOTES.md)
- [全300テーマ一覧](docs/TOPICS_INDEX.md)
- [データ設計](docs/DATABASE_ARCHITECTURE.md) / [採点方法](docs/RANKING_METHOD.md) / [次の作業](docs/NEXT_STEPS.md)

## 使い方

```bash
python scripts/validate.py --export build
python scripts/validate_research.py --export build
python scripts/validate_round3.py --export build
python scripts/query_database.py topic PSY-SLP-004 --limit 5
python scripts/build_research_views.py
```

テーマ正本はdata/topics、出典正本はdata/sources.json、関連性と使える範囲はdata/evidence、資料評価はdata/source_assessments.json、ランキングはdata/rankingsです。候補台帳はdata/literature/catalog.jsonから必要な分割ファイルだけ読みます。

順位は正本の配列を並べ替えず別ファイルに生成します。出典の優先度はテーマとの対応・方法上の情報・確認範囲を区別した調査用指標で、科学的に正しい確率やGRADE評価ではありません。編集ランキングは50テーマの仮説的な評価であり、実際の人気を測定していません。

## 未完了の確認

出典未登録0テーマを引き続き直接資料で補います。登録済みでも書誌・背景だけの場合があり、全文・独立追試・反証・訂正・日本への適用を確認してから記事化します。全テーマのpublication_readyはfalseです。

生活例は説明用の想定場面と研究で実際に調べた場面を区別します。薬・治療・依存・トラウマ等は専門家の安全性確認を必要とします。全論文の原文・図表は公開データに転載していません。

旧データを巻き戻す一回限りのワークフローは廃止しています。通常は正本を編集し、読取専用の検証と派生ビュー生成を行います。定期実行は設定していません。
