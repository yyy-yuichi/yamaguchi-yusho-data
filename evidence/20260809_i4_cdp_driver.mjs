// I-4 verification driver: raw CDP over WebSocket, no npm dependency.
// Node >=22 has a global WebSocket client, so this needs nothing installed.
const CDP_BASE = "http://localhost:9333";
const SITE_BASE = "http://localhost:8791";

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

  const results = [];

  async function checkViewport(width, height, label) {
    consoleMessages.length = 0;
    pageErrors.length = 0;
    await send(ws, "Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: width < 500,
    });

    const municipalities = [
      ["岩国市", "iwakuni"],
      ["光市", "hikari"],
      ["宇部市", "ube"],
      ["美祢市", "mine"],
      ["山陽小野田市", "sanyoonoda"],
      ["山口市", "yamaguchi"],
      ["下関市", "shimonoseki"],
    ];
    for (const [muni, safeMuni] of municipalities) {
      const url = `${SITE_BASE}/index.html?municipality=${encodeURIComponent(muni)}`;
      await send(ws, "Page.navigate", { url });
      await new Promise(r => setTimeout(r, 900));

      const evalResult = await send(ws, "Runtime.evaluate", {
        expression: `(() => {
          const doc = document.documentElement;
          const overflowX = doc.scrollWidth - doc.clientWidth;
          const gtfsResult = document.getElementById("gtfs-result");
          const gtfsHidden = gtfsResult ? gtfsResult.hidden : null;
          const badge = document.getElementById("gtfs-availability-badge");
          const body = document.getElementById("gtfs-availability-body");
          const scopeNote = document.getElementById("gtfs-scope-note");
          const feedCards = document.querySelectorAll("#gtfs-feed-list > article").length;
          const feedCount = document.getElementById("gtfs-feed-count").textContent;
          const muniCount = document.getElementById("gtfs-municipality-count").textContent;
          const caveatHidden = document.getElementById("gtfs-caveat").hidden;
          const errorShown = !document.getElementById("error").hidden;
          const resultVisible = !document.getElementById("result").hidden;
          return JSON.stringify({
            overflowX, gtfsHidden, badge: badge && badge.textContent,
            body: body && body.textContent, scopeNote: scopeNote && scopeNote.textContent,
            feedCards, feedCount, muniCount, caveatHidden, errorShown, resultVisible,
            title: document.title,
          });
        })()`,
        returnByValue: true,
      });

      const shot = await send(ws, "Page.captureScreenshot", { format: "png" });
      const fs = await import("node:fs");
      const shotPath = `C:/Users/user/dev/udc2026/yamaguchi-yusho-data/evidence/20260809_i4_screenshot_${label}_${safeMuni}.png`;
      fs.writeFileSync(shotPath, Buffer.from(shot.data, "base64"));

      results.push({
        label, width, height, municipality: muni,
        data: JSON.parse(evalResult.result.value),
        consoleMessages: [...consoleMessages],
        pageErrors: [...pageErrors],
        screenshot: shotPath,
      });
      consoleMessages.length = 0;
      pageErrors.length = 0;
    }
  }

  await checkViewport(1280, 900, "desktop");
  await checkViewport(390, 844, "mobile");

  await send(ws, "Target.closeTarget", { targetId: target.id }).catch(() => {});
  ws.close();

  console.log(JSON.stringify(results, null, 2));
}

run().catch(err => {
  console.error("DRIVER_ERROR", err);
  process.exit(1);
});
