// Reproducible final checks for SUPPLY-VIEW-1 V4. Writes one UTF-8 evidence log.
import crypto from "node:crypto";
import fs from "node:fs";
import { spawnSync } from "node:child_process";

const REPO = "C:/Users/user/dev/udc2026/yamaguchi-yusho-data";
const OUT = `${REPO}/evidence/20260810_supply_view1_v4_final_checks_raw.txt`;
const sections = [];
const checks = [];
const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };

function run(label, command, args) {
  const result = spawnSync(command, args, { cwd: REPO, env, encoding: "utf8", windowsHide: true });
  const stdout = result.stdout || "";
  const stderr = result.stderr || "";
  sections.push(`=== ${label} ===\ncommand: ${command} ${args.join(" ")}\nexit: ${result.status}\n--- stdout ---\n${stdout}\n--- stderr ---\n${stderr}`);
  return { exit: result.status, stdout, stderr };
}

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function pngSize(file) {
  const data = fs.readFileSync(file);
  return { width: data.readUInt32BE(16), height: data.readUInt32BE(20), bytes: data.length, sha256: sha256(file) };
}

const focused = run("focused site unittest", "python", ["-B", "-m", "unittest", "tests.test_site", "-v"]);
checks.push(["focused 48 tests OK", focused.exit === 0 && /Ran 48 tests/.test(focused.stderr + focused.stdout) && /\bOK\b/.test(focused.stderr + focused.stdout)]);

const full = run("full unittest", "python", ["-B", "-m", "unittest", "discover", "-s", "tests", "-v"]);
checks.push(["full 80 tests OK", full.exit === 0 && /Ran 80 tests/.test(full.stderr + full.stdout) && /\bOK\b/.test(full.stderr + full.stdout)]);

for (const [label, before, after, tokenCount] of [
  ["spec coverage README", "evidence/20260810_supply_view1_readme_before.md", "README.md", 43],
  ["spec coverage status", "evidence/20260810_supply_view1_status_before.html", "docs/status.html", 0],
  ["spec coverage index", "evidence/20260810_supply_view1_index_before.html", "docs/index.html", 18],
]) {
  const coverage = run(label, "python", ["-B", "tools/spec_coverage.py", before, after]);
  checks.push([`${label}: ${tokenCount} tokens, missing 0`, coverage.exit === 0 && coverage.stdout.includes(`検査トークン数        : ${tokenCount}`) && coverage.stdout.includes("欠落・説明なし        : 0") && coverage.stdout.includes("判定: 合格")]);
}

const diffCheck = run("git diff check", "git", ["diff", "--check"]);
checks.push(["git diff --check exit 0", diffCheck.exit === 0]);
const staged = run("staged paths", "git", ["diff", "--cached", "--name-only"]);
checks.push(["staged count 0", staged.exit === 0 && staged.stdout.trim() === ""]);
const status = run("git status", "git", ["status", "--short", "--branch"]);

const browser = JSON.parse(fs.readFileSync(`${REPO}/evidence/20260810_supply_view1_browser_raw.json`, "utf8"));
const initialFail = JSON.parse(fs.readFileSync(`${REPO}/evidence/20260810_supply_view1_browser_initial_fail_raw.json`, "utf8"));
const browserSummary = {
  finalOverallPass: browser.overallPass,
  finalAssertions: `${browser.assertions.filter(item => item.pass).length}/${browser.assertions.length}`,
  finalFailed: browser.failedAssertions.length,
  initialOverallPass: initialFail.overallPass,
  initialAssertions: `${initialFail.assertions.filter(item => item.pass).length}/${initialFail.assertions.length}`,
  initialFailureNames: initialFail.failedAssertions.map(item => item.name),
  viewports: browser.viewports.map(viewport => ({
    label: viewport.label,
    requestedViewport: viewport.requestedViewport,
    actualViewport: viewport.dom.viewport,
    documentOverflow: viewport.dom.documentWidth.difference,
    consoleError: viewport.consoleMessages.filter(item => item.type === "error").length,
    runtimeException: viewport.runtimeExceptions.length,
    logError: viewport.logEntries.filter(item => item.level === "error").length,
    loadingFailed: viewport.loadingFailed.length,
  })),
};
sections.push(`=== browser proof ===\n${JSON.stringify(browserSummary, null, 2)}`);
checks.push(["browser assertions 28/28 PASS", browser.overallPass && browser.assertions.length === 28 && browser.failedAssertions.length === 0]);
checks.push(["initial favicon failure preserved as 27/28", initialFail.overallPass === false && initialFail.assertions.filter(item => item.pass).length === 27 && initialFail.failedAssertions.length === 1]);

const acceptanceFiles = ["PROGRESS.md", "README.md", "docs/status.html", "verification.md", "run_record.md"];
const strictStalePhrases = [
  "SUPPLY-VIEW-1受入待ち",
  "Codex受入待ち",
  "ブラウザ確認・Codex受入待ち",
  "ブラウザ未確認は完了条件の残件",
  "SUPPLY-VIEW-1は未受入",
  "SUPPLY-VIEW-1を受入済みとしない",
  "受入判定するまではSUPPLY-VIEW-1",
  "ブラウザ実確認とCodex独立受入は",
];
const staleAcceptanceMatches = [];
for (const file of acceptanceFiles) {
  const text = fs.readFileSync(`${REPO}/${file}`, "utf8");
  for (const phrase of strictStalePhrases) {
    if (text.includes(phrase)) staleAcceptanceMatches.push({ file, phrase });
  }
}
const acceptedMarkers = {
  "PROGRESS.md": "rev.36でSUPPLY-VIEW-1を受入済み",
  "README.md": "SUPPLY-VIEW-1 Codex受入済み",
  "docs/status.html": "SUPPLY-VIEW-1までCodex受入済み",
  "verification.md": "rev.36でSUPPLY-VIEW-1を受入済み",
  "run_record.md": "SUPPLY-VIEW-1 Codex受入済み・次作業未定義",
};
const missingAcceptedMarkers = Object.entries(acceptedMarkers).filter(([file, marker]) => !fs.readFileSync(`${REPO}/${file}`, "utf8").includes(marker));
sections.push(`=== acceptance-state synchronization ===\nstrict_stale_matches=${JSON.stringify(staleAcceptanceMatches)}\nmissing_accepted_markers=${JSON.stringify(missingAcceptedMarkers)}\nHistorical V3 browser-unavailable wording is retained only with explicit V3/time-of-record and V4-resolution context.`);
checks.push(["strict current SUPPLY-VIEW-1 pending phrases 0", staleAcceptanceMatches.length === 0]);
checks.push(["rev.36 accepted state present in all five control documents", missingAcceptedMarkers.length === 0]);

const html = fs.readFileSync(`${REPO}/docs/index.html`, "utf8");
const faviconMatches = html.match(/<link rel="icon" href="data:image\/svg\+xml,[^"]+">/g) || [];
sections.push(`=== inline favicon ===\nmatch_count=${faviconMatches.length}\nnetwork_independent=${faviconMatches.length === 1}`);
checks.push(["one network-independent inline favicon", faviconMatches.length === 1]);

const dataHash = sha256(`${REPO}/data/gtfs_supply_metrics.json`);
const publicHash = sha256(`${REPO}/docs/data/gtfs_supply_metrics.json`);
const iwakuniHash = sha256(`${REPO}/raw/gtfs/iwakuni_gtfsjp_20260401.zip`);
const hikariHash = sha256(`${REPO}/raw/gtfs/hikari_gtfs_20260401.zip`);
sections.push(`=== hashes ===\ndata/gtfs_supply_metrics.json ${dataHash}\ndocs/data/gtfs_supply_metrics.json ${publicHash}\nraw/gtfs/iwakuni_gtfsjp_20260401.zip ${iwakuniHash}\nraw/gtfs/hikari_gtfs_20260401.zip ${hikariHash}`);
checks.push(["input/public JSON byte-identical accepted hash", dataHash === publicHash && dataHash === "26167df77efce48e6dbcacde757a08ff40f7229fe99b9928f25b541f3766db9b"]);
checks.push(["raw ZIP hashes unchanged", iwakuniHash === "d236a58ff4a0edb4812a8bed543d4897670441164a1019e88d5e35ded5052de2" && hikariHash === "f3403ebaf481805fff0e2316be3a986732f443a06a64eab5b579ea17191adde7"]);

const desktopPng = pngSize(`${REPO}/evidence/20260810_supply_view1_screenshot_1440.png`);
const mobilePng = pngSize(`${REPO}/evidence/20260810_supply_view1_screenshot_390x844.png`);
sections.push(`=== screenshots ===\ndesktop ${JSON.stringify(desktopPng)}\nmobile ${JSON.stringify(mobilePng)}`);
checks.push(["screenshots are non-empty and mobile width is 390", desktopPng.bytes > 10000 && mobilePng.bytes > 10000 && mobilePng.width === 390]);

const porcelain = spawnSync("git", ["status", "--porcelain=v1", "-z"], { cwd: REPO, env, encoding: "utf8", windowsHide: true });
const dirtyPaths = porcelain.stdout.split("\0").filter(Boolean).map(entry => entry.slice(3)).filter(file => fs.existsSync(`${REPO}/${file}`));
const secretPatterns = [
  /(?:ghp_|github_pat_|xox[baprs]-|AKIA|AIza|sk-)[A-Za-z0-9_-]{16,}/g,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/g,
  /(?:api[_-]?key|password|client[_-]?secret|access[_-]?token)\s*[:=]\s*["']?[A-Za-z0-9+/_=-]{16,}/gi,
];
const secretHitFiles = [];
for (const file of dirtyPaths) {
  const fullPath = `${REPO}/${file}`;
  const stat = fs.statSync(fullPath);
  if (!stat.isFile() || stat.size > 2_000_000) continue;
  const data = fs.readFileSync(fullPath);
  if (data.includes(0)) continue;
  const text = data.toString("utf8");
  if (secretPatterns.some(pattern => { pattern.lastIndex = 0; return pattern.test(text); })) secretHitFiles.push(file);
}
sections.push(`=== secret-like scan ===\nscanned_dirty_text_files=${dirtyPaths.length}\nsecret_like_hits=${secretHitFiles.length}\nhit_files=${JSON.stringify(secretHitFiles)}`);
checks.push(["secret-like hits 0", secretHitFiles.length === 0]);

const profileExists = fs.existsSync(`${REPO}/evidence/20260810_supply_view1_cdp_profile`);
sections.push(`=== cleanup ===\ntemporary_profile_exists=${profileExists}\nThe CDP raw evidence records the exact owned server/Edge PIDs; the driver terminates those process trees in finally.`);
checks.push(["dedicated temporary profile removed", !profileExists]);

const v4Touched = [
  "README.md",
  "docs/status.html",
  "docs/index.html",
  "PROGRESS.md",
  "verification.md",
  "tests/test_site.py",
  "evidence/20260810_supply_view1_cdp_driver.mjs",
  "evidence/20260810_supply_view1_browser_initial_fail_raw.json",
  "evidence/20260810_supply_view1_browser_initial_fail_summary.txt",
  "evidence/20260810_supply_view1_browser_raw.json",
  "evidence/20260810_supply_view1_browser_summary.txt",
  "evidence/20260810_supply_view1_screenshot_1440.png",
  "evidence/20260810_supply_view1_screenshot_390x844.png",
  "evidence/20260810_supply_view1_v4_checks.mjs",
  "evidence/20260810_supply_view1_v4_final_checks_raw.txt",
];
sections.push(`=== V4 touch manifest ===\n${v4Touched.join("\n")}\nNo commit, push, publication, raw ZIP edit, calculation-code edit, SPEC.md edit, run_record.md edit, or CLAUDE.md edit was performed by this V4 driver.`);

const failed = checks.filter(([, pass]) => !pass);
const header = [
  "SUPPLY-VIEW-1 V4 final checks",
  `generated_at=${new Date().toISOString()}`,
  `overall=${failed.length === 0 ? "PASS" : "FAIL"}`,
  `checks=${checks.filter(([, pass]) => pass).length}/${checks.length}`,
  ...checks.map(([name, pass]) => `${pass ? "PASS" : "FAIL"}: ${name}`),
  "",
].join("\n");
fs.writeFileSync(OUT, `${header}${sections.join("\n\n")}\n`, "utf8");
console.log(header.trim());
if (failed.length) process.exitCode = 2;
