import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";

const REPO = "C:/Users/user/dev/udc2026/yamaguchi-yusho-data";
const DOCS = `${REPO}/docs`;
const OUT = `${REPO}/evidence`;
const PREFIX = process.env.VERIFY_EVIDENCE_PREFIX || "20260811_entry_page1_local";
const PUBLIC_BASE = process.env.VERIFY_SITE_BASE || null;
const PROFILE = `${OUT}/${PREFIX}_cdp_profile`;
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const RAW = `${OUT}/${PREFIX}_browser_raw.json`;
const SUMMARY = `${OUT}/${PREFIX}_browser_summary.txt`;
const SHOT_1440 = `${OUT}/${PREFIX}_screenshot_1440.png`;
const SHOT_390 = `${OUT}/${PREFIX}_screenshot_390x844.png`;
const EXPECTED_SUMMARY = "山口県の公共交通担当者・事業者向けに、分散した登録簿と公式GTFSを市町別に整理し、輸送供給・日付・根拠・データの限界を同じ画面で確認できる静的Webアプリです。";

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => server.once("error", reject).listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function waitFor(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let last;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
      last = new Error(`${response.status} ${response.statusText}`);
    } catch (error) {
      last = error;
    }
    await sleep(150);
  }
  throw new Error(`timeout waiting for ${url}: ${last?.message || "unknown"}`);
}

function contentType(file) {
  if (file.endsWith(".html")) return "text/html; charset=utf-8";
  if (file.endsWith(".json")) return "application/json; charset=utf-8";
  if (file.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

function localServer(port) {
  return http.createServer((request, response) => {
    const requested = decodeURIComponent(new URL(request.url, `http://127.0.0.1:${port}`).pathname);
    const relative = requested === "/" ? "index.html" : requested.replace(/^\//, "");
    const root = path.resolve(DOCS);
    const file = path.resolve(DOCS, relative);
    if (!(file === root || file.startsWith(`${root}${path.sep}`)) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      response.end("not found");
      return;
    }
    response.writeHead(200, { "Content-Type": contentType(file), "Cache-Control": "no-store" });
    fs.createReadStream(file).pipe(response);
  });
}

let nextId = 0;
function connect(url) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    socket.addEventListener("open", () => resolve(socket), { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
}

function send(socket, method, params = {}) {
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    const listener = event => {
      const message = JSON.parse(event.data);
      if (message.id !== id) return;
      socket.removeEventListener("message", listener);
      if (message.error) reject(new Error(`${method}: ${message.error.message}`));
      else resolve(message.result || {});
    };
    socket.addEventListener("message", listener);
    socket.send(JSON.stringify({ id, method, params }));
  });
}

function check(name, pass, actual) {
  return { name, pass: Boolean(pass), actual };
}

async function stopProcess(child) {
  if (!child?.pid) return;
  await new Promise(resolve => {
    const killer = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
    killer.once("exit", resolve);
    killer.once("error", resolve);
  });
}

async function removeOwnedProfile() {
  let last;
  for (let attempt = 0; attempt < 15; attempt += 1) {
    try {
      fs.rmSync(PROFILE, { recursive: true, force: true });
      return;
    } catch (error) {
      last = error;
      await sleep(200);
    }
  }
  throw last;
}

async function main() {
  if (!path.resolve(PROFILE).replaceAll("\\", "/").startsWith(`${path.resolve(OUT).replaceAll("\\", "/")}/${PREFIX}_`)) {
    throw new Error(`unsafe profile path: ${PROFILE}`);
  }
  await removeOwnedProfile();
  fs.mkdirSync(PROFILE, { recursive: true });

  const sitePort = PUBLIC_BASE ? null : await freePort();
  const cdpPort = await freePort();
  const siteBase = (PUBLIC_BASE || `http://127.0.0.1:${sitePort}`).replace(/\/$/, "");
  const pageUrl = `${siteBase}/entry.html`;
  let server;
  let edge;
  let socket;
  const events = { console: [], runtime: [], log: [], loadingFailed: [], responses: [] };
  const result = {
    task: "ENTRY-PAGE-1 actual-browser verification",
    mode: PUBLIC_BASE ? "public" : "local",
    pageUrl,
    generatedAt: new Date().toISOString(),
    viewports: [],
    assertions: [],
    failedAssertions: [],
  };

  try {
    if (!PUBLIC_BASE) {
      server = localServer(sitePort);
      await new Promise((resolve, reject) => server.once("error", reject).listen(sitePort, "127.0.0.1", resolve));
      await waitFor(pageUrl);
    }

    edge = spawn(EDGE, [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      `--remote-debugging-port=${cdpPort}`,
      `--user-data-dir=${PROFILE}`,
      "about:blank",
    ], { windowsHide: true, stdio: "ignore" });

    await waitFor(`http://127.0.0.1:${cdpPort}/json/version`);
    const targetResponse = await fetch(`http://127.0.0.1:${cdpPort}/json/new?about:blank`, { method: "PUT" });
    const target = await targetResponse.json();
    socket = await connect(target.webSocketDebuggerUrl);

    socket.addEventListener("message", event => {
      const message = JSON.parse(event.data);
      if (message.method === "Runtime.consoleAPICalled") {
        events.console.push({ type: message.params.type, text: (message.params.args || []).map(x => x.value ?? x.description ?? "").join(" ") });
      } else if (message.method === "Runtime.exceptionThrown") {
        events.runtime.push(message.params.exceptionDetails?.text || "exception");
      } else if (message.method === "Log.entryAdded") {
        events.log.push({ level: message.params.entry.level, text: message.params.entry.text });
      } else if (message.method === "Network.loadingFailed") {
        events.loadingFailed.push({ url: message.params.requestId, errorText: message.params.errorText });
      } else if (message.method === "Network.responseReceived") {
        events.responses.push({ url: message.params.response.url, status: message.params.response.status });
      }
    });

    for (const domain of ["Page", "Runtime", "Log", "Network"]) await send(socket, `${domain}.enable`);

    async function verifyViewport(width, height, label, screenshotPath) {
      for (const key of Object.keys(events)) events[key] = [];
      await send(socket, "Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width <= 390 });
      await send(socket, "Page.navigate", { url: `${pageUrl}?v=${Date.now()}` });

      const deadline = Date.now() + 15000;
      let ready = false;
      while (Date.now() < deadline) {
        const state = await send(socket, "Runtime.evaluate", { expression: "document.readyState", returnByValue: true });
        if (state.result?.value === "complete") { ready = true; break; }
        await sleep(100);
      }
      await sleep(250);

      const evaluated = await send(socket, "Runtime.evaluate", {
        expression: `(() => {
          const widths = [document.documentElement.scrollWidth, document.documentElement.offsetWidth, document.documentElement.clientWidth, document.body.scrollWidth, document.body.offsetWidth, document.body.clientWidth];
          const headings = [...document.querySelectorAll('h2')].map(x => x.textContent.trim());
          const links = [...document.querySelectorAll('a')].map(x => ({ text: x.textContent.trim(), href: x.getAttribute('href') }));
          return {
            title: document.title,
            summary: document.querySelector('#entry-summary')?.textContent.trim() || null,
            viewport: { innerWidth, innerHeight },
            documentWidth: {
              maximum: Math.max(...widths),
              rawDifference: Math.max(...widths) - innerWidth,
              overflow: Math.max(0, Math.max(...widths) - innerWidth),
            },
            headings,
            links,
            bodyText: document.body.innerText,
          };
        })()`,
        returnByValue: true,
      });
      const dom = evaluated.result.value;
      const layout = await send(socket, "Page.getLayoutMetrics");
      const content = layout.cssContentSize || layout.contentSize;
      const capture = await send(socket, "Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: true,
        clip: { x: 0, y: 0, width: Math.ceil(content.width), height: Math.ceil(content.height), scale: 1 },
      });
      fs.writeFileSync(screenshotPath, Buffer.from(capture.data, "base64"));

      const requiredHeadings = ["解決したい問題", "誰が、何のために使うか", "3段階の使い方", "使用データと、現在確認できる範囲", "実用度・完成度・挑戦度の根拠", "分かること／分からないこと"];
      const errors = {
        console: events.console.filter(x => x.type === "error"),
        runtime: [...events.runtime],
        log: events.log.filter(x => x.level === "error"),
        loadingFailed: [...events.loadingFailed],
      };
      const documentResponse = events.responses.find(x => x.url.startsWith(pageUrl));
      const assertions = [
        check(`${label}: ready`, ready, ready),
        check(`${label}: viewport`, dom.viewport.innerWidth === width && dom.viewport.innerHeight === height, dom.viewport),
        check(`${label}: document overflow`, dom.documentWidth.overflow === 0, dom.documentWidth),
        check(`${label}: HTTP 200`, documentResponse?.status === 200, documentResponse || null),
        check(`${label}: summary exact`, dom.summary === EXPECTED_SUMMARY, dom.summary),
        check(`${label}: six required headings`, requiredHeadings.every(x => dom.headings.includes(x)), dom.headings),
        check(`${label}: demo link`, dom.links.some(x => x.href === "index.html"), dom.links),
        check(`${label}: comparison link`, dom.links.some(x => x.href === "index.html#supply-comparison"), dom.links),
        check(`${label}: status link`, dom.links.some(x => x.href === "status.html"), dom.links),
        check(`${label}: repository link`, dom.links.some(x => x.href === "https://github.com/yyy-yuichi/yamaguchi-yusho-data"), dom.links),
        check(`${label}: no application completion claim`, !/応募済み|外部提出済み|受賞済み|受賞しました/.test(dom.bodyText), null),
        check(`${label}: console error 0`, errors.console.length === 0, errors.console),
        check(`${label}: runtime exception 0`, errors.runtime.length === 0, errors.runtime),
        check(`${label}: log error 0`, errors.log.length === 0, errors.log),
        check(`${label}: network loadingFailed 0`, errors.loadingFailed.length === 0, errors.loadingFailed),
      ];
      return { label, pass: assertions.every(x => x.pass), dom, errors, screenshotPath, assertions };
    }

    result.viewports.push(await verifyViewport(1440, 1600, "desktop-1440", SHOT_1440));
    result.viewports.push(await verifyViewport(390, 844, "mobile-390x844", SHOT_390));
    result.assertions = result.viewports.flatMap(x => x.assertions);
    result.failedAssertions = result.assertions.filter(x => !x.pass);
    result.overallPass = result.failedAssertions.length === 0;

    const summary = [
      "ENTRY-PAGE-1 actual-browser verification",
      `mode: ${result.mode}`,
      `url: ${pageUrl}`,
      `overall: ${result.overallPass ? "PASS" : "FAIL"}`,
      `assertions: ${result.assertions.length - result.failedAssertions.length}/${result.assertions.length} passed`,
      `failed assertions: ${result.failedAssertions.length}`,
      ...result.viewports.map(x => `${x.label}: ${x.pass ? "PASS" : "FAIL"}; viewport=${x.dom.viewport.innerWidth}x${x.dom.viewport.innerHeight}; document overflow=${x.dom.documentWidth.overflow}; console=${x.errors.console.length}; runtime=${x.errors.runtime.length}; log=${x.errors.log.length}; loadingFailed=${x.errors.loadingFailed.length}; screenshot=${path.basename(x.screenshotPath)}`),
    ];
    if (result.failedAssertions.length) for (const failed of result.failedAssertions) summary.push(`- ${failed.name}: ${JSON.stringify(failed.actual)}`);
    fs.writeFileSync(RAW, `${JSON.stringify(result, null, 2)}\n`, "utf8");
    fs.writeFileSync(SUMMARY, `${summary.join("\n")}\n`, "utf8");
    console.log(summary.join("\n"));
    if (!result.overallPass) process.exitCode = 2;
  } finally {
    try { socket?.close(); } catch {}
    await stopProcess(edge);
    if (server) await new Promise(resolve => server.close(resolve));
    await removeOwnedProfile();
  }
}

main().catch(error => {
  const message = `DRIVER_ERROR: ${error.stack || error}`;
  fs.writeFileSync(SUMMARY, `${message}\n`, "utf8");
  console.error(message);
  process.exitCode = 1;
});
