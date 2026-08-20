"""Build a self-contained local prototype for Work 1 information-gap display.

The output is deliberately written under ``internal/`` and has no network
dependencies.  It renders the accepted presentation specification without
copying bounded measurement values or modifying any public file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = "data/work1_supply_side_information_gap_presentation_spec.json"
OUTPUT_PATH = REPO_ROOT / "internal" / "work1_supply_side_information_gap_prototype.html"

TASK_ID = "WORK1-SUPPLY-SIDE-INFORMATION-GAP-INTERNAL-PROTOTYPE-1"
PROTOTYPE_AS_OF = "2026-08-20"
PROTOTYPE_STATUS = "LOCAL_ONLY_NOT_PUBLIC"
DEFAULT_FILTER = "NEXT_CONFIRMATION"

REQUIRED_ROW_FIELDS = (
    "municipality_code",
    "municipality",
    "category_id",
    "category_label",
    "item_id",
    "item_label",
    "presentation_state",
    "information_condition",
    "public_visibility",
    "accepted_source_ids",
    "measurement_result_ids",
    "detail_spec_id",
    "evidence_date",
    "primary_label",
    "display_explanation",
    "source_scope_note",
    "scope_note",
    "value_rendering_rule",
    "next_confirmation",
    "claim_boundary",
)


HTML_TEMPLATE = r'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <meta name="work1-prototype-status" content="LOCAL_ONLY_NOT_PUBLIC">
  <title>確認できる情報と、次に必要な確認｜作品① 内部プロトタイプ</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17233b;
      --muted: #56647a;
      --line: #d9e0ea;
      --surface: #ffffff;
      --surface-soft: #f4f7fb;
      --navy: #16375b;
      --navy-soft: #e9f1f9;
      --focus: #0069c2;
      --public: #1e5a91;
      --public-bg: #e6f1fb;
      --measured: #27644d;
      --measured-bg: #e5f5ed;
      --partial: #76540a;
      --partial-bg: #fff3cf;
      --input: #8a430d;
      --input-bg: #ffeadb;
      --information: #674a30;
      --information-bg: #f4ece3;
      --demand: #634e8f;
      --demand-bg: #f0ebfb;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans JP", sans-serif;
    }

    * { box-sizing: border-box; }

    html { background: #edf2f7; }

    body {
      margin: 0;
      color: var(--ink);
      background: #edf2f7;
      line-height: 1.65;
    }

    button, select { font: inherit; }

    button:focus-visible,
    select:focus-visible,
    summary:focus-visible {
      outline: 3px solid var(--focus);
      outline-offset: 2px;
    }

    .internal-banner {
      background: #242b38;
      color: #fff;
      padding: 0.55rem 1rem;
      text-align: center;
      font-size: 0.86rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }

    .page-shell {
      width: min(1180px, calc(100% - 32px));
      margin: 24px auto 56px;
    }

    .hero,
    .control-panel,
    .legend-panel,
    .category-section {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 8px 28px rgba(26, 50, 80, 0.06);
    }

    .hero { padding: clamp(22px, 4vw, 42px); }

    .eyebrow {
      margin: 0 0 0.55rem;
      color: var(--navy);
      font-size: 0.84rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    h1 {
      margin: 0;
      max-width: 25em;
      font-size: clamp(1.7rem, 4vw, 2.65rem);
      line-height: 1.25;
      letter-spacing: -0.02em;
    }

    .hero-lead {
      margin: 1rem 0 0;
      max-width: 70em;
      color: var(--muted);
    }

    .boundary-note {
      margin: 1.2rem 0 0;
      padding: 0.95rem 1rem;
      background: var(--navy-soft);
      border-left: 5px solid var(--navy);
      border-radius: 8px;
      font-weight: 700;
    }

    .zero-note {
      margin: 0.75rem 0 0;
      color: var(--muted);
      font-size: 0.9rem;
    }

    .control-panel {
      margin-top: 18px;
      padding: 20px;
    }

    .control-row {
      display: grid;
      grid-template-columns: minmax(240px, 0.8fr) minmax(0, 2.2fr);
      gap: 20px;
      align-items: end;
    }

    .field-label {
      display: block;
      margin-bottom: 0.45rem;
      font-weight: 800;
    }

    select {
      width: 100%;
      min-height: 44px;
      padding: 0.55rem 2.3rem 0.55rem 0.75rem;
      color: var(--ink);
      background: #fff;
      border: 1px solid #9facc0;
      border-radius: 9px;
    }

    .filter-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .filter-button {
      min-height: 42px;
      padding: 0.52rem 0.82rem;
      color: var(--navy);
      background: #fff;
      border: 1px solid #9facc0;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 700;
    }

    .filter-button[aria-pressed="true"] {
      color: #fff;
      background: var(--navy);
      border-color: var(--navy);
    }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }

    .summary-card {
      min-width: 0;
      padding: 18px;
      background: var(--surface-soft);
      border: 1px solid var(--line);
      border-radius: 13px;
    }

    .summary-card.is-primary {
      background: #fff7e8;
      border-color: #e3bd71;
    }

    .summary-label {
      display: block;
      color: var(--muted);
      font-size: 0.88rem;
      font-weight: 700;
    }

    .summary-value {
      display: block;
      margin-top: 0.2rem;
      font-size: 2rem;
      font-weight: 850;
      line-height: 1.2;
    }

    .summary-suffix { font-size: 0.9rem; font-weight: 700; }

    .legend-panel {
      margin-top: 18px;
      padding: 18px 20px;
    }

    .legend-panel h2,
    .results-heading h2 {
      margin: 0;
      font-size: 1.15rem;
    }

    .legend-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0 0;
      padding: 0;
      list-style: none;
    }

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 0.42rem;
      min-width: 0;
      padding: 0.35rem 0.62rem;
      background: var(--surface-soft);
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 0.84rem;
    }

    .legend-count { color: var(--muted); font-weight: 800; }

    .results-heading {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin: 28px 2px 12px;
    }

    .results-status {
      margin: 0;
      color: var(--muted);
      font-size: 0.92rem;
      text-align: right;
    }

    .category-section {
      margin-top: 14px;
      overflow: hidden;
    }

    .category-heading {
      margin: 0;
      padding: 15px 18px;
      color: var(--navy);
      background: var(--navy-soft);
      border-bottom: 1px solid var(--line);
      font-size: 1.05rem;
    }

    .category-count {
      margin-left: 0.45rem;
      color: var(--muted);
      font-size: 0.82rem;
      font-weight: 700;
    }

    .item-list { padding: 0 18px; }

    .item-card {
      padding: 18px 0;
      border-bottom: 1px solid var(--line);
    }

    .item-card:last-child { border-bottom: 0; }

    .item-heading-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: flex-start;
      justify-content: space-between;
    }

    .item-title {
      min-width: 0;
      margin: 0;
      font-size: 1rem;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }

    .status-badge,
    .scope-badge {
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      padding: 0.28rem 0.55rem;
      border: 1px solid transparent;
      border-radius: 7px;
      font-size: 0.78rem;
      font-weight: 800;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }

    .status-badge[data-state="PUBLICLY_VISIBLE_CURRENT"] { color: var(--public); background: var(--public-bg); border-color: #bad4ec; }
    .status-badge[data-state="MEASURED_BOUNDED_INTERNAL"] { color: var(--measured); background: var(--measured-bg); border-color: #b7ddcc; }
    .status-badge[data-state="MEASUREMENT_GAP_PARTIAL_SOURCE"] { color: var(--partial); background: var(--partial-bg); border-color: #ead18b; }
    .status-badge[data-state="MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED"] { color: var(--input); background: var(--input-bg); border-color: #edc19e; }
    .status-badge[data-state="INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED"] { color: var(--information); background: var(--information-bg); border-color: #dac7b4; }
    .status-badge[data-state="DEMAND_COMPARATOR_REQUIRED"] { color: var(--demand); background: var(--demand-bg); border-color: #cfc3ea; }

    .scope-badge {
      margin-top: 0.7rem;
      color: var(--navy);
      background: #f2f6fb;
      border-color: #ccd8e7;
    }

    .item-explanation {
      margin: 0.75rem 0 0;
      color: #35445a;
    }

    details {
      margin-top: 0.8rem;
      border: 1px solid var(--line);
      border-radius: 9px;
      background: #fbfcfe;
    }

    summary {
      padding: 0.7rem 0.8rem;
      color: var(--navy);
      cursor: pointer;
      font-weight: 800;
    }

    .evidence-body {
      padding: 0 0.8rem 0.85rem;
      border-top: 1px solid var(--line);
    }

    .evidence-list {
      display: grid;
      grid-template-columns: minmax(9rem, 0.28fr) minmax(0, 1fr);
      margin: 0;
    }

    .evidence-list dt,
    .evidence-list dd {
      margin: 0;
      padding: 0.65rem 0;
      border-bottom: 1px solid #e7ebf1;
      overflow-wrap: anywhere;
    }

    .evidence-list dt { padding-right: 0.8rem; color: var(--muted); font-weight: 800; }
    .evidence-list dd { color: #2c3b50; }
    .evidence-list dt:last-of-type,
    .evidence-list dd:last-of-type { border-bottom: 0; }

    .empty-state {
      padding: 28px;
      text-align: center;
      color: var(--muted);
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 14px;
    }

    .page-footer {
      margin-top: 24px;
      padding: 18px;
      color: var(--muted);
      text-align: center;
      font-size: 0.85rem;
    }

    [hidden] { display: none !important; }

    @media (max-width: 720px) {
      .page-shell {
        width: min(100% - 20px, 1180px);
        margin-top: 10px;
      }

      .hero,
      .control-panel,
      .legend-panel,
      .category-section { border-radius: 12px; }

      .hero { padding: 20px 17px; }
      .control-panel { padding: 16px; }
      .control-row { grid-template-columns: minmax(0, 1fr); gap: 14px; }
      .filter-buttons { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .filter-button { width: 100%; padding-inline: 0.5rem; }
      .summary-grid { grid-template-columns: minmax(0, 1fr); }
      .legend-list { display: grid; grid-template-columns: minmax(0, 1fr); }
      .results-heading { display: block; }
      .results-status { margin-top: 0.35rem; text-align: left; }
      .category-heading { padding: 13px 14px; }
      .item-list { padding: 0 14px; }
      .item-heading-row { display: block; }
      .status-badge { margin-top: 0.55rem; }
      .evidence-list { grid-template-columns: minmax(0, 1fr); }
      .evidence-list dt { padding-bottom: 0.1rem; border-bottom: 0; }
      .evidence-list dd { padding-top: 0.1rem; }
    }

    @media (max-width: 390px) {
      .filter-buttons { grid-template-columns: minmax(0, 1fr); }
    }
  </style>
</head>
<body>
  <div class="internal-banner" role="status" data-testid="internal-banner">
    作品①・ローカル内部プロトタイプ｜公開ページではありません
  </div>

  <main class="page-shell">
    <section class="hero" aria-labelledby="page-title">
      <p class="eyebrow">Work 1 / information review prototype</p>
      <h1 id="page-title">確認できる情報と、次に必要な確認</h1>
      <p class="hero-lead">
        山口県19市町について、受入済み原本から確認できること、原本内で追加測定が必要なこと、
        追加原本の検討が必要なこと、生活・需要との比較が必要なことを分けて確認する試作画面です。
      </p>
      <p class="boundary-note" data-testid="boundary-note">
        情報の不足と、現実の交通サービスの不足は別です。この画面だけで交通の充足・不足は判断しません。
      </p>
      <p class="zero-note" data-testid="registered-zero-note">
        「4登録簿上の該当記載0件」は、交通手段・移動支援・別制度がないことを意味しません。
      </p>
    </section>

    <section class="control-panel" aria-label="表示条件">
      <div class="control-row">
        <div>
          <label class="field-label" for="municipality-select">市町を選ぶ</label>
          <select id="municipality-select" data-testid="municipality-select"></select>
        </div>
        <div>
          <span class="field-label" id="filter-label">表示する情報</span>
          <div class="filter-buttons" role="group" aria-labelledby="filter-label">
            <button class="filter-button" type="button" data-filter="NEXT_CONFIRMATION" aria-pressed="true">次に確認する情報</button>
            <button class="filter-button" type="button" data-filter="CONFIRMED_INFORMATION" aria-pressed="false">確認できる情報</button>
            <button class="filter-button" type="button" data-filter="DEMAND_COMPARATOR_REQUIRED" aria-pressed="false">生活・需要との比較</button>
            <button class="filter-button" type="button" data-filter="ALL" aria-pressed="false">全35項目</button>
          </div>
        </div>
      </div>

      <div class="summary-grid" aria-label="選択市町の情報確認状況">
        <article class="summary-card is-primary">
          <span class="summary-label">次に確認する情報</span>
          <strong class="summary-value"><span id="summary-next">0</span><span class="summary-suffix">項目</span></strong>
        </article>
        <article class="summary-card">
          <span class="summary-label">確認できる情報</span>
          <strong class="summary-value"><span id="summary-confirmed">0</span><span class="summary-suffix">項目</span></strong>
        </article>
        <article class="summary-card">
          <span class="summary-label">生活・需要との比較が必要</span>
          <strong class="summary-value"><span id="summary-demand">0</span><span class="summary-suffix">項目</span></strong>
        </article>
      </div>
    </section>

    <section class="legend-panel" aria-labelledby="legend-title">
      <h2 id="legend-title">6つの確認状態</h2>
      <ul class="legend-list" id="legend-list"></ul>
    </section>

    <div class="results-heading">
      <h2 id="results-title">項目別の確認状況</h2>
      <p class="results-status" id="results-status" aria-live="polite" data-testid="results-status"></p>
    </div>

    <div id="category-container" aria-labelledby="results-title" data-testid="category-container"></div>
    <p class="empty-state" id="empty-state" hidden>この表示条件に該当する項目はありません。</p>

    <footer class="page-footer">
      本成果物はローカル検証専用です。公開4ページ、docs/data、交通判断には使用していません。
    </footer>
  </main>

  <script id="prototype-data" type="application/json">__PROTOTYPE_DATA__</script>
  <script>
    (() => {
      "use strict";
      const DATA = JSON.parse(document.getElementById("prototype-data").textContent);
      const municipalitySelect = document.getElementById("municipality-select");
      const categoryContainer = document.getElementById("category-container");
      const resultsStatus = document.getElementById("results-status");
      const emptyState = document.getElementById("empty-state");
      const summaryNext = document.getElementById("summary-next");
      const summaryConfirmed = document.getElementById("summary-confirmed");
      const summaryDemand = document.getElementById("summary-demand");
      const legendList = document.getElementById("legend-list");
      const filterButtons = Array.from(document.querySelectorAll("[data-filter]"));
      let activeFilter = DATA.prototype_contract.default_filter;

      const byMunicipality = new Map();
      for (const row of DATA.rows) {
        if (!byMunicipality.has(row.municipality_code)) byMunicipality.set(row.municipality_code, []);
        byMunicipality.get(row.municipality_code).push(row);
      }

      const summaryByCode = new Map(
        DATA.municipality_summaries.map((item) => [item.municipality_code, item])
      );

      function makeElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined && text !== null) element.textContent = String(text);
        return element;
      }

      function displayValue(value, emptyText) {
        if (Array.isArray(value)) return value.length ? value.join(" / ") : emptyText;
        if (value === null || value === undefined || value === "") return emptyText;
        return String(value);
      }

      function addEvidencePair(list, term, value, emptyText = "該当記録なし") {
        list.append(makeElement("dt", "", term));
        list.append(makeElement("dd", "", displayValue(value, emptyText)));
      }

      function rowMatchesFilter(row) {
        if (activeFilter === "ALL") return true;
        if (activeFilter === "NEXT_CONFIRMATION") {
          return row.information_condition === "MEASUREMENT_GAP"
            || row.information_condition === "INFORMATION_GAP";
        }
        return row.information_condition === activeFilter;
      }

      function filterLabel() {
        const button = filterButtons.find((item) => item.dataset.filter === activeFilter);
        return button ? button.textContent : "表示中";
      }

      function createItemCard(row) {
        const article = makeElement("article", "item-card");
        article.dataset.state = row.presentation_state;
        article.dataset.itemId = row.item_id;

        const headingRow = makeElement("div", "item-heading-row");
        headingRow.append(makeElement("h3", "item-title", row.item_label));
        const stateBadge = makeElement("span", "status-badge", row.primary_label);
        stateBadge.dataset.state = row.presentation_state;
        headingRow.append(stateBadge);
        article.append(headingRow);

        const scopeBadge = makeElement("span", "scope-badge", row.source_scope_note);
        article.append(scopeBadge);
        article.append(makeElement("p", "item-explanation", row.display_explanation));

        const details = makeElement("details", "evidence-details");
        details.append(makeElement("summary", "", "根拠・日付・範囲・次の確認を見る"));
        const body = makeElement("div", "evidence-body");
        const list = makeElement("dl", "evidence-list");
        addEvidencePair(list, "受入原本ID", row.accepted_source_ids, "現在の受入原本なし");
        addEvidencePair(list, "証拠日", row.evidence_date, "日付未設定");
        addEvidencePair(list, "範囲", row.scope_note, "範囲注記なし");
        addEvidencePair(list, "次の確認", row.next_confirmation, "追加確認なし");
        addEvidencePair(list, "表示ルール", row.value_rendering_rule, "表示ルールなし");
        addEvidencePair(list, "非主張", row.claim_boundary, "非主張注記なし");
        if (row.detail_spec_id) addEvidencePair(list, "内部詳細仕様", row.detail_spec_id);
        if (row.measurement_result_ids.length) {
          addEvidencePair(list, "内部測定result", row.measurement_result_ids);
        }
        body.append(list);
        details.append(body);
        article.append(details);
        return article;
      }

      function updateLegend(summary) {
        legendList.replaceChildren();
        for (const state of DATA.states) {
          const item = makeElement("li", "legend-item");
          const badge = makeElement("span", "status-badge", state.short_label);
          badge.dataset.state = state.code;
          const count = summary.presentation_state_counts[state.code] || 0;
          item.append(badge, makeElement("span", "legend-count", `${count}項目`));
          legendList.append(item);
        }
      }

      function render() {
        const code = municipalitySelect.value;
        const rows = byMunicipality.get(code) || [];
        const summary = summaryByCode.get(code);
        if (!summary) return;

        summaryNext.textContent = String(summary.next_confirmation_count);
        summaryConfirmed.textContent = String(summary.information_condition_counts.CONFIRMED_INFORMATION);
        summaryDemand.textContent = String(summary.demand_comparator_count);
        updateLegend(summary);

        const matching = rows.filter(rowMatchesFilter);
        categoryContainer.replaceChildren();
        for (const category of DATA.categories) {
          const categoryRows = matching.filter((row) => row.category_id === category.category_id);
          if (!categoryRows.length) continue;
          const section = makeElement("section", "category-section");
          section.dataset.categoryId = category.category_id;
          const heading = makeElement("h2", "category-heading", category.category_label);
          heading.append(makeElement("span", "category-count", `${categoryRows.length}項目`));
          section.append(heading);
          const list = makeElement("div", "item-list");
          for (const row of categoryRows) list.append(createItemCard(row));
          section.append(list);
          categoryContainer.append(section);
        }

        emptyState.hidden = matching.length !== 0;
        resultsStatus.textContent = `${summary.municipality}：${filterLabel()} ${matching.length}項目`;
        document.title = `${summary.municipality}｜確認できる情報と、次に必要な確認｜作品① 内部プロトタイプ`;
      }

      for (const municipality of DATA.municipalities) {
        const option = makeElement("option", "", municipality.municipality);
        option.value = municipality.municipality_code;
        municipalitySelect.append(option);
      }

      municipalitySelect.addEventListener("change", render);
      for (const button of filterButtons) {
        button.addEventListener("click", () => {
          activeFilter = button.dataset.filter;
          for (const candidate of filterButtons) {
            candidate.setAttribute("aria-pressed", String(candidate === button));
          }
          render();
        });
      }

      window.__WORK1_PROTOTYPE__ = {
        taskId: DATA.task_id,
        status: DATA.prototype_status,
        get activeFilter() { return activeFilter; },
        get selectedMunicipalityCode() { return municipalitySelect.value; },
        get visibleItemCount() { return categoryContainer.querySelectorAll(".item-card").length; }
      };

      render();
    })();
  </script>
</body>
</html>
'''


def _load_specification() -> dict[str, Any]:
    return json.loads((REPO_ROOT / INPUT_PATH).read_text(encoding="utf-8"))


def _sha256_and_size(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def build_prototype_data(specification: dict[str, Any]) -> dict[str, Any]:
    if specification["task_id"] != "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PRESENTATION-SPEC-1":
        raise ValueError("unexpected presentation specification task")
    if specification["spec_status"] != "DEFINED_INTERNAL_NOT_IMPLEMENTED_PUBLICLY":
        raise ValueError("presentation specification is not an internal accepted definition")
    if specification["dimensions"]["municipality_item_row_count"] != 665:
        raise ValueError("presentation specification row count drifted")

    input_sha256, input_size = _sha256_and_size(REPO_ROOT / INPUT_PATH)
    rows = []
    for source in specification["municipality_item_presentation_specs"]:
        row = {field: source[field] for field in REQUIRED_ROW_FIELDS}
        if tuple(row) != REQUIRED_ROW_FIELDS:
            raise AssertionError("prototype row field order drifted")
        rows.append(row)

    if len(rows) != 665:
        raise ValueError("prototype must contain exactly 665 rows")
    unique_keys = {(row["municipality_code"], row["item_id"]) for row in rows}
    if len(unique_keys) != 665:
        raise ValueError("prototype rows are not unique")
    if any(row["information_condition"] == "SERVICE_GAP" for row in rows):
        raise ValueError("prototype cannot contain a service-gap decision state")

    municipalities = [
        {
            "municipality_code": item["municipality_code"],
            "municipality": item["municipality"],
        }
        for item in specification["municipality_summaries"]
    ]
    categories = [
        {
            "category_id": item["category_id"],
            "category_label": item["category_label"],
        }
        for item in specification["category_summaries"]
    ]
    states = [
        {
            "code": item["code"],
            "short_label": item["short_label"],
            "information_condition": item["information_condition"],
            "public_visibility": item["public_visibility"],
        }
        for item in specification["presentation_state_vocabulary"]
    ]

    return {
        "task_id": TASK_ID,
        "prototype_as_of": PROTOTYPE_AS_OF,
        "prototype_status": PROTOTYPE_STATUS,
        "input_file": {
            "path": INPUT_PATH,
            "bytes": input_size,
            "sha256": input_sha256,
        },
        "dimensions": {
            "municipality_count": len(municipalities),
            "category_count": len(categories),
            "item_count_per_municipality": 35,
            "row_count": len(rows),
            "state_count": len(states),
        },
        "prototype_contract": {
            "default_filter": DEFAULT_FILTER,
            "available_filters": [
                "NEXT_CONFIRMATION",
                "CONFIRMED_INFORMATION",
                "DEMAND_COMPARATOR_REQUIRED",
                "ALL",
            ],
            "network_dependencies": 0,
            "public_files_changed": 0,
            "measurement_values_copied": 0,
            "service_gap_decisions": 0,
            "responsive_breakpoints_px": [720, 390],
        },
        "municipalities": municipalities,
        "categories": categories,
        "states": states,
        "municipality_summaries": specification["municipality_summaries"],
        "zero_and_missing_value_contract": specification["zero_and_missing_value_contract"],
        "rows": rows,
        "global_boundaries": specification["global_boundaries"],
    }


def render_prototype_html(prototype_data: dict[str, Any]) -> str:
    embedded = json.dumps(prototype_data, ensure_ascii=False, separators=(",", ":"))
    embedded = embedded.replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__PROTOTYPE_DATA__", embedded)


def build_html() -> str:
    return render_prototype_html(build_prototype_data(_load_specification()))


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(build_html().encode("utf-8"))


if __name__ == "__main__":
    main()
