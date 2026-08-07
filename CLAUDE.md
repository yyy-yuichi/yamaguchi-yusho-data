# CLAUDE.md(新 runtime)

## このディレクトリの位置付け

- 場所: C:\new_runtime\
- 役割: 公共工事積算業務の deterministic runtime
- ユーザー: Yuichi(積算業務の初心者)
- 旧環境: C:\archive\old_claude_runtime_2026-05-24\(参照のみ可、書き込み禁止)

## 必ず最初に読むべきファイル

1. C:\new_runtime\session_state.md
   bootstrap_log.md から導出した薄い head。最新状態の入口。矛盾時は bootstrap_log.md が正。

2. C:\new_runtime\open_items.md
   未解決項目の薄い索引。矛盾時は bootstrap_log.md が正。

3. C:\new_runtime\CLAUDE.md
   本ファイル(位置付け・禁止事項・原則)。

### 初手で全文読込しないもの

- C:\new_runtime\design_notes\design_2026-05-25.md
  設計前提に疑義がある時のみ、必要箇所だけ読む。初手で全文読込しない。
- C:\new_runtime\bootstrap_log.md
  これまでの作業ログ。append-only。履歴確認・MD5 根拠確認・closeout append の時のみ、必要箇所だけ読む。初手で全文読込しない。append は byte-exact append を原則とする。

## ユーザー前提(極めて重要)

- Yuichi は積算業務の初心者
- 専門用語や計算式の意味は分からない
- 原本 PDF を読んで内容を verify することはできない
- PowerShell 等のオペレーションは指示通り実行できる
- 旧 runtime のコンセプトも「初心者でも積算業務ができる」

ユーザーに業務知識を要求する手順を提案してはならない。

## 5 階層アーキテクチャ

- Layer 1: 自動収集(非知能、判断しない)→ Routines で実装
- Layer 2: raw 保存(append-only、削除禁止)→ C:\new_runtime\inbox\
- Layer 3: Yuichi 確認(分類のみ、判断しない)
- Layer 4: Claude 整理(main agent)→ Skills で原則固定化
- Layer 5: subagent(必要時のみ、探索/検証用)→ /goal で完了条件明示

核心原則: relevance を AI に決めさせない。raw は捨てない。

## 旧 runtime の本質的失敗

- subagent に「情報収集」と「重要性判断」を同時委任したことが核心
- 初心者ユーザーは subagent の relevance 判定を監査できなかった
- 結果: 何が捨てられたか追えない状態に

新 runtime ではこれを構造的に防ぐ。

## 禁止事項

- registry/ を LLM が直接書き換えない(Yuichi 承認経由)
- approved/ を上書き・削除しない
- inbox/ の raw データを削除しない(append-only)
- 旧 Vault から派生物(AI 判断要約等)を import しない
- hook を勝手に増やさない
- agent graph を作らない
- memory OS 化しない
- bootstrap_log.md の既存行を編集・削除しない(append-only)
- fetch/DL 結果の PASS を実体検証(disk MD5・bytes・Content-Type が GATE 条件充足)前に記録しない(S17J fetch_log 誤PASS→erratum supersede の再発防止)

## 継承する資産(import 対象)

import する:
- N=102 の正解値マスタ(旧 archive の dkgi_master.csv)
- formula スクリプト(旧 archive の bottomup_estimate.py 等)
- 過去収集された raw データ(歩掛 PDF、業者 HP、入札情報等)

import しない:
- subagent 定義
- hook スクリプト
- LLM のセッション履歴
- subagent が判定した要約データ

原則: 生データは持ち込む、AI 判断の派生物は持ち込まない。

## approved の意味

- 「正しいと保証する」印ではない
- 「N に加算可能な状態」を意味する
- 業務で使った結果が判明したら自動的に approved 扱い
- Yuichi が中身を判断する必要はない

## 使用する Claude Code 最新機能

- /goal: LLM のさまよう問題を構造的に解決
- Skills: 原則・パターンを SKILL.md として固定化
- Routines: 旧 Task Scheduler 20 タスクの後継(クラウド実行)
- MCP server: formula 計算基盤の実装手段

これらは段階的に導入する。全部一気には入れない。

## bootstrap_log.md の扱い

- append 専用
- 既存行の編集・削除禁止
- GO/NO-GO 判定は Yuichi が口頭で承認した時のみ Claude Code が記入

## 詳細

C:\new_runtime\design_notes\design_2026-05-25.md を参照