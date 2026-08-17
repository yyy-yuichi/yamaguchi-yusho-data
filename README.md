# yamaguchi-yusho-data

UDC2026（アーバンデータチャレンジ2026）応募作品①のデータ基盤リポジトリ。

## UDC2026 に何を出すのか

作品①は、山口県の公共交通における「供給側データ」の欠落を埋めるアプリ／サービスである。
GTFS-JP の整備状況・鮮度、交通空白、福祉輸送（UD タクシー・福祉有償運送）の供給を突き合わせ、
市町単位で可視化する。

- **想定利用者**: 県・市町の公共交通担当部局、地域の交通事業者
- **差別化**: 運行管理者としての制度知識（自家用有償旅客運送の登録要件・様式・通達）を
  データ整備に反映している点
- **狙う賞**: GTFS 賞、BODIK 賞

## 公開情報と開発用診断

[GitHub Pages](https://yyy-yuichi.github.io/yamaguchi-yusho-data/)は、作品を使う人が必要とする
機能、利用価値、現在の到達点、出典、日付、限界を中心に構成する。UDC2026一次審査の観点は
応募説明へ事実として反映するが、応募者による数値の自己採点はPagesへ掲載しない。

改善優先度を検討する機械可読な診断資料は`data/work1_award_scorecard.json`、共通形式は
`data/award_scorecard_schema.json`に保持する。リポジトリ自体は公開されているため秘密情報では
ないが、作品の機能や公式評価と誤解されないよう、利用者向け公開成果物とは分離する。
公式根拠は[UDC2026作品募集要領](https://urbandata-challenge.jp/udc2026_entry)である。

## このリポジトリの役割

このリポジトリは作品①のうち、**「自家用有償旅客運送者の登録簿」の機械可読化**と、
**市町別の登録供給ビュー**、**公式GTFS/GTFS-JP確認状況**、**岩国市・光市関連2フィードの
GTFS供給比較**、**市町別の交通協議前確認メモ**までを担う。
中国運輸局が PDF でのみ公表している登録簿を構造化し、山口県の市町別に供給量
（団体数・車種別の車両台数）を機械可読なデータとして取り出したうえで、山口県公式19市町
から1市町を選んで団体・車両・原本を追跡できる画面（`docs/index.html`）を公開用HTMLとして
提供している。同じ画面で、公式一次資料から確認できたGTFS/GTFS-JPフィードの状況と、
岩国市・光市関連2フィードに収録された構造3指標・同じ7実日付の予定運行便も確認できる。
光市公式GTFSの広域生活交通は周南市内停留所も含むため、周南市メモからも同じ光市フィード全体値を
関連情報として確認できる。周南市内だけの値へ分割・推計はしない。
登録簿PDFの処理やCSV作成、市町別ビューの実装は作品を成立させるための手段であり、
このリポジトリ単体を UDC2026 への提出作品の完成とは扱わない。提出物の中心は、
利用者が市町別の供給状況と公開データ上の空白を確認できる静的アプリ／サービスである。

## 市町別 交通協議前確認メモ（WORK1-TASK-MEMO-1）

[`docs/municipality-memo.html`](docs/municipality-memo.html)は、既存の公開JSONだけから、選択した
市町について「いま確認できる範囲」「登録簿上の供給」「GTFSの公開確認状況」「測定済み指標」
「協議前に次に確認すること」を一枚に構成する。さらに、登録簿記録あり/0件とGTFS確認済み/
確認範囲では未確認の4状態に応じて、共有する事実、次の確認、外部分析へ渡す条件を示す。
市町をURLに保持でき、共有URLのコピーと印刷・PDF保存に対応する。登録0件やGTFS未確認を
サービスの不存在とせず、指標のない市町へ値を補完しない。外部サービスへ自動送信しない。

- 公開画面: <https://yyy-yuichi.github.io/yamaguchi-yusho-data/municipality-memo.html>
- 入力: `docs/data/municipal_supply.json`、`docs/data/municipality_gtfs.json`、
  `docs/data/gtfs_feeds.json`、`docs/data/gtfs_supply_metrics.json`
- 原本・既存公開JSON・計算値はこの画面から更新しない
- 作品②からの入力は0件

## 制度区分

自家用有償旅客運送には、根拠・要件が異なる区分が複数ある。
このリポジトリではまとめて「福祉輸送」と呼ばず、区分ごとに扱う。

- **交通空白地有償運送** — 交通が不便な地域で、自治体・NPO等が有償で運送する制度
- **福祉有償運送** — 単独では公共交通機関を利用できない方を対象に、自治体・NPO等が
  有償で運送する制度

対象は山口県分 4 ファイル（上記2区分 × 市町村営・NPO等）。

## 現在地（WORK1-OFFICIAL-GTFS-COVERAGE-EXTENSION-1、2026-08-13時点）

このリポジトリはI-1〜I-4までの市町別ビューに、受入済みGTFS検査・供給指標を使う
SUPPLY-VIEW-1の比較画面を追加し、RELEASE-1でGitHub Pagesへ公開した。公開URLに対する
Edge/CDPの1440×1600・390×844実確認28/28とCodexの独立読戻しを終え、`run_record.md` rev.37で
受入済みである。この公開範囲は、
UDC2026応募全体の終了条件（作品概要エントリー・本応募・第三者検証公開・受賞）の達成を
意味しない。作品の課題・使い方・利用価値・類似サービスとの役割差は `docs/entry.html`、詳細な工程・残作業・終了条件は
`docs/status.html` に表示している。

作品①と別作品の作業境界、deny-by-defaultの検査方法、全体DAGは[`WORK_SCOPE.md`](WORK_SCOPE.md)を
正とする。このChatとリポジトリは作品①だけを扱い、別作品のパス・ファイル・Git履歴を入力にしない。

- **I-1**: 登録簿4PDFの機械可読化（23団体、`data/vehicles.csv` 90行、実車両136台、軽20台）
- **I-2**: 山口県公式順19市町から選べる市町別の登録供給ビュー（登録あり15/19市町）
- **I-3**: `docs/status.html` から `docs/index.html` へ確実に到達できる現況説明
- **I-4 / WORK1-OFFICIAL-GTFS-COVERAGE-EXTENSION-1**: 公式GTFS記録8件を根拠に、19市町を
  公開取得可能7、認証必要2、存在確認済み・一般配布なし9、公式記録あり・現在取得不能1へ区分
- **SUPPLY-VIEW-1 / RELEASE-1**: 岩国市関連・光市関連フィードの構造3指標と
  2026-04-06〜2026-04-12の予定運行便を、切替操作なしで根拠・状態とともに確認できる公開比較画面
- **ENTRY-PAGE-1**: 作品名、81字概要、対象者、課題、3段階の使い方、使用データ、
  利用価値、現在の到達点、限界を初見の人向けに結ぶ応募説明ページ。Pages run
  `31462820456`と公開実Edge 30/30をCodex受入済み
- **WORK1-FRESHNESS-1（継続確認）**: 受入済み4登録簿PDF・3 GTFS ZIPを公式配布と
  継続照合し、原本を採用し直さずに状態だけを区別する。GitHub Actionsの週次・手動検査と
  Pagesからの履歴導線を運用する
- **WORK1-TASK-MEMO-1**: 既存の作品①公開データを、市町別の交通協議前確認メモとして
  共有・印刷できる実務向け出力へ変換する
- **WORK1-GTFS-COVERAGE-2**: 未確認14市町の公式資料を再探索し、新規採用0件を記録。
  受入済み光市GTFSの広域生活交通について、周南市内31乗降停留所ID・17停留所名を確認し、
  原本・実測値を増やさず周南市を関連フィードへ接続する
- **WORK1-OFFICIAL-GTFS-COVERAGE-EXTENSION-1**: 未確認13市町を公式一次情報から再調査。
  人間承認後にJRバス中国公式ZIP 1件を手動受入し、全19市町を4つのアクセス状態へ更新する。
  非公開・認証必要・現在取得不能の原本や値は補完しない。専用5 / 5、全174 / 174テスト成功
- **WORK1-GTFS-COVERAGE-AUDIT-1**: 固定HEADと公開配信をread-onlyで監査し、P0 0件、P1 0件、
  P2 1件でGO。P2の有限工程表示は比較第2版で継続改善モデルへ訂正
- **WORK1-AWARD-COMPARISON-2**: 受け入れ済み確認メモとGTFS範囲再確認を現行証拠へ反映し、
  根拠のない加点を行わず診断値を据え置いた。Actions・Pages・公開PC/スマホ読戻しまで最終受入済み
- **WORK1-AWARD-COMPARISON-AUDIT-2**: 固定HEADと公開配信をread-onlyで監査し、P0 0件、P1 0件、
  P2 2件でGO。公式用語の揺れと比較第2版の根拠節不足を検出
- **WORK1-AWARD-COMPARISON-TRACEABILITY-1**: 公式用語を「実用度・完成度・挑戦度」へ統一し、
  状況ページの根拠を`SPEC.md §20・§23`へ接続した。診断資料のbytesは変更せず、
  全150テスト、Actions・Pages、公開PC・スマホ読戻しまで最終受入済み
- **WORK1-AWARD-COMPARISON-TRACEABILITY-AUDIT-1**: 最終HEAD `a0fd712`をread-onlyで監査し、
  P0 0件、P1 0件、P2 1件でGO。P2は最終commit自身と後続run IDをrepo内へ記録できない自己参照
- **WORK1-RELEASE-ATTESTATION-1**: Pages成功後に、対象SHA、自身とPagesのrun ID、全テスト、
  公開4資産、7原本、作品①境界を機械可読JSONへ固定する。最新の90日保存artifactは
  [Work 1 release attestation Actions](https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/workflows/release-attestation.yml)
  から対象SHA名で確認する。初回GOはcommit `3dd7693`・run `31646234472`、151 / 151テスト、
  公開3 / 3、原本6 / 6、境界0件。artifactのrun IDはartifact自身を正本とし、repoへ書き戻さない
- **WORK1-RELEASE-ATTESTATION-AUDIT-1**: 固定HEAD `ed1f0b4`をread-only監査し、P0 0件・
  P1 0件・P2 3件でGO。P2はartifact期限・発見性、Pages報告SHA不一致の非停止、観測と宣言の混在
- **WORK1-RELEASE-EVIDENCE-HARDENING-1**: [監査証拠JSON](docs/data/work1_release_attestation_audit.json)、
  [可読snapshot](docs/data/release-attestation-ed1f0b4997acd19016da45e21c88821ef57bb365.json)、
  [Base64正本](docs/data/release-attestation-ed1f0b4997acd19016da45e21c88821ef57bb365.json.b64)を
  Git履歴・Pagesへ保存する。Pages報告SHA不一致をNO_GOとし、観測GETと運用宣言を分離する。
  この時点のattestation公開照合対象は6資産。診断資料の値は変更しない
- 初回強化commit `7b4527a8737166acebead845afc3a0549cc40227`はscope lock
  `31650244128`、Pages `31650243548`、attestation `31650293402`がsuccess。
  artifactはGO、151 / 151、公開6 / 6、原本6 / 6、保護3 / 3、Pages報告SHA一致、errors 0です。
  [初回公開受入記録](evidence/20260813_work1_release_evidence_hardening_public_acceptance.json)を
  反映した最終HEAD自身も同じworkflow artifactで外部証明し、run IDはartifactを正本とします。
- **WORK1-RELEASE-EVIDENCE-HARDENING-AUDIT-1**: 最終HEAD `618d636`をread-only監査し、
  P0 0件・P1 0件・P2 1件でGO。P2は最終artifactの90日失効と恒久的な発見経路の不足
- **WORK1-RELEASE-EVIDENCE-PERMALINK-1**: [最新の公開Release](https://github.com/yyy-yuichi/yamaguchi-yusho-data/releases/latest)へ、
  `work1-release-attestation.zip`、`attestation.json`、`attestation.md`、
  `release-provenance.json`、`SHA256SUMS.txt`を固定する。Release/tagは検証証拠の公開であり、
  UDC概要フォーム、本応募、BODIK登録ではない。5資産とtagを公開し、最終受入済み
- **WORK1-PUBLIC-INFORMATION-ARCHITECTURE-1**: Pagesを機能・利用価値・実装事実・出典・限界中心へ
  整理し、改善判断用の数値診断を利用者向け公開成果物から分離した。内部正本と計算検証は保持。
  commit `48f5f90`のscope lock `31669272686`、Pages `31669272478`、attestation
  `31669319617`はsuccess・GOで、151 / 151、公開4 / 4、原本6 / 6、保護3 / 3、errors 0。
  公開PC・スマートフォン、現行4 URLの200、旧3 URLの404まで受入済み
- **WORK1-PUBLIC-INFORMATION-ARCHITECTURE-AUDIT-1**: 固定HEAD `c8dc19d`をread-only監査し、
  P0 0件・P1 0件・P2 1件でGO。P2は現HEADのCI artifactと永続Releaseの証拠寿命の差
- **WORK1-SIMILAR-SERVICE-BENCHMARK-1**: GTFSデータリポジトリ、GTFS-GO、LINKS Mobilysを
  運営・開発主体と国土交通省の一次資料6件で比較した。作品①を、データ取得や高度分析の代替ではなく、
  登録供給・公式GTFS確認状況・日付・限界を市町別に揃える協議前確認の層として位置付けた。
  唯一・優劣・機能不存在は主張せず、内部診断値は変更していない
- **WORK1-SIMILAR-SERVICE-BENCHMARK-AUDIT-1**: 固定HEAD `0aeff8f`をread-only監査し、
  P0 0件・P1 0件・P2 3件でGO。P2はAPI詳細URLの取得不安定、GitHub Pages workflowの
  Node 20警告、現HEAD artifactと永続Releaseの証拠寿命差
- **WORK1-PRECONSULTATION-HANDOFF-1**: 市町別メモへ4状態別の共有事実・次の確認・分析へ渡す
  条件を追加し、公開・最終受入済み。GTFSデータリポジトリ、GTFS-GO、LINKS Mobilysは公式条件を
  確認して人が手動で選ぶ次工程とし、この画面からデータを自動送信しない。実装commit `5cb74d3`は
  scope lock・Pages・attestationが同一SHAでsuccess・GO、公開PC・スマホの4状態も受入済み

## 原本変更の継続確認（WORK1-FRESHNESS-1）

公開値の根拠にした7原本（4登録簿PDF・3 GTFS ZIP）を、`data/source_freshness_manifest.json`の受入済みbytes・SHA256と
公式配布ファイルの双方へ照合します。状態語彙は`unchanged`（一致）、`changed`（差異あり）、
`unavailable`（取得不能）、`oversize`（安全上限超過）、`invalid_baseline`（ローカル基準異常）です。
差異や取得不能を検出しても、原本・派生データ・公開値は**自動更新しません**。

- 固定確認日: 2026-08-12（初回ローカル実測、2026-08-11T22:47:51Z）
- 固定実測: 4 PDFは`unchanged`、2 GTFS ZIPはTLS接続不能のため`unavailable`、
  `changed`・`oversize`・`invalid_baseline`は0、終了コード2
- WORK1-FRESHNESS-1の集中16件を追加し、全102件のunittestが成功
- この固定記録は「現在も不変」という断定ではない。**最新状態**は
  [Source freshness Actions履歴](https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/workflows/source-freshness.yml)で確認する
- workflowは週1回と手動実行に限定し、権限は`contents: read`だけ。結果JSONをartifactへ保存し、
  commit・issue作成・Pages更新は行わない
- GitHub初回受入は[run 31547441902](https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/31547441902)。
  4 PDFが`unchanged`、2 GTFS ZIPが配布元のTLSエラーで`unavailable`、他3状態は0だった。
  GitHub上の`failure`表示は取得不能を通知する終了コード2であり、結果artifactの保存は成功している
- GitHub Pagesは[build run 31546971782](https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/31546971782)が成功。
  公開HTMLのcommit一致、1440×1600・390×844の表示、横方向overflow 0、console error 0を受入済み

## 処理状況

対象4ファイルすべてが、原本取得・全ページ確認・機械可読化・完了条件（`SPEC.md` §5）を通過済み。

- `000271730.pdf`（福祉有償運送・NPO等）
- `000230003.pdf`（福祉有償運送・市町村営）
- `000359215.pdf`（交通空白地有償運送・市町村営）
- `000268896.pdf`（交通空白地有償運送・NPO等）

- `data/operators.csv`: 23団体（4団体＋3団体＋12団体＋4団体）
- `data/vehicles.csv`: 90行、実車両合計136台（うち軽20台）
  - `vehicle_type=合計` の行は明細との照合用であり、実車両合計へ二重加算していない
- 自動テスト: ENTRY-PAGE-1実装時点で86件成功（`python -m unittest discover -s tests -v`。
  内訳は `verification.md` を参照）

## 公式GTFS/GTFS-JPのアクセス状況（2026-08-13再確認）

自治体、交通事業者、公式配布ポータルの一次資料を確認した。登録簿の団体・車両数
（上記の23団体・136台）とは別の集計であり、混同していない。

- 公式GTFS記録: **8件**
- **公開取得可能 7 / 19**: 岩国市、光市、周南市、山口市、萩市、防府市、美祢市
- **認証が必要 2 / 19**: 宇部市、山陽小野田市
- **存在確認済み・一般配布なし 9 / 19**: 下関市、下松市、長門市、柳井市、周防大島町、
  上関町、田布施町、平生町、阿武町
- **公式配布記録あり・現在取得不能 1 / 19**: 和木町
- 受入済み原本は岩国市・光市・JRバス中国の公式3 ZIP。JRバス中国ZIPは1,863,715バイト、
  SHA256 `9162224158a8a748d0365e850f2c0575c845a98063b7a469912c0a15b9201620`で固定し、
  危険パス0、暗号化0、CRC異常0を確認した
- JRバス中国は山口市・萩市・防府市・美祢市との関係を確認したが、フィード全18路線の値を
  各市内の供給量として既存比較へ混在させていない
- この4状態はアクセス条件であり、県内交通の完全収録を示すものではない。交通の充足度、
  達成度、市町の優劣や順位にも読み替えない

詳細（フィードごとの公開主体・アクセス条件・公式データ基準日・有効期間）は
`data/gtfs_feeds.csv` / `data/gtfs_feeds.json`、市町別の確認状況は
`data/municipality_gtfs.csv` / `data/municipality_gtfs.json`、画面での確認は
`docs/index.html` を参照。

## 岩国市・光市関連フィードのGTFS供給比較（SUPPLY-VIEW-1）

表示値の唯一の数値入力は `data/gtfs_supply_metrics.json` で、静的サイト用の
`docs/data/gtfs_supply_metrics.json` とバイト一致する。画面では岩国市関連・光市関連を列にし、
GTFS収録の交通ブランド情報、路線情報ID、乗降場所IDと、2026-04-06〜2026-04-12の
各実日付に予定された運行便を並べる。これらは確認したフィード全体の収録値であり、
市内だけの値、市内の全公共交通、実運行、利用者数、便利さ、順位、良否を示す値ではない。

## データソース・出典

- 中国運輸局「自家用有償旅客運送者の登録簿」
  <https://wwwtb.mlit.go.jp/chugoku/00001_00903.html>
- 対象は山口県分 4 ファイル（交通空白地有償運送・福祉有償運送 × 市町村営・NPO等）
- 取得日: `000271730.pdf` は2026-08-07、他3PDFは2026-08-09
- 上記を加工して作成したデータであり、**国土交通省が作成した成果物ではない**
- `raw/` 配下に山口県分4PDFの原本を出典保存している:
  `raw/000271730.pdf`、`raw/000230003.pdf`、`raw/000359215.pdf`、
  `raw/000268896.pdf`
- GTFS/GTFS-JP確認の出典: 山口県オープンデータカタログサイト
  <https://yamaguchi-opendata.jp/>、公共交通オープンデータセンター（ODPT）
  <https://ckan.odpt.org/organization/sentetsu_bus>

## 収録データ・利用画面

- `data/operators.csv` / `data/operators.json` — 登録団体ごとの主テーブル
- `data/vehicles.csv` / `data/vehicles.json` — 団体ごとの車両明細
- `data/gtfs_feeds.csv` / `data/gtfs_feeds.json` — 公式GTFS/GTFS-JPフィードの確認状況
- `data/municipality_gtfs.csv` / `data/municipality_gtfs.json` — 市町別のGTFS/GTFS-JP確認状況
- `data/gtfs_supply_metrics.json` — 岩国市・光市関連フィードの構造指標・同一週の日別予定便・根拠
- `docs/data/gtfs_supply_metrics.json` — 上記入力とバイト一致する静的サイト用JSON
- `docs/index.html` — 市町別の登録供給、公式GTFS確認状況、岩国市・光市の供給比較を確認できるHTML
- `docs/municipality-memo.html` — 市町別の根拠・限界・次の確認事項を共有・印刷できる協議前確認メモ
- `docs/status.html` — このリポジトリの現況説明（受入済み成果・残作業・終了条件の状況）
- `data/work1_award_scorecard.json` / `data/award_scorecard_schema.json` — 改善優先度を検討する開発用診断の正本JSONと共通形式（Pagesには配信しない）

**代表者の氏名は抽出も出力もしていない。**

## 開発

```
pip install -r requirements.txt
```

依存は `pdfplumber` のみ。pandas は使用しない。

### 独立再現・復旧ドリル

確定済み7原本だけを使い、対象commitの一時スナップショットで17生成物を削除・再生成して
内容を照合する。さらに一時スナップショット内の`docs/data/municipal_supply.json`を意図的に
欠落させ、既存ビルダーで復旧できることを確認する。正本worktreeの原本・生成物は削除しない。

```
python -B src/run_reproduction_drill.py --repo . --subject-sha HEAD --run-tests --output-dir reproduction-out
```

WindowsとLinuxのテキスト改行差は、完全byte一致と改行正規化後の内容一致を分けて記録する。
通常のローカル実行は内容一致を判定し、GitHubのUbuntu runnerは`--require-byte-match`により
17件すべての完全byte一致も必須にする。再現時の直接依存は`pdfplumber==0.11.10`へ固定し、
artifactへ実際のバージョンを記録する。新規原本の取得・自動採用・外部送信は行わない。
公開されたクリーンrunnerの結果は
[Work 1 independent reproduction drill](https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/workflows/reproduction-drill.yml)
で確認できる。

## ライセンス

派生データセット（`data/` 配下の CSV・JSON）は **CC BY 4.0**。

原データ（国土交通省中国運輸局が掲載する登録簿PDF）は、特記・別の権利表記がなく、
「公共データ利用規約（第1.0版）」PDL1.0 に準拠した条件で利用する。
国土交通省の[ウェブサイト利用条件](https://www.mlit.go.jp/link.html)と
[別ルール適用コンテンツ一覧](https://www.mlit.go.jp/page/kanbo01_hy_003657.html)、
一覧ページ・4PDFの権利表記を照合済み。確認記録は
`evidence/20260809_mlit_usage_terms.txt`に保存している。

利用時は出典を記載し、加工した場合はその旨も記載する。加工物を国土交通省が作成したかの
ように表示しない。`raw/*.pdf`は原データの現物であり、このプロジェクトのCC BY 4.0で
再許諾したものではない。

## 公開

`docs/` が GitHub Pages の公開ルート。現在のデモは
<https://yyy-yuichi.github.io/yamaguchi-yusho-data/> で公開中である。公開本体commitは
`18170b2a207940a889d527e29ef77f702c066b30`で、Pagesのbuild・deploy成功後に公開URLを
PC・スマホ幅で再検証した。**この現行デモの公開をUDC応募・受賞の完了として扱わない。**
外部提出は行っておらず、UDC2026応募全体の終了条件（T1〜T4）はいずれも未達である。
応募説明ページは `docs/entry.html`（公開URL:
<https://yyy-yuichi.github.io/yamaguchi-yusho-data/entry.html>）。公開ファイルのバイト一致と
PC・スマホの実Edge 30/30を確認済みである。進捗の詳細は `docs/status.html` を参照。

---

本リポジトリは UDC2026（アーバンデータチャレンジ2026）応募作品①のデータ基盤として作成した。

## 改訂点

旧版からの主な変更点と理由。

- 旧見出し「現在地（I-1〜I-4・SUPPLY-VIEW-1 Codex受入済み、2026-08-11時点）」を、
  RELEASE-1の公開到達性と公開ブラウザ受入を含む現在地へ更新した。

- SUPPLY-VIEW-1として、検証済みGTFS供給指標を数値二重管理せず画面表示し、対象範囲・日付・
  状態・原本ZIP・完全なSHA256・出典・利用条件を同じ比較区画から追跡できるようにした。
- 岩国市・光市の公式2 ZIPはGTFS-2で取得・検査済みであるため、旧「GTFS本体の解析は行っていない」
  を、2 ZIPは検査済み・船木鉄道本体は未取得という現在値へ訂正した。
- 自動テスト件数をSUPPLY-VIEW-1追加後の実測80件へ同期した。

- I-5でREADMEを受け入れ済みI-1〜I-4の現在地へ同期した。新機能は追加していない
  （SPEC.md §13）。
- 「処理状況（2026-08-09時点）」の見出しを「処理状況」に改め、日付を「現在の受入状況
  （I-1〜I-4・2026-08-10時点）」節へ移した。
- 自動テスト件数の固定値をI-5完了時点の実測値へ同期した。旧版の値はI-1（4PDF統合）時点の
  ものでしかなく、I-2〜I-4で追加したテストを反映していなかった。
- 冒頭の「このリポジトリの役割」を、登録簿の機械可読化だけでなく、市町別登録供給ビュー
  （I-2・`docs/index.html`）と公式GTFS/GTFS-JP確認状況の表示（I-4）まで含む現況に直した。
- 「現在の受入状況（I-1〜I-4）」節を新設し、I-1〜I-4それぞれの受入済み成果を短く要約した。
- 「公式GTFS/GTFS-JPの確認状況」節を新設し、I-4で確認できた3フィード・5/19市町・
  未確認14/19市町を、率や達成度の指標と呼ばず、GTFS不存在とも断定せずに記載した。
- 「収録データ」節を「収録データ・利用画面」に改め、`data/gtfs_feeds.*`・
  `data/municipality_gtfs.*`・`docs/index.html`・`docs/status.html`を追加した。
- 「公開」節に、このリポジトリ・ローカル実装をUDC応募・公開・受賞の完了として扱わない旨と、
  T1〜T4がいずれも未達である旨を明記した。
- 「背景」節の「同種の機械可読データは全国に存在しない」という記述を削除した。
  出典のない断定であり、確認していない。
- ライセンス節の「準備中」を、確認済みの内容（派生データはCC BY 4.0、原データは
  PDL1.0準拠）に置き換えた。中国運輸局掲載分への適用根拠と別ルール一覧を再確認し、
  旧版の未確認表示を解消した。
- 「取得した PDF 原本は `raw/` 配下に出典保存として含めている」という記述を、
  実在確認済みの山口県分4PDFに合わせた。
- 「福祉輸送（交通空白地有償運送・福祉有償運送）」という一括りの表現をやめ、
  両制度を別区分として説明する節を追加した。
- PDF処理を目的化しないよう、登録簿データは静的アプリ／サービスの供給側データの一部であり、
  このリポジトリ単体は提出作品の完成ではないと明記した。
