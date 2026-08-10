// I-5 verification driver: raw CDP over WebSocket, no npm dependency.
// Checks docs/status.html at desktop and mobile widths, and exercises the
// real links to docs/index.html and the public JSON files.
const CDP_BASE = "http://localhost:9335";
const SITE_BASE = "http://localhost:8793";
const OUT_DIR = "C:/Users/user/dev/udc2026/yamaguchi-yusho-data/evidence";

function rid() {
  return Math.floor(Math.random() * 1e9);
}

async function newTarget() {
  const res = await fetch(`${CDP_BASE}/json/new?about:blank`, { method: "PUT" });
  return res.json();
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.addEventListener("open", () => resolve(ws));
    ws.addEventListener("error", reject);
  });
}

function send(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = rid();
    const handler = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id === id) {
        ws.removeEventListener("message", handler);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    };
    ws.addEventListener("message", handler);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function run() {
  const target = await newTarget();
  const ws = await connect(target.webSocketDebuggerUrl);

  const consoleMessages = [];
  const pageErrors = [];
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.method === "Runtime.consoleAPICalled") {
      const text = (msg.params.args || []).map(a => a.value ?? a.description ?? "").join(" ");
      consoleMessages.push({ type: msg.params.type, text });
    }
    if (msg.method === "Runtime.exceptionThrown") {
      pageErrors.push(msg.params.exceptionDetails.text || JSON.stringify(msg.params.exceptionDetails));
    }
  });

  await send(ws, "Page.enable");
  await send(ws, "Runtime.enable");
  await send(ws, "Log.enable");

  const results = { viewports: [], linkChecks: [] };
  const fs = await import("node:fs");

  async function gotoStatus() {
    await send(ws, "Page.navigate", { url: `${SITE_BASE}/status.html` });
    await new Promise(r => setTimeout(r, 700));
  }

  async function checkViewport(width, height, label) {
    consoleMessages.length = 0;
    pageErrors.length = 0;
    await send(ws, "Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: width < 500,
    });
    await gotoStatus();

    const evalResult = await send(ws, "Runtime.evaluate", {
      expression: `(() => {
        const doc = document.documentElement;
        const overflowX = doc.scrollWidth - doc.clientWidth;
        const sections = document.querySelectorAll('section').length;
        const hasTerms = document.body.textContent.includes('T1') &&
          document.body.textContent.includes('T4') &&
          document.body.textContent.includes('未達');
        const hasGtfsSection = !!document.getElementById('gtfs-title');
        const roadmapItems = document.querySelectorAll('.roadmap li').length;
        return JSON.stringify({
          overflowX, sections, hasTerms, hasGtfsSection, roadmapItems,
          title: document.title,
          scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth,
        });
      })()`,
      returnByValue: true,
    });

    const shot = await send(ws, "Page.captureScreenshot", { format: "png" });
    const shotPath = `${OUT_DIR}/20260810_i5_screenshot_${label}_status.png`;
    fs.writeFileSync(shotPath, Buffer.from(shot.data, "base64"));

    results.viewports.push({
      label, width, height,
      data: JSON.parse(evalResult.result.value),
      consoleMessages: [...consoleMessages],
      pageErrors: [...pageErrors],
      screenshot: shotPath,
    });
  }

  async function clickLinkAndCheck(label, hrefSubstring, expectation) {
    consoleMessages.length = 0;
    pageErrors.length = 0;
    await send(ws, "Emulation.setDeviceMetricsOverride", {
      width: 1280, height: 900, deviceScaleFactor: 1, mobile: false,
    });
    await gotoStatus();

    const clickResult = await send(ws, "Runtime.evaluate", {
      expression: `(() => {
        const anchors = Array.from(document.querySelectorAll('a'));
        const target = anchors.find(a => (a.getAttribute('href') || '').includes(${JSON.stringify(hrefSubstring)}));
        if (!target) return JSON.stringify({ found: false });
        const href = target.getAttribute('href');
        target.click();
        return JSON.stringify({ found: true, href });
      })()`,
      returnByValue: true,
    });
    const clickInfo = JSON.parse(clickResult.result.value);
    await new Promise(r => setTimeout(r, 700));

    const afterNav = await send(ws, "Runtime.evaluate", {
      expression: `(() => {
        let bodyIsValidJson = null;
        let jsonLength = null;
        try {
          const text = document.body.innerText || document.body.textContent || "";
          const parsed = JSON.parse(text);
          bodyIsValidJson = true;
          jsonLength = Array.isArray(parsed) ? parsed.length : Object.keys(parsed).length;
        } catch (e) {
          bodyIsValidJson = false;
        }
        return JSON.stringify({
          url: document.location.href,
          title: document.title,
          bodyIsValidJson, jsonLength,
          bodySnippet: (document.body.innerText || "").slice(0, 200),
        });
      })()`,
      returnByValue: true,
    });

    results.linkChecks.push({
      label,
      clickInfo,
      afterNav: JSON.parse(afterNav.result.value),
      consoleMessages: [...consoleMessages],
      pageErrors: [...pageErrors],
    });
  }

  await checkViewport(1280, 900, "desktop");
  await checkViewport(390, 844, "mobile");

  await clickLinkAndCheck("index.html", "index.html?v=20260810", null);
  await clickLinkAndCheck("gtfs_feeds.json", "data/gtfs_feeds.json", null);
  await clickLinkAndCheck("municipality_gtfs.json", "data/municipality_gtfs.json", null);
  await clickLinkAndCheck("operators.json", "data/operators.json", null);
  await clickLinkAndCheck("vehicles.json", "data/vehicles.json", null);

  await send(ws, "Target.closeTarget", { targetId: target.id }).catch(() => {});
  ws.close();

  console.log(JSON.stringify(results, null, 2));
}

run().catch(err => {
  console.error("DRIVER_ERROR", err);
  process.exit(1);
});
