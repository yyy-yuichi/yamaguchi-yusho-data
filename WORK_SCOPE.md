# 作品①の境界と全体DAG

このリポジトリは作品①「山口県 市町別の登録供給ビュー」だけを扱う。作品②は別Chat・別リポジトリが
所有し、このChatからはパス、ファイル、Git履歴、公開物を調べない。比較時に受け取れるのは、人が
転記した短い評価結果だけである。

## deny-by-defaultの三重ガード

1. `AGENTS.md`が、作品②の探索・読取り・変更・コマンド実行・委譲を禁止する。
2. `src/check_work_scope.py`が、実行位置、Git root、origin、候補パスを作品①のallowlistへ照合する。
3. `.github/workflows/work1-scope-lock.yml`と`tests/test_work_scope.py`が、境界をpush・PR・手動実行で検証する。

スコープロックが失敗した場合は安全停止とし、拒否対象を見に行かない。Gitリポジトリの規則だけでは
Windows全体のACLを変更できないため、OSレベルの物理的隔離が必要な場合は別Windowsアカウントまたは
アクセス許可を分けたworkspaceを使う。本プロジェクトでは、Chat・repo・CIの操作境界をdeny-by-default
にして作品②を入力にしない。

## 全体の位置づけ

```mermaid
flowchart TD
    G["全体ゴール<br/>作成者本人名義でUDC2026受賞"]
    W1["作品①レーン<br/>このChat・このrepoだけ"]
    W2["作品②レーン<br/>別Chat・別repo<br/>本Chatからは不可視"]
    F["WORK1-FRESHNESS-1<br/>完了"]
    L["WORK1-SCOPE-LOCK-1<br/>境界を固定"]
    C1["WORK1-AWARD-COMPARISON-1<br/>作品①の比較用出力<br/>公開・最終受入済み"]
    A1["WORK1-AWARD-AUDIT-1<br/>固定HEADの独立監査<br/>GO"]
    M1["WORK1-TASK-MEMO-1<br/>市町別の協議前確認メモ<br/>ローカルGO・公開反映待ち"]
    A2["WORK1-TASK-MEMO-AUDIT-1<br/>固定HEADの独立監査<br/>次段階"]
    C2["作品②の比較用出力<br/>作品②Chatが所有"]
    D{"比較・注力判断<br/>人が決定"}
    S["選んだ作品を応募品質まで強化"]
    A["応募・受賞"]

    G --> W1
    G --> W2
    W1 --> F --> L --> C1 --> A1 --> M1 --> A2 --> D
    W2 --> C2 --> D
    D --> S --> A
```

作品①と作品②の間に直接の矢印はない。両作品が同じ評価形式の出力を人へ渡し、人だけが注力判断を行う。

## 現在地と次段階

- `WORK1-FRESHNESS-1`: 公開・最終受入済み。
- `WORK1-SCOPE-LOCK-1`: 公開・最終受入済み。作品①の操作境界を固定した。
- `WORK1-AWARD-COMPARISON-1`: 公開・最終受入済み。作品①の公開証拠だけで、実用度3.5、
  完成度4.0、挑戦度3.0、内部比較指数70.0 / 100を同一形式のスコアカードへ固定した。
- `WORK1-AWARD-AUDIT-1`: 固定HEAD、公開配信、採点計算、証拠リンク、作品②入力0件を
  read-onlyで独立監査し、GO判定済み。
- `WORK1-TASK-MEMO-1`: 既存の作品①公開データだけから、市町別に根拠・日付・限界・
  次の確認事項を一枚へ構成し、共有・印刷できる実務向け出力をローカル受入済み。公開反映待ち。
- `WORK1-TASK-MEMO-AUDIT-1`: TASK-MEMO-1公開受入後の一作業。固定HEAD、公開配信、
  代表3分岐、PC・390px・印刷、作品②入力0件をread-onlyで監査する。
- 作品①の公開出力: [受賞準備スコアカード](https://yyy-yuichi.github.io/yamaguchi-yusho-data/award-comparison.html)
- 作品①の実務出力: [市町別 交通協議前確認メモ](https://yyy-yuichi.github.io/yamaguchi-yusho-data/municipality-memo.html)
- 応募送信、本応募、BODIK登録、作品②の変更は別の人間承認・別Chatの責任範囲である。
