#!/usr/bin/env python3
"""SPEC.md 改訂時の網羅チェック。

旧版から「落ちたら困るトークン」を機械的に抽出し、新版に残っているかを総当たりで見る。
落ちているものは、新版の改訂点セクションに言及があるかまで確認する。

使い方: python spec_coverage.py <旧版> <新版> [改訂点セクションの見出し]
終了コード: 未説明の欠落が1件でもあれば 1
"""
import re
import sys
import unicodedata


def norm(s: str) -> str:
    """全角/半角・空白を潰して比較する。"""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", "", s)


def extract_tokens(text: str) -> dict:
    """旧版から検査対象トークンを種類別に抽出する。"""
    t = {}
    # 見出し
    t["見出し"] = re.findall(r"^#{2,4}\s+(.+?)\s*$", text, re.M)
    # バッククォート識別子（列名・ファイル名・パス・コマンド）
    t["識別子"] = sorted(set(re.findall(r"`([^`\n]{2,80})`", text)))
    # 表の1列目（列名定義表を拾う）
    rows = re.findall(r"^\|\s*([^|\n]+?)\s*\|", text, re.M)
    t["表の1列目"] = sorted(
        set(r for r in rows if r not in ("列名", "---", "列", "#", "運送種別", "バナー画像"))
        - {"-" * n for n in range(1, 10)}
    )
    # コードフェンス内の各行（構成図・指示文）
    fences = re.findall(r"```[a-z]*\n(.*?)```", text, re.S)
    lines = []
    for f in fences:
        for ln in f.splitlines():
            ln = ln.strip()
            if len(ln) >= 4:
                lines.append(ln)
    t["コードブロック行"] = sorted(set(lines))
    return t


def main():
    old_path, new_path = sys.argv[1], sys.argv[2]
    revsec = sys.argv[3] if len(sys.argv) > 3 else "改訂点"

    old = open(old_path, encoding="utf-8").read()
    new = open(new_path, encoding="utf-8").read()
    new_n = norm(new)

    # 改訂点セクション（ここに理由が書いてあれば「説明済みの欠落」とみなす）
    m = re.search(rf"^#{{1,3}}.*{re.escape(revsec)}.*$", new, re.M)
    revtext_n = norm(new[m.start():]) if m else ""

    tokens = extract_tokens(old)
    missing_unexplained = []
    missing_explained = []
    total = 0

    print(f"旧版: {old_path}")
    print(f"新版: {new_path}")
    print("=" * 72)

    for kind, items in tokens.items():
        present = 0
        gone = []
        for it in items:
            total += 1
            key = norm(it)
            if not key:
                continue
            if key in new_n:
                present += 1
            else:
                gone.append(it)
        print(f"\n[{kind}] {present}/{len(items)} が新版に存在")
        for g in gone:
            if norm(g) in revtext_n:
                missing_explained.append((kind, g))
                print(f"  - 欠落（改訂点に記載あり）: {g}")
            else:
                missing_unexplained.append((kind, g))
                print(f"  ! 欠落（説明なし）      : {g}")

    print("\n" + "=" * 72)
    print(f"検査トークン数        : {total}")
    print(f"欠落・改訂点に記載あり: {len(missing_explained)}")
    print(f"欠落・説明なし        : {len(missing_unexplained)}")
    if missing_unexplained:
        print("\n判定: 不合格。上記「説明なし」を新版に戻すか、改訂点表に理由を書くこと。")
        return 1
    print("\n判定: 合格。旧版のトークンはすべて新版に残っているか、改訂点に理由がある。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
