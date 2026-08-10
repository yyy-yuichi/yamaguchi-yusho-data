// I-5 verification driver (part 2): scroll to specific sections and capture
// screenshots of the new GTFS and T1-T4 sections, desktop + mobile.
const CDP_BASE = "http://localhost:9335";
const SITE_BASE = "http://localhost:8793";
const OUT_DIR = "C:/Users/user/dev/udc2026/yamaguchi-yusho-data/evidence";

function rid() { return Math.floor(Math.random() * 1e9); }

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
  await send(ws, "Page.enable");
  await send(ws, "Runtime.enable");
  const fs = await import("node:fs");

  async function shotSection(width, height, label, anchorId, fileTag) {
    await send(ws, "Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 1, mobile: width < 500,
    });
    await send(ws, "Page.navigate", { url: `${SITE_BASE}/status.html#${anchorId}` });
    await new Promise(r => setTimeout(r, 700));
    await send(ws, "Runtime.evaluate", {
      expression: `document.getElementById(${JSON.stringify(anchorId)}).scrollIntoView({block:'start'})`,
    });
    await new Promise(r => setTimeout(r, 300));
    const shot = await send(ws, "Page.captureScreenshot", { format: "png" });
    const shotPath = `${OUT_DIR}/20260810_i5_screenshot_${label}_${fileTag}.png`;
    fs.writeFileSync(shotPath, Buffer.from(shot.data, "base64"));
    return shotPath;
  }

  const paths = [];
  paths.push(await shotSection(1280, 900, "desktop", "gtfs-title", "gtfs_section"));
  paths.push(await shotSection(390, 844, "mobile", "gtfs-title", "gtfs_section"));
  paths.push(await shotSection(1280, 900, "desktop", "terms-title", "terms_section"));
  paths.push(await shotSection(390, 844, "mobile", "terms-title", "terms_section"));

  await send(ws, "Target.closeTarget", { targetId: target.id }).catch(() => {});
  ws.close();
  console.log(JSON.stringify(paths, null, 2));
}

run().catch(err => {
  console.error("DRIVER_ERROR", err);
  process.exit(1);
});
