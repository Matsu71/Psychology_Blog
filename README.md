# Psychology Blog — 人間の科学・記事制作データベース

**最終目標：一般向けに面白く、科学的根拠をたどれる300記事。**

28分野・300テーマ。出典273件。出典未登録0テーマ。

本文26件、主張対応表26件。原文照合後の改稿10件。公開承認済み0件。

- [記事の現在地](docs/ARTICLE_PROGRESS.md)
- [原文照合と注意点](docs/SOURCE_CHECKS.md)
- [次の作業](docs/NEXT_STEPS.md)
- [順位](docs/RANKINGS.md) / [データ設計](docs/DATABASE_ARCHITECTURE.md)

出典登録、抄録読解、本文の確認範囲、原稿編集、公開判断を分離します。相関と因果、研究場面と応用例、同じ試験の別版を区別し、未確認情報を推測しません。

テーマはdata/topics、出典はdata/sources.json、読解はdata/research/source_text_checks.json、原稿はarticles/manuscripts、根拠表はdata/articles/claimsです。旧入力とGit履歴、テーマのID・題名・順序を維持します。

```bash
python scripts/apply_editorial_pass.py
python scripts/validate.py
python scripts/validate_research.py
python scripts/validate_round3.py
python scripts/validate_editorial_pass.py
```

スクリプトは編集入力を反映するもので、科学的な正しさを自動認定しません。公開サイトへの自動配信・定期実行は設定していません。
