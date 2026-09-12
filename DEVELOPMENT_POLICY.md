# 共通開発・ホスティング方針

このリポジトリは、Matsu71 配下のサービス開発における共通方針に従う。

## GitHub Pages

GitHub Pages で公開するサービスは、特別な理由がない限り次を標準とする。

- 公開ブランチ: `main`
- 公開フォルダ: `/(root)`
- リポジトリ直下に公開用の `index.html` を置き、GitHub Pages の設定だけで公開できる状態を維持する。
- `docs/` は原則として仕様書、調査資料、設計資料などの文書用ディレクトリとして扱い、Pages の公開先には使わない。
- GitHub Actions は Pages へのデプロイ自体には原則必須とせず、テスト、lint、型チェック、ビルド検証などの CI 用途では必要に応じて利用する。
- ビルドツールを使用する場合も、GitHub Pages 対象サービスでは最終的な公開物を `main / (root)` から配信できる構成を優先する。

## 例外

- Cloudflare Pages、Cloudflare Workers など Cloudflare と連携し、Cloudflare 側でホストするサービスはこの `main / (root)` 方針の対象外とする。Cloudflare に適したビルド・デプロイ構成を優先する。
- SSR、API、サーバー実行など GitHub Pages では成立しない要件がある場合は、無理に `main / (root)` に合わせず、適切なホスティング方式を採用する。
- 例外を採用する場合は、README または関連ドキュメントに理由と公開方法を明記する。

## 運用原則

新規サービスおよび今後の改修では、ホスティング方式を決める際にまずこの方針を確認する。GitHub Pages を使う場合は `main / (root)` をデフォルトとし、Cloudflare ホスト等の場合のみ別構成とする。
