# GitHubを正本にする研究データ設計

更新: 2026-09-11。GitHubを、変更履歴のある研究用コンテンツデータベースとして使います。利用者の個人情報、閲覧履歴、頻繁に更新するカウンタ、複数利用者が同時に書くトランザクション用DBとは分けます。

## 正本・関係・派生物

```text
data/
  categories.json             分野ID、順序、テーマファイルの場所
  topics/01_sleep.json ...     分野別のテーマ正本。既存ID・題名・順序を維持
  sources.json                出典の書誌正本。DOIを重複登録しない
  source_assessments.json     読んだ範囲、方法上の情報、未確認事項
  evidence/<category>.json    テーマと出典の多対多対応、関連性、使える範囲
  evidence/catalog.json       対応ファイルの目録
  research/briefs.json         旧68件の読解メモ（保持）
  research/source_reviews.json 第3回の書誌・抄録メモ
  research/coverage.json       現在の件数・確認範囲
  research/history/           前の調査段階の小さな集計
  literature/catalog.json     候補・検索履歴のファイル目録
  literature/round3/          新規候補・検索ログを100件単位で分割
  index/topics.json           AIや表示用の軽量索引（再生成可能）
  rankings/                  出典優先度、50テーマの編集評価、300テーマの調査順
  storage_policy.json        このプロジェクト内部の容量目安
  storage_report.json        実測サイズ（Gitの履歴は含まない）
```

書誌を各テーマへ何度もコピーしません。テーマは`source_ids`を参照し、出典とテーマの関係にだけ関連性を持たせます。同じ論文でも、ある問いには直接の根拠、別の問いには背景説明にしかならないためです。

既存の`source_ids`と`research_brief_ids`は互換性を保ちます。新しい詳細は`source_review_ids`と`evidence`に分離しました。資料付きかどうかと、その資料をどこまで読んだかは別の状態です。既存の`search_pending`は「出典未登録」の互換ラベルで、検索を一度も実施していないという意味ではありません。

`schema_version=1.0`はファイル形式の互換性を示します。ランキングの式は別の`scoring_version`で管理します。新しい必須項目や破壊的変更が必要になったらスキーマを更新し、移行手順・互換出力を付けます。

## 例：テーマと論文の対応

```json
{
  "topic_id": "PSY-SLP-004",
  "source_id": "SRC038",
  "relation_role": "direct_or_targeted_evidence",
  "relevance_1_to_5": 5,
  "relevance_scope": "anchor_question_checked",
  "formal_evidence_certainty": "not_assessed"
}
```

これは対応関係の一部を示す例です。書誌、研究結果、対象、限界、本文で確認した箇所はそれぞれ出典・読解メモ・評価レコードを参照します。未確認値には`null`や明示的な未評価状態を使い、0点や空文字で「効果なし」を表現しません。

## 容量と分割方針

2026-09-11にGitHubの公式文書を確認しました。

- 通常Gitでは50 MiBを超えるファイルに警告、100 MiBを超えるファイルはブロックされます。ブラウザ経由は25 MiB以下です。[公式：大きいファイル](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
- 同ページはリポジトリを理想的には1 GB未満、強く推奨する目安として5 GB未満としています。これを有料プランの固定容量やファイル一つの上限と混同しません。
- 別のリポジトリ制限のページには`.git`圧縮サイズ10 GB、単一オブジェクト推奨1 MB、1回のpushは2 GBという異なる範囲の目安・制限があります。[公式：リポジトリ制限](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits)

今回の設計は公式上限よりかなり手前で、通常のJSONは1 MiBを超えたら分割検討、新しい候補台帳は100件を一つのファイルにします。旧候補ファイルは約1 MB未満なので無理に再配置せず、カタログ経由で新しい分割ファイルと合わせて読みます。件数が増えた出典・読解メモも、同様に100～数百レコードのID範囲またはカテゴリ単位へ移せます。今は230前後の出典を1件1ファイルにして管理ファイルを増やす必要はありません。

これは内部の運用目安であり、GitHubのハード上限ではありません。容量は文字数でなくUTF-8のバイト数を測ります。更新を重ねるとGitの履歴も増えるため、現在のファイル合計だけで余裕を判断しません。巨大な生成済み統合ファイル、論文PDF、画像、原文キャッシュは正本に置かず、必要な場合は別の配信・保管場所を使います。

## AIが読む順番

`AGENTS.md` → 軽量索引 → 対象カテゴリのテーマ → そのテーマの上位3～5出典 → 必要な読解メモ、という順に読みます。検索候補を全部プロンプトに入れません。

```bash
python scripts/query_database.py topic PSY-SLP-004 --limit 5
python scripts/query_database.py source SRC038
python scripts/query_database.py queue --limit 10
```

テキスト形式だからというだけで効率が良いわけではありません。小さな単位で選択的に取得でき、未知・推測・観察・因果の区別が明示されていることを重視します。将来はこの正本から検索インデックスやSQLiteを生成できます。生成物を正本として二重更新しません。

## 書き込み・検証・公開

変更前に最新コミットを確認し、1テーマの修正と出典・対応関係・集計を同じ変更単位で扱います。複数のAIが作業する場合は別ブランチまたはカテゴリで分担し、無条件の上書き・force pushをしません。IDを再利用しません。順位は正本の配列をソートせず、別ビューに生成します。

通常は正本編集 → 派生ビュー再生成 → 3つの検証スクリプト → 差分確認 → commitの順です。現在の自動検証は構文・ID・参照・件数・点数の再現・サイズを確認します。意味の重複、論文の真偽、全URLの到達性は別工程です。

`build/`は可搬用の出力です。第3回以降の完全版は`build/database/`に正本・評価・順位・全候補シャードを含みます。旧互換の単体`topics.json`だけでは追加の評価台帳・全候補を網羅しません。

将来のブログ公開時は、GitHubの正本から静的な配信用JSONを生成し、サイト側の配信層で読みます。各訪問のたびにGitHub APIで全台帳を取得・更新する設計にはしません。
