# PROGRESS

## 2026-08-07 リポジトリセットアップ

### やったこと

1. `C:\Users\user\dev\udc2026\yamaguchi-yusho-data` が OneDrive / iCloud Drive の同期対象外であることを確認
2. `C:\Users\user\dev\udc2026\.venv` を作成（Python 環境まわりで詰まった。詳細は下記）
3. `.gitignore` を作成（`raw/` は除外していない。git init より前に作成）
4. `git init`（デフォルトブランチ `main`）
5. `src/` `raw/` `data/` `tests/` `docs/` を作成し各々に `.gitkeep` を配置
6. `requirements.txt` に `pdfplumber` の1行のみ記載し、`.venv` にインストール
7. `README.md` の骨子を作成（出典・ライセンス（準備中）・UDC2026応募作品である旨）
8. `docs/index.html` にタイトルのみのプレースホルダを配置
9. `git config --local user.email` を `183986175+yyy-yuichi@users.noreply.github.com` に設定（`--global` は未変更、`yuichi@example.com` のまま）
10. `git status` を確認後、`git add -A` → コミット（`.claude/` はユーザー確認のうえ含める判断）
11. `gh repo create yamaguchi-yusho-data --public` でリポジトリ作成
12. `git log --format='%ae'` で全コミットのメールアドレスが noreply アドレスのみであることを確認
13. `git push -u origin main` → GitHub Pages を `main` ブランチ `/docs` で有効化

### 確認できた事実（数字を含める）

- `.venv` の Python: **3.13.12**（後述の経緯により `uv` 管理下のビルドを使用）
- `.venv` へのインストール: `pdfplumber==0.11.10` を含む8パッケージ。`import pdfplumber` の動作確認済み（バージョン `0.11.10` を表示）。pandas は未インストール
- 初回コミット: `9974a3f`、14ファイル、559行追加
- リモートリポジトリ: `https://github.com/yyy-yuichi/yamaguchi-yusho-data`（public）
- コミット者メールアドレス: 全1コミットとも `183986175+yyy-yuichi@users.noreply.github.com` のみ（実メールアドレスの混入なし）
- GitHub Pages: `main` ブランチ `/docs` で有効化。`status: "built"` を確認
- **公開URL: <https://yyy-yuichi.github.io/yamaguchi-yusho-data/>**（ブラウザで表示確認済み。タイトル・本文とも想定どおり）

### 詰まったこと、SPEC.md と食い違ったこと

- **SPEC.md との食い違いではないが、環境起因で大きく詰まった点として記録する。**
  `python` / `python3` コマンドが `%LOCALAPPDATA%\Microsoft\WindowsApps\` の
  App Execution Alias スタブ（0バイト）にしか解決せず、`python -m venv` や
  `python --version` がハングした。調査の結果、実体は
  `C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_...\python.exe`
  （Microsoft Store 版、171,744バイト）だが、保護フォルダのため直接実行不可（Access Denied）。
  通常のインストーラー版 Python・Anaconda・pyenv 等はこのマシンに存在しなかった
  （レジストリ・優先パス・`C:\` 全体の再帰検索のいずれでも未検出）。
  → アプリ実行エイリアスの修復を試みる前に、既に `C:\Users\user\.local\bin\uv.exe`
  （`uv` 0.10.0）が導入済みであることが判明したため、方針を切替。
  `uv python install 3.13` で Python 3.13.12 を導入し、
  `uv venv .venv --python 3.13` で仮想環境を作成した。
  **今後このマシンで Python が絡む作業をする際は、素の `python` コマンドではなく
  `uv` 経由（または `.venv\Scripts\python.exe` のフルパス）を使うこと。**
  なお `uv python list`（引数なし）はシステムの `python.exe` を検出しようとして
  同様にハングする。`uv python list --managed-python --only-installed` を使えば回避できる。
- 上記以外、`SPEC.md` の内容そのものとの食い違いは無し。

### 次にやること

- `SPEC.md` §2「最初にやること」— 中国運輸局サイトの利用規約確認（二次利用条件の控え）
- 一覧ページ（`https://wwwtb.mlit.go.jp/chugoku/00001_00903.html`、cp932）を取得し、
  山口県の行と列の対応が `SPEC.md` の表と一致するか確認
- 上記2点が終わるまで、`parse.py` の実装には着手しない（CLAUDE.md の指示どおり）
