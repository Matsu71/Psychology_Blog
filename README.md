# Psychology Blog — 人間の科学・記事制作データベース

**最終目標：世界最高水準の心理学情報・トピックサイト。300テーマは最初の制作対象です。**

28分野・300テーマ。出典320件。出典未登録0テーマ。

本文60件、主張対応表60件。 限定した原文照合記録あり20件。公開承認済み0件。

- [記事の現在地](docs/ARTICLE_PROGRESS.md)
- [次の作業](docs/NEXT_STEPS.md)
- [原文照合と注意点](docs/SOURCE_CHECKS.md)
- [順位](docs/RANKINGS.md) / [データ設計](docs/DATABASE_ARCHITECTURE.md)

原稿の存在、限定した主張の照合、独立した点検、公開承認は別の状態です。構造検証は科学的正しさを自動認定しません。

テーマはdata/topics、書誌はdata/sources.json、記事の参照先はdata/articles/catalog.jsonが正本です。題名・ID・テーマの順序を維持し、改稿案を独立記事として水増ししません。

```bash
python scripts/build_research_views.py
python scripts/reconcile_article_progress.py
python scripts/validate.py
python scripts/validate_research.py
python scripts/validate_round3.py
python scripts/validate_editorial_pass.py
python scripts/reconcile_article_progress.py --check
```

全文・抄録の原文は公開データに転載しません。想定例と実際の研究場面を分けます。定期的な自動執筆は設定していません。サイトの生成・配信は、下記の読者版の説明を参照してください。

## 追加原稿・改稿案

- [CONTINUATION_20260911B](docs/CONTINUATION_20260911B.md)
- [CONTINUATION_20260911D](docs/CONTINUATION_20260911D.md)
- [CONTINUATION_DAILY_LIFE_20260911](docs/CONTINUATION_DAILY_LIFE_20260911.md)
- [CONTINUATION_LEARNING_20260911](docs/CONTINUATION_LEARNING_20260911.md)

## 読者向けサイト（2026-09-14）

[制作プレビュー](https://matsu71.github.io/Psychology_Blog/) / [参考サイト比較](docs/redesign/REFERENCE_REVIEW.md) / [編集基準](docs/redesign/EDITORIAL_STANDARD.md)

8つの入口、28分野、300テーマ。読者向け本文は76テーマ（従来の60原稿に、新稿16テーマを追加。そのうち既存22テーマは読者向けに改稿）。原稿数は公開承認数ではありません。

タイトル・導入・見出しは既存媒体の情報設計を参照して再設計しました。正本の題名・ID・元原稿は保持し、表示タイトルと読者版を別管理しています。全ページは編集確認中のためnoindexです。

配置は main / (root)。Reader siteワークフローが変更されたソースを検証・生成し、生成物をmainへ保存してPagesの再ビルドを要求します。記事の公開承認を自動で付与するものではありません。手元で再生成する場合は次の順序です。

```bash
python scripts/register_reader_sources.py
python scripts/build_research_views.py
python scripts/reconcile_article_progress.py
python scripts/build_reader_site.py
python scripts/test_reader_site.py
```

構造点検は [READER_SITE_TESTS.json](docs/READER_SITE_TESTS.json)、実ブラウザ点検は [READER_BROWSER_TESTS.json](docs/READER_BROWSER_TESTS.json)。科学的真偽や医療監修を自動認定するテストではありません。
