"""Build deterministic static data for the municipal supply view (I-2)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DOCS_DATA_DIR = REPO_ROOT / "docs" / "data"

MUNICIPALITY_SOURCE_URL = "https://www.pref.yamaguchi.lg.jp/soshiki/21/26969.html"
MUNICIPALITY_SOURCE_SHA256 = "c947ebd3e02ae11772db8aa4d28828747037e6d6d47113c5ee233213c61860e1"
MUNICIPALITIES = (
    "下関市", "宇部市", "山口市", "萩市", "防府市", "下松市", "岩国市",
    "光市", "長門市", "柳井市", "美祢市", "周南市", "山陽小野田市",
    "周防大島町", "和木町", "上関町", "田布施町", "平生町", "阿武町",
)
TRANSPORT_TYPES = ("福祉有償運送", "交通空白地有償運送")
SOURCE_INDEX_URL = "https://wwwtb.mlit.go.jp/chugoku/00001_00903.html"
SOURCE_ACQUIRED_DATES = {
    "000271730.pdf": "2026-08-07",
    "000230003.pdf": "2026-08-09",
    "000359215.pdf": "2026-08-09",
    "000268896.pdf": "2026-08-09",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def in_municipality(operator, municipality):
    values = [value for value in operator["service_area_municipalities"].split(";") if value]
    return municipality in values


def summarize_operators(operators):
    return {
        "operator_count": len(operators),
        "vehicles_total": sum(int(operator["vehicles_total"]) for operator in operators),
        "vehicles_total_kei": sum(int(operator["vehicles_total_kei"]) for operator in operators),
    }


def public_operator(operator):
    source_pdf = operator["source_pdf"]
    return {
        "registration_no": operator["registration_no"],
        "org_name": operator["org_name"],
        "transport_type": operator["transport_type"],
        "operator_type": operator["operator_type"],
        "valid_to": operator["valid_to"],
        "vehicles_total": int(operator["vehicles_total"]),
        "vehicles_total_kei": int(operator["vehicles_total_kei"]),
        "source_pdf": source_pdf,
        "source_page": int(operator["source_page"]),
        "source_url": f"https://wwwtb.mlit.go.jp/chugoku/content/{source_pdf}",
    }


def build_supply(operators):
    municipalities = []
    for municipality in MUNICIPALITIES:
        related = [operator for operator in operators if in_municipality(operator, municipality)]
        by_transport_type = []
        for transport_type in TRANSPORT_TYPES:
            grouped = [operator for operator in related if operator["transport_type"] == transport_type]
            by_transport_type.append({
                "transport_type": transport_type,
                **summarize_operators(grouped),
            })
        municipalities.append({
            "municipality": municipality,
            **summarize_operators(related),
            "by_transport_type": by_transport_type,
            "operators": [public_operator(operator) for operator in related],
        })

    unique_totals = summarize_operators(operators)
    return {
        "meta": {
            "title": "山口県 市町別の登録供給ビュー",
            "data_as_of": "2026-08-09",
            "source_index_url": SOURCE_INDEX_URL,
            "source_files": list(SOURCE_ACQUIRED_DATES),
            "source_acquired_dates": SOURCE_ACQUIRED_DATES,
            "municipality_source_url": MUNICIPALITY_SOURCE_URL,
            "municipality_source_sha256": MUNICIPALITY_SOURCE_SHA256,
            "municipality_count": len(MUNICIPALITIES),
            "municipalities_with_records": sum(item["operator_count"] > 0 for item in municipalities),
            "unique_prefecture_totals": unique_totals,
        },
        "municipalities": municipalities,
    }


def main():
    operators = read_json(DATA_DIR / "operators.json")
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Published source tables must remain byte-for-byte identical to the verified outputs.
    for filename in ("operators.json", "vehicles.json"):
        shutil.copyfile(DATA_DIR / filename, DOCS_DATA_DIR / filename)

    supply = build_supply(operators)
    (DOCS_DATA_DIR / "municipal_supply.json").write_text(
        json.dumps(supply, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"municipalities: {supply['meta']['municipality_count']}, "
        f"with records: {supply['meta']['municipalities_with_records']}, "
        f"operators: {supply['meta']['unique_prefecture_totals']['operator_count']}"
    )


if __name__ == "__main__":
    main()
