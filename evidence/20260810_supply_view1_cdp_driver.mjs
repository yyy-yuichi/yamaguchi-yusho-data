// SUPPLY-VIEW-1 actual-browser verification over raw Chrome DevTools Protocol.
// This script owns and stops only the optional localhost server and headless Edge it starts.
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";

const REPO = "C:/Users/user/dev/udc2026/yamaguchi-yusho-data";
const DOCS = `${REPO}/docs`;
const OUT = `${REPO}/evidence`;
const EVIDENCE_PREFIX = process.env.VERIFY_EVIDENCE_PREFIX || "20260810_supply_view1";
const PUBLIC_SITE_BASE = process.env.VERIFY_SITE_BASE || null;
const TASK_LABEL = process.env.VERIFY_TASK_LABEL || "SUPPLY-VIEW-1 V4 actual-browser verification";
const PROFILE = `${OUT}/${EVIDENCE_PREFIX}_cdp_profile`;
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const RAW_PATH = `${OUT}/${EVIDENCE_PREFIX}_browser_raw.json`;
const SUMMARY_PATH = `${OUT}/${EVIDENCE_PREFIX}_browser_summary.txt`;
const DESKTOP_SHOT = `${OUT}/${EVIDENCE_PREFIX}_screenshot_1440.png`;
const MOBILE_SHOT = `${OUT}/${EVIDENCE_PREFIX}_screenshot_390x844.png`;

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitFor(url, label, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
      lastError = new Error(`${label}: HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(100);
  }
  throw new Error(`${label} did not become ready: ${lastError}`);
}

function requestId() {
  return Math.floor(Math.random() * 1e9);
}

function connect(webSocketDebuggerUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(webSocketDebuggerUrl);
    ws.addEventListener("open", () => resolve(ws));
    ws.addEventListener("error", reject);
  });
}

function send(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = requestId();
    const handler = event => {
      const message = JSON.parse(event.data);
      if (message.id !== id) return;
      ws.removeEventListener("message", handler);
      if (message.error) reject(new Error(`${method}: ${JSON.stringify(message.error)}`));
      else resolve(message.result);
    };
    ws.addEventListener("message", handler);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function stopOwned(child) {
  if (!child || child.exitCode !== null || !child.pid) return;
  await new Promise(resolve => {
    const killer = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore",
    });
    killer.once("close", resolve);
    killer.once("error", resolve);
  });
}

function assertion(name, pass, actual) {
  return { name, pass: Boolean(pass), actual };
}

function normalizedDate(text) {
  const match = String(text).match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
  if (!match) return null;
  return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
}

function numberFrom(text) {
  const match = String(text).replaceAll(",", "").match(/-?\d+/);
  return match ? Number(match[0]) : null;
}

async function main() {
  if (!fs.existsSync(EDGE)) throw new Error(`Edge not found: ${EDGE}`);
  if (fs.existsSync(RAW_PATH)) {
    const prior = JSON.parse(fs.readFileSync(RAW_PATH, "utf8"));
    if (prior.overallPass === false) {
      fs.copyFileSync(RAW_PATH, `${OUT}/${EVIDENCE_PREFIX}_browser_initial_fail_raw.json`);
      if (fs.existsSync(SUMMARY_PATH)) {
        fs.copyFileSync(SUMMARY_PATH, `${OUT}/${EVIDENCE_PREFIX}_browser_initial_fail_summary.txt`);
      }
    }
  }
  const safeProfile = path.resolve(PROFILE).replaceAll("\\", "/");
  const safePrefix = path.resolve(OUT, `${EVIDENCE_PREFIX}_`).replaceAll("\\", "/");
  if (!safeProfile.startsWith(safePrefix)) throw new Error(`unsafe profile path: ${safeProfile}`);
  fs.rmSync(PROFILE, { recursive: true, force: true });
  fs.mkdirSync(PROFILE, { recursive: true });

  const sitePort = PUBLIC_SITE_BASE ? null : await freePort();
  const cdpPort = await freePort();
  const siteBase = PUBLIC_SITE_BASE || `http://localhost:${sitePort}`;
  const cdpBase = `http://127.0.0.1:${cdpPort}`;
  let server = null;
  let edge = null;
  let ws = null;
  let targetId = null;

  const result = {
    task: TASK_LABEL,
    generatedAt: new Date().toISOString(),
    siteBase,
    cdpPort,
    ownedProcesses: {},
    expectedSource: `${siteBase}/data/gtfs_supply_metrics.json`,
    viewports: [],
    assertions: [],
    overallPass: false,
  };

  try {
    if (PUBLIC_SITE_BASE) {
      await waitFor(`${siteBase}/`, "public site");
    } else {
      server = spawn("python", ["-B", "-m", "http.server", String(sitePort), "--bind", "127.0.0.1", "--directory", DOCS], {
        cwd: REPO,
        windowsHide: true,
        stdio: "ignore",
      });
      result.ownedProcesses.serverPid = server.pid;
      await waitFor(`${siteBase}/index.html`, "docs HTTP server");
    }

    edge = spawn(EDGE, [
      "--headless=new",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-component-update",
      `--remote-debugging-port=${cdpPort}`,
      "--remote-debugging-address=127.0.0.1",
      `--user-data-dir=${PROFILE}`,
      "about:blank",
    ], { windowsHide: true, stdio: "ignore" });
    result.ownedProcesses.edgePid = edge.pid;
    await waitFor(`${cdpBase}/json/version`, "Edge CDP");

    const targetResponse = await fetch(`${cdpBase}/json/new?about:blank`, { method: "PUT" });
    if (!targetResponse.ok) throw new Error(`new CDP target: HTTP ${targetResponse.status}`);
    const target = await targetResponse.json();
    targetId = target.id;
    ws = await connect(target.webSocketDebuggerUrl);

    let events = null;
    ws.addEventListener("message", event => {
      if (!events) return;
      const message = JSON.parse(event.data);
      if (message.method === "Runtime.consoleAPICalled") {
        const text = (message.params.args || []).map(arg => arg.value ?? arg.description ?? "").join(" ");
        events.console.push({ type: message.params.type, text });
      } else if (message.method === "Runtime.exceptionThrown") {
        events.runtimeExceptions.push(message.params.exceptionDetails.text || JSON.stringify(message.params.exceptionDetails));
      } else if (message.method === "Log.entryAdded") {
        events.log.push({ level: message.params.entry.level, text: message.params.entry.text, url: message.params.entry.url || null });
      } else if (message.method === "Network.loadingFailed") {
        events.loadingFailed.push({ url: events.requests.get(message.params.requestId) || null, errorText: message.params.errorText, canceled: Boolean(message.params.canceled) });
      } else if (message.method === "Network.requestWillBeSent") {
        events.requests.set(message.params.requestId, message.params.request.url);
      } else if (message.method === "Network.responseReceived") {
        events.responses.push({ url: message.params.response.url, status: message.params.response.status, type: message.params.type });
      }
    });

    await send(ws, "Page.enable");
    await send(ws, "Runtime.enable");
    await send(ws, "Log.enable");
    await send(ws, "Network.enable");

    const expectedResponse = await fetch(`${siteBase}/data/gtfs_supply_metrics.json`);
    const expected = await expectedResponse.json();
    const feedsResponse = await fetch(`${siteBase}/data/gtfs_feeds.json`);
    const expectedByCity = Object.fromEntries(expected.map(record => [record.municipality, record]));
    const cities = ["岩国市", "光市"];
    const metricIds = ["gtfs_agency_record_count", "gtfs_route_id_count", "gtfs_boarding_location_id_count"];
    const dates = Object.keys(expectedByCity["岩国市"].scheduled_trip_count_by_date);

    result.assertions.push(assertion("preflight supply JSON HTTP 200", expectedResponse.status === 200, expectedResponse.status));
    result.assertions.push(assertion("preflight gtfs_feeds JSON HTTP 200", feedsResponse.status === 200, feedsResponse.status));

    async function evaluate(expression) {
      const evaluated = await send(ws, "Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
      if (evaluated.exceptionDetails) throw new Error(`Runtime.evaluate failed: ${evaluated.exceptionDetails.text}`);
      return evaluated.result.value;
    }

    async function waitForPageReady() {
      const deadline = Date.now() + 15000;
      let last = null;
      while (Date.now() < deadline) {
        last = JSON.parse(await evaluate(`(() => JSON.stringify({
          ready: document.readyState,
          supplyVisible: Boolean(document.querySelector('#supply-comparison-content:not([hidden])')),
          municipalVisible: Boolean(document.querySelector('#result:not([hidden])')),
          gtfsVisible: Boolean(document.querySelector('#gtfs-result:not([hidden])')),
          supplyError: Boolean(document.querySelector('#supply-comparison-error:not([hidden])')),
          existingError: Boolean(document.querySelector('#error:not([hidden])'))
        }))()`));
        if (last.ready === "complete" && last.supplyVisible && last.municipalVisible && last.gtfsVisible) return last;
        if (last.supplyError || last.existingError) return last;
        await sleep(100);
      }
      throw new Error(`page did not finish rendering: ${JSON.stringify(last)}`);
    }

    async function checkViewport(width, height, label, screenshotPath) {
      events = { console: [], runtimeExceptions: [], log: [], loadingFailed: [], responses: [], requests: new Map() };
      await send(ws, "Emulation.setDeviceMetricsOverride", {
        width, height, screenWidth: width, screenHeight: height,
        deviceScaleFactor: 1, mobile: width < 500,
      });
      await send(ws, "Page.navigate", { url: `${siteBase}/index.html?verify=${Date.now()}` });
      const ready = await waitForPageReady();
      await sleep(250);

      const dom = JSON.parse(await evaluate(`(() => {
        document.querySelectorAll('#supply-evidence-list details').forEach(node => { node.open = true; });
        const doc = document.documentElement;
        const structureTable = document.querySelector('#supply-structure-body')?.closest('table');
        const dailyTable = document.querySelector('#supply-daily-body')?.closest('table');
        function tableData(table) {
          if (!table) return null;
          const wrap = table.closest('.table-wrap');
          const rect = table.getBoundingClientRect();
          const wrapRect = wrap.getBoundingClientRect();
          const headerCells = [...table.querySelectorAll('thead th')].map(cell => cell.textContent.trim());
          const rows = [...table.querySelectorAll('tbody tr')].map(row => [...row.children].map(cell => cell.textContent.trim()));
          const allCellsVisible = [...table.querySelectorAll('thead th, tbody th, tbody td')].every(cell => {
            const r = cell.getBoundingClientRect();
            return r.left >= wrapRect.left - 1 && r.right <= wrapRect.right + 1;
          });
          return {
            headerCells, rows,
            tableWidth: rect.width,
            wrapperClientWidth: wrap.clientWidth,
            wrapperScrollWidth: wrap.scrollWidth,
            allCellsVisible,
          };
        }
        const supply = document.querySelector('#supply-comparison');
        const evidence = document.querySelector('#supply-evidence-list');
        const bodyText = document.body.textContent.replace(/\\s+/g, ' ').trim();
        return JSON.stringify({
          title: document.title,
          viewport: { innerWidth: window.innerWidth, innerHeight: window.innerHeight },
          documentWidth: { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth, difference: doc.scrollWidth - doc.clientWidth },
          supplyExists: Boolean(supply),
          supplyHeading: document.querySelector('#supply-comparison-title')?.textContent.trim() || null,
          supplyContentHidden: document.querySelector('#supply-comparison-content')?.hidden ?? null,
          supplyErrorHidden: document.querySelector('#supply-comparison-error')?.hidden ?? null,
          existingErrorHidden: document.querySelector('#error')?.hidden ?? null,
          municipalResultVisible: Boolean(document.querySelector('#result:not([hidden])')),
          gtfsResultVisible: Boolean(document.querySelector('#gtfs-result:not([hidden])')),
          municipalHeading: document.querySelector('#result-title')?.textContent.trim() || null,
          gtfsHeading: document.querySelector('#gtfs-result-title')?.textContent.trim() || null,
          structureHeading: document.querySelector('#supply-structure-body')?.closest('.comparison-block')?.querySelector('h3')?.textContent.trim() || null,
          dailyHeading: document.querySelector('#supply-daily-body')?.closest('.comparison-block')?.querySelector('h3')?.textContent.trim() || null,
          evidenceHeading: evidence?.closest('.comparison-block')?.querySelector('h3')?.textContent.trim() || null,
          sectionOffsets: {
            supply: supply?.offsetTop ?? null,
            structure: structureTable?.offsetTop ?? null,
            daily: dailyTable?.offsetTop ?? null,
            evidence: evidence?.offsetTop ?? null,
          },
          structure: tableData(structureTable),
          daily: tableData(dailyTable),
          evidenceDetails: evidence ? [...evidence.querySelectorAll('details')].map(node => ({ open: node.open, text: node.textContent.replace(/\\s+/g, ' ').trim() })) : [],
          bodyText
        });
      })()`));

      const layout = await send(ws, "Page.getLayoutMetrics");
      const content = layout.cssContentSize || layout.contentSize;
      const capture = await send(ws, "Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: true,
        clip: { x: 0, y: 0, width: Math.ceil(content.width), height: Math.ceil(content.height), scale: 1 },
      });
      fs.writeFileSync(screenshotPath, Buffer.from(capture.data, "base64"));

      const assertions = [];
      assertions.push(assertion(`${label}: requested viewport applied`, dom.viewport.innerWidth === width && dom.viewport.innerHeight === height, dom.viewport));
      assertions.push(assertion(`${label}: document horizontal overflow is zero`, dom.documentWidth.difference === 0, dom.documentWidth));
      assertions.push(assertion(`${label}: comparison headings and evidence are reachable`, dom.supplyExists && dom.supplyHeading && dom.structureHeading && dom.dailyHeading && dom.evidenceHeading && dom.evidenceDetails.length === 2, { supply: dom.supplyHeading, structure: dom.structureHeading, daily: dom.dailyHeading, evidence: dom.evidenceHeading, offsets: dom.sectionOffsets, detailCount: dom.evidenceDetails.length }));
      assertions.push(assertion(`${label}: supply comparison rendered without failure`, dom.supplyContentHidden === false && dom.supplyErrorHidden === true, { supplyContentHidden: dom.supplyContentHidden, supplyErrorHidden: dom.supplyErrorHidden }));
      assertions.push(assertion(`${label}: existing municipal and GTFS views remain rendered`, dom.existingErrorHidden === true && dom.municipalResultVisible && dom.gtfsResultVisible, { existingErrorHidden: dom.existingErrorHidden, municipalResultVisible: dom.municipalResultVisible, gtfsResultVisible: dom.gtfsResultVisible, municipalHeading: dom.municipalHeading, gtfsHeading: dom.gtfsHeading }));

      const expectedHeaders = ["指標", "岩国市関連", "光市関連"];
      assertions.push(assertion(`${label}: structure table has both cities simultaneously visible`, JSON.stringify(dom.structure?.headerCells) === JSON.stringify(expectedHeaders) && dom.structure?.allCellsVisible && dom.structure?.wrapperScrollWidth === dom.structure?.wrapperClientWidth, dom.structure));
      const structureValues = dom.structure?.rows.map(row => row.slice(1).map(numberFrom)) || [];
      const expectedStructure = metricIds.map(metricId => cities.map(city => expectedByCity[city].metrics[metricId].value));
      assertions.push(assertion(`${label}: all six structure values match JSON`, JSON.stringify(structureValues) === JSON.stringify(expectedStructure), { expected: expectedStructure, actual: structureValues }));

      const actualDates = dom.daily?.rows.map(row => normalizedDate(row[0])) || [];
      const dailyValues = dom.daily?.rows.map(row => row.slice(1).map(numberFrom)) || [];
      const expectedDaily = dates.map(date => cities.map(city => expectedByCity[city].scheduled_trip_count_by_date[date].value));
      assertions.push(assertion(`${label}: seven real dates match JSON`, JSON.stringify(actualDates) === JSON.stringify(dates), { expected: dates, actual: actualDates }));
      assertions.push(assertion(`${label}: all fourteen daily values match JSON`, JSON.stringify(dailyValues) === JSON.stringify(expectedDaily), { expected: expectedDaily, actual: dailyValues }));
      assertions.push(assertion(`${label}: daily table has both cities simultaneously visible`, dom.daily?.allCellsVisible && dom.daily?.wrapperScrollWidth === dom.daily?.wrapperClientWidth, dom.daily));

      const text = dom.bodyText;
      const dateAndEvidenceChecks = expected.flatMap(record => [
        text.includes(record.municipality),
        text.includes(record.scope_note),
        text.includes(record.official_reference_date),
        text.includes(record.checked_at),
        text.includes(record.metric_computed_at),
        text.includes(record.source_zip_path),
        text.includes(record.source_zip_sha256),
        text.includes(record.date_basis.feed_info.feed_start_date),
        text.includes(record.date_basis.feed_info.feed_end_date),
      ]);
      const labelledDates = ["公式ページ記載のデータ基準日", "GTFS内部日付", "確認日", "計算日", "原本ZIP", "原本ZIP SHA256"].every(labelText => text.includes(labelText));
      assertions.push(assertion(`${label}: status, scope limit, labelled dates, ZIP and full SHA are present`, text.includes("測定済み") && text.includes("市内だけの値") && text.includes("市内のすべての公共交通") && labelledDates && dateAndEvidenceChecks.every(Boolean), { measured: text.includes("測定済み"), feedWideLimit: text.includes("市内だけの値") && text.includes("市内のすべての公共交通"), labelledDates, exactEvidenceChecks: dateAndEvidenceChecks.filter(Boolean).length, exactEvidenceTotal: dateAndEvidenceChecks.length }));

      const supplyStatus = events.responses.filter(item => new URL(item.url).pathname.endsWith("/data/gtfs_supply_metrics.json")).map(item => item.status);
      const feedsStatus = events.responses.filter(item => new URL(item.url).pathname.endsWith("/data/gtfs_feeds.json")).map(item => item.status);
      assertions.push(assertion(`${label}: supply and gtfs_feeds JSON loaded with HTTP 200`, supplyStatus.includes(200) && feedsStatus.includes(200), { supplyStatus, feedsStatus }));
      const consoleErrors = events.console.filter(item => item.type === "error");
      const logErrors = events.log.filter(item => item.level === "error");
      assertions.push(assertion(`${label}: browser error channels are empty`, consoleErrors.length === 0 && events.runtimeExceptions.length === 0 && logErrors.length === 0 && events.loadingFailed.length === 0, { consoleErrors, runtimeExceptions: events.runtimeExceptions, logErrors, loadingFailed: events.loadingFailed }));

      return {
        label, requestedViewport: { width, height }, ready, screenshot: screenshotPath,
        screenshotPixels: { width: Math.ceil(content.width), height: Math.ceil(content.height) },
        dom: { ...dom, bodyText: undefined },
        networkResponses: events.responses,
        consoleMessages: events.console,
        runtimeExceptions: events.runtimeExceptions,
        logEntries: events.log,
        loadingFailed: events.loadingFailed,
        assertions,
        pass: assertions.every(item => item.pass),
      };
    }

    result.viewports.push(await checkViewport(1440, 1600, "desktop-1440", DESKTOP_SHOT));
    result.viewports.push(await checkViewport(390, 844, "mobile-390x844", MOBILE_SHOT));
    result.assertions.push(...result.viewports.flatMap(viewport => viewport.assertions));
    result.overallPass = result.assertions.every(item => item.pass);
    result.failedAssertions = result.assertions.filter(item => !item.pass);

    const summaryLines = [
      TASK_LABEL,
      `overall: ${result.overallPass ? "PASS" : "FAIL"}`,
      `site: ${siteBase}`,
      `owned server PID: ${result.ownedProcesses.serverPid}`,
      `owned Edge PID: ${result.ownedProcesses.edgePid}`,
      `assertions: ${result.assertions.length - result.failedAssertions.length}/${result.assertions.length} passed`,
      `failed assertions: ${result.failedAssertions.length}`,
      ...result.viewports.map(viewport => `${viewport.label}: ${viewport.pass ? "PASS" : "FAIL"}; viewport=${viewport.dom.viewport.innerWidth}x${viewport.dom.viewport.innerHeight}; document overflow=${viewport.dom.documentWidth.difference}; screenshot=${viewport.screenshotPixels.width}x${viewport.screenshotPixels.height}; console error=${viewport.consoleMessages.filter(item => item.type === "error").length}; Runtime.exceptionThrown=${viewport.runtimeExceptions.length}; Log error=${viewport.logEntries.filter(item => item.level === "error").length}; Network.loadingFailed=${viewport.loadingFailed.length}`),
      `Expected values were read from ${siteBase}/data/gtfs_supply_metrics.json and compared with rendered DOM; no expected value is duplicated in this driver.`,
      "This raw result is evidence for subsequent Codex acceptance.",
    ];
    if (result.failedAssertions.length) {
      summaryLines.push("Failures:");
      for (const failed of result.failedAssertions) summaryLines.push(`- ${failed.name}: ${JSON.stringify(failed.actual)}`);
    }
    fs.writeFileSync(RAW_PATH, `${JSON.stringify(result, null, 2)}\n`, "utf8");
    fs.writeFileSync(SUMMARY_PATH, `${summaryLines.join("\n")}\n`, "utf8");
    console.log(summaryLines.join("\n"));
    if (!result.overallPass) process.exitCode = 2;
  } finally {
    if (ws) {
      if (targetId) await send(ws, "Target.closeTarget", { targetId }).catch(() => {});
      ws.close();
    }
    await stopOwned(edge);
    await stopOwned(server);
    for (let attempt = 0; attempt < 5; attempt += 1) {
      try {
        fs.rmSync(PROFILE, { recursive: true, force: true });
        break;
      } catch (error) {
        if (attempt === 4) throw error;
        await sleep(200);
      }
    }
  }
}

main().catch(error => {
  const message = `DRIVER_ERROR: ${error.stack || error}`;
  fs.writeFileSync(SUMMARY_PATH, `${message}\n`, "utf8");
  console.error(message);
  process.exitCode = 1;
});
