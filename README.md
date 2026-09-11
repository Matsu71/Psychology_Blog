# Psychology Blog — 人間の科学・記事制作データベース

**最終目標：一般向けに面白く、科学的根拠をたどれる300記事。**

28分野・300テーマ。出典281件。出典未登録0テーマ。

本文44件、主張対応表44件。 限定した原文照合記録あり20件。公開承認済み0件。

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

全文・抄録の原文は公開データに転載しません。想定例と実際の研究場面を分けます。定期執筆・自動サイト公開は設定していません。

## 追加原稿・改稿案

- [CONTINUATION_20260911B](docs/CONTINUATION_20260911B.md)
- [CONTINUATION_20260911D](docs/CONTINUATION_20260911D.md)
