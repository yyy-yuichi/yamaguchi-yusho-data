# verification.md — I-1（000271730.pdf）検証結果

対象: `raw/000271730.pdf`（福祉有償運送・NPO等、山口県、4ページ=4団体）1本のみ。
SPEC.md §5 の完了条件1〜8について、実行結果を記録する。

## 実行環境

- 実行日時: 2026-08-07
- git commit: `7c21ce837716ee7a440facb49247b0b6cfaf0452`
- Python: `C:\Users\user\dev\udc2026\.venv\Scripts\python.exe` 3.13.12
- pdfplumber: 0.11.10
- 実行コマンド:
  ```
  C:\Users\user\dev\udc2026\.venv\Scripts\python.exe src\parse.py
  C:\Users\user\dev\udc2026\.venv\Scripts\python.exe -m unittest tests.test_verify -v
  ```
- 入力PDF: `raw/000271730.pdf`（136,476バイト、MD5 `c49543729e3122adbd935fa79260b3b7`、4ページ）
- 生の中間データ: `raw/text/000271730_p{1..4}.txt`（ページ単位の抽出テキスト、SPEC.md §4.4）
- 座標・罫線の実測記録: `evidence/20260807_explore_words_edges.txt`,
  `evidence/20260807_explore_hedges.txt`
- 目視確認用のページ画像（200dpi）: `evidence/20260807_page_render-{1..4}.png`
  （`pdftoppm -r 200` で生成。フォント代替の警告が出るが表示上の文字は正しく確認できている）

---

## §5-1 団体数の一致

`evidence/20260807_page_render-{1..4}.png` を目視し、各ページに登録番号1件ずつ、計4団体を確認した。

| ページ | 登録番号 | 名称 |
|---|---|---|
| p1 | 中山福第１号 | 特定非営利活動法人 豆たん |
| p2 | 中山福第3号 | 特定非営利活動法人 らいと |
| p3 | 中山福第４号 | 社会福祉法人 菊水会 |
| p4 | 中山福第６号 | 社会福祉法人 大島白壽會 |

`data/operators.csv` の行数（ヘッダ除く）: **4行**。目視の4団体と一致。

---

## §5-2, §5-3 自動テスト結果

`tests/test_verify.py` を `unittest` で実行した結果（全6件成功）:

```
test_authority_code_is_uniform ... ok
test_service_type_code_is_fukushi ... ok
test_no_representative_column_in_schema ... ok
test_representative_name_absent_from_all_outputs ... ok
test_count_kei_le_count ... ok
test_count_sum_matches_vehicles_total ... ok

Ran 6 tests in 0.429s

OK
```

車両合計の一致表（`vehicles.csv` の `合計` 以外の行を `count`/`count_kei` で合算した値 vs
`operators.csv` の `vehicles_total`/`vehicles_total_kei`）:

| registration_no | count合計(計算) | vehicles_total(CSV) | count_kei合計(計算) | vehicles_total_kei(CSV) |
|---|---|---|---|---|
| 中山福第1号 | 3 (車いす車2+セダン等1) | 3 | 2 (1+1) | 2 |
| 中山福第3号 | 10 (車いす車9+セダン等1) | 10 | 7 (6+1) | 7 |
| 中山福第4号 | 3 (車いす車1+セダン等2) | 3 | 2 (0+2) | 2 |
| 中山福第6号 | 1 (車いす車1) | 1 | 1 (1) | 1 |

**全4件一致。不一致0件。**

`count_kei <= count` の不変条件は、`count_kei` が空文字列でない全行（11行中、バス列該当は
0行のため11行全て）で成立を確認した。

---

## §5-4 登録番号の整合

| registration_no | service_type_code | authority_code |
|---|---|---|
| 中山福第1号 | 福 | 中山 |
| 中山福第3号 | 福 | 中山 |
| 中山福第4号 | 福 | 中山 |
| 中山福第6号 | 福 | 中山 |

`service_type_code` は全件 `福`（福祉有償運送ファイルと一致）。`authority_code` は全件 `中山` で同一。

---

## §5-5 全件突合

`evidence/20260807_page_render-{1..4}.png` を目視し、原本と `data/operators.csv` /
`data/vehicles.csv` を突き合わせた。

| 項目 | p1(中山福第1号) | p2(中山福第3号) | p3(中山福第4号) | p4(中山福第6号) |
|---|---|---|---|---|
| org_name | 特定非営利活動法人 豆たん ✓ | 特定非営利活動法人 らいと ✓ | 社会福祉法人 菊水会 ✓ | 社会福祉法人 大島白壽會 ✓ |
| service_area | 下関市全域（離島を除く） ✓ | 下関市 ✓ | 下関市 ✓ | 周防大島町（平成１６年１０月１日付けで合併された旧東和町に限る） ✓ |
| valid_to | 2027-04-23 ✓ | 2027-10-10 ✓ | 2028-06-22 ✓ | 2026-08-31 ✓ |
| 車種別台数(所有) | 車いす車2(1)+セダン等1(1)=合計3(2) ✓ | 車いす車9(6)+セダン等1(1)=合計10(7) ✓ | 車いす車1(0)+セダン等2(2)=合計3(2) ✓ | 車いす車1(1)=合計1(1) ✓ |
| 持込 | 0台 ✓ | 0台 ✓ | 0台 ✓ | 0台 ✓ |

**全件一致。** 登録番号は 第1号・第3号・第4号・第6号のみ存在し、**第2号・第5号は欠番**であることを
`data/operators.csv` の内容（4行、上記4件のみ）で確認した。

### 旅客範囲7列（SPEC.md明示要求を超える追加確認）

`extract_scope_flags` のロジックがページごとに異なる凡例レイアウト（後述バグ6参照）に依存するため、
SPEC.md §5-5 の明示列（registration_no/org_name/service_area/valid_to/車種別台数）には
含まれていないが、`scope_*` 7列も4ページ全件を画像で目視突合した。

| registration_no | 原本のマーク（目視） | scope_*列（CSV） |
|---|---|---|
| 中山福第1号 | イ ニ ホ ヘ | scope_i_physical=1, scope_ni_care=1, scope_ho_support=1, scope_he_checklist=1, 他0 ✓ |
| 中山福第3号 | イ ニ | scope_i_physical=1, scope_ni_care=1, 他0 ✓ |
| 中山福第4号 | （マーク無し） | 全列0 ✓ |
| 中山福第6号 | ニ ホ | scope_ni_care=1, scope_ho_support=1, 他0 ✓ |

**全件一致。**

---

## §5-6 日付の健全性

| registration_no | valid_from | valid_to | valid_from<valid_to | 期間長 |
|---|---|---|---|---|
| 中山福第1号 | 2024-04-24 | 2027-04-23 | 成立 | 3年(-1日) |
| 中山福第3号 | 2024-10-11 | 2027-10-10 | 成立 | 3年(-1日) |
| 中山福第4号 | 2025-06-23 | 2028-06-22 | 成立 | 3年(-1日) |
| 中山福第6号 | 2023-09-01 | 2026-08-31 | 成立 | 3年(-1日) |

全件で `valid_from < valid_to` が成立。年は2024〜2028年の範囲内で、2000年代前半・2100年代の
異常値は無い。期間長は全件「3年」（起算日の前日を満了日とする表記のため実質3年-1日）で、
SPEC.md §3.4(d)の「改善命令・事故・業務停止命令のいずれも無い場合=3年」のパターンと整合する。
外れは無いため警告事項も無い。

---

## §5-7 事務所情報の不一致の列挙

`SPEC.md` rev.3（§3.6）で、以前は `office_mismatch` 1種類だったフラグが2種類に分かれた。
比較の前処理は「1. 全角→半角、2. 空白（全角・半角）をすべて除去」の2段のみで、
これで解消する差はフラグを立てない。前処理をしても一致しない場合、`office_name` が
不一致なら `office_mismatch`、`office_name` は一致し `office_location` のみ不一致なら
`office_notation_diff` とする（住所を吸収する正規化はしない。§3.6の注記どおり、
「同じ場所」と主張しないため）。`src/parse.py` をこの規定に合わせて修正した。

`operators.csv` の `flags` 列:

| registration_no | 上部office_name | 車両欄office_name | 上部office_location | 車両欄office_location | flags |
|---|---|---|---|---|---|
| 中山福第1号 | 豆たん介護センター | 豆たん介護センター | 下関市内日下１０２７－３ | 下関市内日下1027-3 | (空) |
| 中山福第3号 | 特定非営利活動法人 らいと | 特定非営利活動法人らいと | 下関市秋根南町１丁目１－５ | 下関市秋根南町１丁目１－５ | (空) |
| 中山福第4号 | まんてんの星 | まんてんの星 | 下関市菊川町大字田部５３６番地１ | 下関市菊川町大字田部５３６－１ | `office_notation_diff` |
| 中山福第6号 | 大島白壽會 | 桑陽病院腎友会 | 山口県大島郡周防大島町大字西方1623番地の３ | 防府市車塚町3番２０号 | `office_mismatch` |

**`SPEC.md` §3.6 の期待値と完全一致（`tests/test_verify.py` の `OfficeFlagsTest` で自動テスト化済み）:**

- 中山福第1号・第3号: 全角/半角・空白の差のみで前処理により解消 → フラグなし
- 中山福第4号: `office_name`（まんてんの星）は一致、`office_location` のみ
  「５３６番地１」/「５３６－１」で不一致 → `office_notation_diff`
- 中山福第6号: `office_name` 自体が不一致（大島白壽會 ≠ 桑陽病院腎友会） → `office_mismatch`
  （`SPEC.md` §3.6 に既知の異常として明記されている、別組織・別市町。消さずに残っていることを確認）

前回セッションで「要確認事項」として保留していた中山福第4号の扱いは、
`SPEC.md` rev.3（チャット側）で `office_notation_diff` として規定され解消した。

---

## §5-8 代表者氏名の不出力確認

`tests/test_verify.py` の `RepresentativeNameNotOutputTest` で、4ページ全件について
「代表者の氏名」ラベルの右側の語をPDFから動的に抽出し、`data/operators.csv` /
`data/operators.json` / `data/vehicles.csv` / `data/vehicles.json` のいずれにも
含まれていないことを確認した（実際の氏名はこのファイルにも書かない）。

- `test_representative_name_absent_from_all_outputs`: 4ページ全件で氏名文字列・氏名の一部分の
  いずれも出力ファイルに含まれないことを確認 → **成功**
- `test_no_representative_column_in_schema`: 列見出しに「代表者」「氏名」等を示唆する語が
  無いことを確認 → **成功**

`OPERATORS_COLUMNS` / `VEHICLES_COLUMNS`（`src/parse.py`）にも代表者氏名に相当する列は無く、
`src/parse.py` は「代表者の氏名」ラベル自体を検索・抽出する処理を一切持たない
（パース段階で最初から捨てている）。

---

## まとめ

SPEC.md §5 の完了条件1〜8を全て満たした。

1. 団体数一致（4件） ✓
2. 車両合計照合（自動テスト） ✓ 不一致0件
3. count_kei ≤ count（自動テスト） ✓ 全行成立
4. 登録番号整合 ✓ service_type_code全件「福」、authority_code全件「中山」
5. 全件突合 ✓ 4団体全項目一致、欠番(2号・5号)を確認
6. 日付健全性 ✓ 全件成立、警告なし
7. 事務所情報不一致列挙 ✓ `SPEC.md` rev.3（§3.6）の2種類のフラグに対応。
   中山福第4号=`office_notation_diff`、中山福第6号=`office_mismatch`、他2件はフラグなし。
   期待値どおり一致（自動テスト `OfficeFlagsTest` で確認）
8. 代表者氏名不出力 ✓ 自動テストで確認
