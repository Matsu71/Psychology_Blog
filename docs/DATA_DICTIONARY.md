# データ辞書

更新：2026-09-11。基本スキーマ1.0を維持し、任意項目と研究台帳を追加しました。

## 正本と一覧

`data/topics/` の分野別JSONがテーマの正本です。`data/categories.json` が分類・ファイル・順序・件数を管理します。`data/sources.json` は旧35資料と追加71資料を含む出典台帳です。読みやすい入口は `docs/TOPICS_INDEX.md` と `docs/RESEARCH_NOTES.md` です。

## テーマの項目

| 項目 | 意味 |
|---|---|
| `id` | `PSY-分野略号-連番` の安定ID。削除番号も再利用しない。 |
| `title_ja` | 記事の問い・題名候補であり、効果を断定する結論ではない。 |
| `concepts_en` | 文献検索に使う研究概念。 |
| `angle_ja` | 記事の切り口、対象とする生活上の疑問。 |
| `search_query` | 追加調査用の検索文字列。実行履歴は別台帳を参照。 |
| `priority` | 編集上の調査優先度。1=初期優先、2=発展。証拠の強さではない。 |
| `source_ids` | 関連する資料。背景資料や訂正告知も含み、全主張を直接支持するとは限らない。 |
| `caution_ja` | 因果の飛躍、対象、健康上の注意など。 |
| `research_brief_ids` | 今回追加した抄録中心の読解メモへの参照。 |
| `related_topic_ids` | 関連する別の問い。親子関係や因果関係ではない。 |
| `parent_topic_ids` | 明確な応用・派生元。複数の親を持てる。 |
| `daily_life_example` | 説明用の想定場面。新規100テーマに追加。 |

全テーマに `manifest.json` の既定値を適用します。`record_status=theme_candidate`、`evidence_appraisal=not_assessed`、`publication_ready=false` です。読解メモを付けたことと、テーマ全体の正式なエビデンス評価が完了したことは区別します。

資料があれば `reference_linked`、なければ `search_pending` とする従来の状態は互換性のため維持しています。後者は『資料未登録』の意味であり、検索自体を一度も実行していないとは限りません。既存200テーマの概念検索は実行済みです。

## 資料と確認範囲

基本項目は `id,title,authors_display,year,journal,source_type,doi,url,verified_via_url,verification_scope,notes_ja`。追加資料には `pmid,first_publication_date,accessed_on,provenance_query_ids,record_role,indexed_related_records,correction_retraction_check` も記録します。

`year` は書誌の掲載年で、オンライン初公開日とは異なり得ます。未確認のDOI・年は推測せず `null` にします。`verified_via_url` は実際の書誌・抄録確認に使ったAPIまたはページです。

| `verification_scope` | 意味 |
|---|---|
| `official_page_reviewed` | 公的解説・参考文献一覧を閲覧。 |
| `bibliography_verified` | 書誌確認。抄録・全文の読解完了を意味しない。 |
| `abstract_reviewed` | 抄録を確認。全文の品質評価や解析再現ではない。 |
| `article_text_reviewed` | 本文を閲覧した既存資料。体系的な査読相当の評価ではない。 |

`record_role=correction_notice` は訂正告知で、独立した効果研究の件数には含めません。`indexed_links_checked_not_exhaustive` は索引の関連論文欄を見たという意味です。関連欄が空でも、訂正・撤回・反論が一切存在しないと確認したわけではありません。

## 研究の読解メモ

`data/research/briefs.json` に68件を保存します。`primary_source_id` と `source_ids`、対応する `topic_ids`、`study_design`、`study_context`、`key_findings_ja`、`limitations_ja`、`daily_life_example` を持ちます。

`study_context.type=study_context` は実際に研究した対象と比較条件です。一方、`daily_life_example.type=illustrative_scenario`、`observed_in_a_study=false` は編集上の想定例です。後者を被験者の体験談や検証済みの生活指導として転記しないでください。

今回の `review_scope=abstract`、`review_method=AI_assisted_single_review` はAI支援による一回の予備読解です。独立した二重選別や専門家の監修を意味しません。`formal_evidence_certainty=not_assessed` を保持します。

## 検索候補と履歴

`data/literature/candidates.json` は検索で取得したレコード台帳です。候補IDは `MED:PMID` などのデータベースIDで、一つの研究のプレプリント・刊行版を自動で統合したものではありません。`machine_retrieved_not_screened` の候補は採用した根拠ではありません。

`data/literature/search_log.json` は実際に実行した300回の検索式、API URL、取得件数相当の候補ID、実行状態を保存します。元の概念検索200件と重点調査100件を区別します。補足検索の個別時刻が取得できていないものは `null` とし、実行run IDと日付を保存しています。

各検索の上位5レコードに限定した探索です。引用数は取得時点の指標で、研究の質や真偽の判定には用いません。論文全文・抄録原文は正本に保存しません。

## 件数と検証

`data/research/coverage.json` は今回の範囲と残る作業を数値化しています。`next_queue.json` は未読解テーマの一覧で、自動スケジュールではありません。

```bash
python scripts/validate.py --export build
python scripts/validate_research.py --export build
```

正本JSONを更新して再出力します。`research/` のPSVは今回の編集原稿で、通常は修正して再取り込みせず正本を編集してください。一度限りのインポータは二重適用を拒否します。候補・読解メモ・資料・件数の更新は相互参照を維持して行ってください。
