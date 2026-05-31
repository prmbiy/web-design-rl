#!/usr/bin/env node
/**
 * Screen recording capture script for animated sites.
 * Records scroll-through videos at 1440x1000, then converts to mp4 via ffmpeg.
 *
 * Usage:
 *   node screenrecording_capture.js --source-dir <dir> --out-dir <dir> --slugs home,about
 */
const fs = require("fs");
const path = require("path");
const http = require("http");
const { spawnSync } = require("child_process");
const { chromium } = require("playwright");

const VIEWPORT = { width: 1440, height: 1000 };
const TOP_HOLD_MS = 2500;
const BOTTOM_HOLD_MS = 2000;
const MIN_SCROLL_MS = 7000;
const MAX_SCROLL_MS = 15000;
const PORT = Math.floor(Math.random() * 20000) + 30000;

function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return fallback;
  return process.argv[index + 1];
}

function servedir(dir, port) {
  const server = http.createServer((req, res) => {
    let filePath = path.join(dir, req.url === "/" ? "home.html" : req.url);
    filePath = filePath.split("?")[0];
    if (!path.extname(filePath)) filePath += ".html";
    fs.readFile(filePath, (err, data) => {
      if (err) { res.writeHead(404); res.end("not found"); return; }
      const ext = path.extname(filePath).toLowerCase();
      const mime = ext === ".html" ? "text/html" : ext === ".css" ? "text/css" : "application/octet-stream";
      res.writeHead(200, { "Content-Type": mime });
      res.end(data);
    });
  });
  server.listen(port);
  return server;
}

function convertWebmToMp4(inputPath, outputPath) {
  const result = spawnSync("ffmpeg", [
    "-y", "-i", inputPath,
    "-an",
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-pix_fmt", "yuv420p",
    "-r", "25",
    "-fps_mode", "cfr",
    "-movflags", "+faststart",
    outputPath,
  ], { encoding: "utf8" });

  if (result.status !== 0) {
    throw new Error(`ffmpeg failed (${result.status}): ${result.stderr || result.stdout}`);
  }
}

async function waitForStability(page) {
  await page.waitForLoadState("domcontentloaded", { timeout: 15000 });
  await page.waitForLoadState("load", { timeout: 15000 }).catch(() => {});
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
  }).catch(() => {});
  await page.waitForTimeout(500);
}

async function scrollThrough(page, maxScrollY, durationMs) {
  await page.evaluate(async ({ maxScrollY, durationMs }) => {
    const html = document.documentElement;
    const body = document.body;
    const prevHtml = html.style.scrollBehavior;
    const prevBody = body ? body.style.scrollBehavior : "";
    html.style.scrollBehavior = "auto";
    if (body) body.style.scrollBehavior = "auto";

    // Inject override to prevent CSS smooth scroll interference
    const override = document.createElement("style");
    override.setAttribute("data-override", "screenrecording");
    override.textContent = "html, body, * { scroll-behavior: auto !important; }";
    document.head.appendChild(override);

    try {
      window.scrollTo({ left: 0, top: 0, behavior: "instant" });
      if (maxScrollY <= 0) return;
      await new Promise(resolve => {
        const startedAt = performance.now();
        function tick(now) {
          const progress = Math.min(1, (now - startedAt) / durationMs);
          const eased = progress < 0.5
            ? 2 * progress * progress
            : 1 - Math.pow(-2 * progress + 2, 2) / 2;
          window.scrollTo({ left: 0, top: Math.round(maxScrollY * eased), behavior: "instant" });
          if (progress < 1) requestAnimationFrame(tick);
          else resolve();
        }
        requestAnimationFrame(tick);
      });
    } finally {
      override.remove();
      html.style.scrollBehavior = prevHtml;
      if (body) body.style.scrollBehavior = prevBody;
    }
  }, { maxScrollY, durationMs });
}

async function main() {
  const sourceDir = argValue("--source-dir", null);
  const outDir = argValue("--out-dir", null);
  const slugsArg = argValue("--slugs", null);
  const reportPath = argValue("--report", path.join(outDir || ".", "screenrecording_report.json"));

  if (!sourceDir || !outDir) {
    console.error("Usage: node screenrecording_capture.js --source-dir <dir> --out-dir <dir> [--slugs slug1,slug2]");
    process.exit(1);
  }

  const allHtml = fs.readdirSync(sourceDir).filter(f => f.endsWith(".html")).map(f => f.replace(".html", ""));
  const slugs = slugsArg ? slugsArg.split(",") : allHtml;

  fs.mkdirSync(outDir, { recursive: true });
  const tmpDir = path.join(outDir, ".tmp_webm");
  fs.mkdirSync(tmpDir, { recursive: true });

  const server = servedir(sourceDir, PORT);
  const browser = await chromium.launch({ headless: true });

  const failures = [];
  const pageReports = [];

  try {
    for (const slug of slugs) {
      const url = `http://127.0.0.1:${PORT}/${slug}.html`;
      const outPath = path.join(outDir, `${slug}.mp4`);
      const pageReport = { slug, path: `${slug}.mp4`, failures: [] };

      const context = await browser.newContext({
        viewport: VIEWPORT,
        recordVideo: { dir: tmpDir, size: VIEWPORT },
      });
      const page = await context.newPage();
      const video = page.video();

      try {
        const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });
        const status = response ? response.status() : null;
        pageReport.response_status = status;

        if (!status || status < 200 || status >= 300) {
          throw new Error(`HTTP ${status}`);
        }

        await waitForStability(page);

        const scrollHeight = await page.evaluate(() => {
          const b = document.body, h = document.documentElement;
          return Math.max(b?.scrollHeight || 0, b?.offsetHeight || 0, h?.scrollHeight || 0, h?.offsetHeight || 0);
        });
        const maxScrollY = Math.max(0, scrollHeight - VIEWPORT.height);
        const scrollDurationMs = Math.min(MAX_SCROLL_MS, Math.max(MIN_SCROLL_MS, maxScrollY * 2));

        pageReport.scroll_height = scrollHeight;
        pageReport.max_scroll_y = maxScrollY;
        pageReport.scroll_duration_ms = scrollDurationMs;

        // Reset to top, hold, scroll, hold at bottom
        await page.evaluate(() => window.scrollTo({ left: 0, top: 0, behavior: "instant" }));
        await page.waitForTimeout(TOP_HOLD_MS);
        await scrollThrough(page, maxScrollY, scrollDurationMs);
        await page.waitForTimeout(BOTTOM_HOLD_MS);
        await page.waitForTimeout(300);

      } catch (err) {
        const msg = `Recording failed for ${slug}: ${err.message}`;
        failures.push(msg);
        pageReport.failures.push(msg);
        console.error(`  [screenrecording] ERROR: ${msg}`);
      } finally {
        await page.close().catch(() => {});
        await context.close().catch(() => {});
      }

      // Convert webm → mp4
      try {
        const webmPath = await video.path();
        if (fs.existsSync(outPath)) fs.rmSync(outPath);
        convertWebmToMp4(webmPath, outPath);
        pageReport.bytes = fs.statSync(outPath).size;
        if (pageReport.bytes <= 0) throw new Error("mp4 is empty");
        fs.rmSync(webmPath, { force: true });
        console.log(`  [screenrecording] ${slug}: ${pageReport.bytes} bytes mp4`);
      } catch (err) {
        const msg = `mp4 conversion failed for ${slug}: ${err.message}`;
        failures.push(msg);
        pageReport.failures.push(msg);
        console.error(`  [screenrecording] ERROR: ${msg}`);
      }

      pageReports.push(pageReport);
    }
  } finally {
    await browser.close();
    server.close();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }

  const captured = pageReports.filter(p => p.bytes && p.bytes > 0).length;
  const valid = failures.length === 0 && slugs.length > 0 && captured === slugs.length;

  const report = {
    valid,
    viewport: VIEWPORT,
    top_hold_ms: TOP_HOLD_MS,
    bottom_hold_ms: BOTTOM_HOLD_MS,
    output_dir: outDir,
    metrics: { expected: slugs.length, recorded: captured },
    failures,
    pages: pageReports,
  };

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + "\n");
  process.exit(valid ? 0 : 2);
}

main().catch(err => {
  console.error("Fatal:", err);
  process.exit(2);
});
