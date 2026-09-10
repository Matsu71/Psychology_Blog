# データ辞書

## 構造

正本は `data/topics/` の分野別JSONです。`data/categories.json` が順序・ファイル名・件数を管理し、出典は `data/sources.json` に正規化しています。安定IDを維持し、件数だけを増やす言い換え・再採番・無断の並べ替えは避けます。

## テーマの項目

| 項目 | 意味 |
|---|---|
| `id` | `PSY-分野略号-連番` の安定ID。削除した番号も再利用しない。 |
| `title_ja` | 日常の疑問を入口にした記事タイトル候補。問いであって結論ではない。 |
| `concepts_en` | 研究で使われる英語の概念・キーワード。 |
| `angle_ja` | 記事で何を比較・説明・検討するか。 |
| `search_query` | 追加の文献検索に使える英語検索文字列。実行済みの検索ログではない。 |
| `priority` | 編集上の調査優先度。1=初期優先、2=発展。効果の強さや確実性ではない。 |
| `source_ids` | 関連資料への入口。背景資料も含み、各主張の直接的根拠の対応表ではない。空配列は出典未確認。 |
| `caution_ja` | 因果の飛躍、個人差、研究の限界、健康上の注意など。 |

`category_id` と `schema_version` は各分野ファイルの親オブジェクトに置きます。

## 全テーマに適用される状態

`data/manifest.json` の `topic_defaults` を全テーマに適用します。初版は全200件が `record_status=theme_candidate`、`evidence_appraisal=not_assessed`、`publication_ready=false` です。

`research_status` は、`source_ids` があれば `reference_linked`、なければ `search_pending` です。**reference_linkedは、効果確認済み・論文全文確認済み・公開可能という意味ではありません。** エクスポート時には、この状態と分類情報を各レコードへ明示的に展開します。

## 資料の項目

`id`、`title`、`authors_display`、`year`、`journal`、`source_type`、`doi`、`url`、`verified_via_url`、`verification_scope`、`notes_ja` を持ちます。著者は表示用で、`et al.` は省略を示します。未確認のDOIや公的ページの刊行年は `null` とし、推測しません。`year` は原則掲載号の年で、オンライン初公開年と異なる場合があります。

`source_type` は `journal_article`、`official_health_information`、`official_bibliography` のいずれかです。

| `verification_scope` | 実施した確認 |
|---|---|
| `official_page_reviewed` | 公的機関の説明ページまたは文献一覧を閲覧。原著試験の査読・再評価ではない。 |
| `bibliography_verified` | 信頼できる参照先で書誌情報を確認。原論文の抄録・全文は未精査。 |
| `abstract_reviewed` | 論文の抄録を確認。全文・補足資料・分析データの検証ではない。 |
| `article_text_reviewed` | 論考の本文を閲覧。体系的な批判的評価や解析再現は未実施。 |

`verified_via_url` は実際に確認したページです。`url` がDOIの解決先でも、そこを全文閲覧できたとは限りません。資料台帳の `accessed_on` は共通の閲覧日、`evidence_appraisal` は現時点の未評価状態です。

`correction_notes_ja` は確認できた訂正告知のメモです。項目がない資料が「訂正・撤回なしと確認済み」という意味にはなりません。`title_form=editorial_short_title` の場合、正式題名はリンク先で確認します。

## 使い方

```bash
python scripts/validate.py
python scripts/validate.py --export build
```

後者は、検証に成功した場合に `build/topics.json`、`build/topics.md`、`build/validation_report.json` を生成します。統合JSONには分類、状態、出典台帳も含まれます。生成物を修正せず、正本を修正して再生成してください。更新時は `manifest.json` と各分類の件数も更新します。
