#!/usr/bin/env node
/**
 * Playwright screenshot capture script.
 * Serves HTML pages locally and takes full-page screenshots at 1440px wide.
 *
 * Usage:
 *   node screenshot_capture.js --source-dir /path/to/source --out-dir /path/to/screenshots --blueprint /path/to/blueprint.json
 */
const fs = require("fs");
const path = require("path");
const http = require("http");
const { chromium } = require("playwright");

const VIEWPORT_WIDTH = 1440;
const PORT = Math.floor(Math.random() * 20000) + 30000;

function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return fallback;
  return process.argv[index + 1];
}

function servedir(dir, port) {
  const server = http.createServer((req, res) => {
    let filePath = path.join(dir, req.url === "/" ? "home.html" : req.url);
    // strip query string
    filePath = filePath.split("?")[0];
    if (!path.extname(filePath)) filePath += ".html";
    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end("not found");
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      const mime =
        ext === ".html" ? "text/html" :
        ext === ".css" ? "text/css" :
        ext === ".js" ? "application/javascript" :
        "application/octet-stream";
      res.writeHead(200, { "Content-Type": mime });
      res.end(data);
    });
  });
  server.listen(port);
  return server;
}

async function waitForStability(page) {
  await page.waitForLoadState("domcontentloaded", { timeout: 15000 });
  await page.waitForLoadState("load", { timeout: 15000 }).catch(() => {});
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
  }).catch(() => {});
  // Give CSS transitions / animations a moment to settle
  await page.waitForTimeout(800);
}

async function main() {
  const sourceDir = argValue("--source-dir", null);
  const outDir = argValue("--out-dir", null);
  const reportPath = argValue("--report", path.join(outDir || ".", "screenshot_report.json"));

  if (!sourceDir || !outDir) {
    console.error("Usage: node screenshot_capture.js --source-dir <dir> --out-dir <dir>");
    process.exit(1);
  }

  fs.mkdirSync(outDir, { recursive: true });
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });

  // List all HTML files in source dir
  const htmlFiles = fs.readdirSync(sourceDir).filter(f => f.endsWith(".html"));
  const pages = htmlFiles.map(f => ({ slug: f.replace(".html", ""), file: f }));

  const server = servedir(sourceDir, PORT);
  const browser = await chromium.launch({ headless: true });

  const failures = [];
  const pageReports = [];

  try {
    for (const page of pages) {
      const url = `http://127.0.0.1:${PORT}/${page.file}`;
      const outPath = path.join(outDir, `${page.slug}.png`);
      const pageReport = { slug: page.slug, path: `${page.slug}.png`, failures: [] };

      try {
        const context = await browser.newContext({
          viewport: { width: VIEWPORT_WIDTH, height: 900 },
        });
        const bpage = await context.newPage();
        const response = await bpage.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });

        const status = response ? response.status() : null;
        pageReport.response_status = status;

        if (!status || status < 200 || status >= 300) {
          throw new Error(`HTTP ${status}`);
        }

        await waitForStability(bpage);

        // Full-page screenshot (scrolls to capture entire page height)
        await bpage.screenshot({
          path: outPath,
          fullPage: true,
        });

        const stat = fs.statSync(outPath);
        pageReport.bytes = stat.size;
        if (stat.size < 5000) {
          throw new Error(`Screenshot suspiciously small: ${stat.size} bytes`);
        }

        // Record actual page dimensions
        const dims = await bpage.evaluate(() => ({
          width: document.documentElement.scrollWidth,
          height: document.documentElement.scrollHeight,
        }));
        pageReport.page_width = dims.width;
        pageReport.page_height = dims.height;

        console.log(`  [screenshot] ${page.slug}: ${dims.width}x${dims.height}px, ${stat.size} bytes`);
        await context.close();
      } catch (err) {
        const msg = `Screenshot failed for ${page.slug}: ${err.message}`;
        failures.push(msg);
        pageReport.failures.push(msg);
        console.error(`  [screenshot] ERROR: ${msg}`);
      }

      pageReports.push(pageReport);
    }
  } finally {
    await browser.close();
    server.close();
  }

  const valid = failures.length === 0 && pages.length > 0;
  const report = {
    valid,
    viewport_width: VIEWPORT_WIDTH,
    pages: pageReports,
    failures,
    metrics: {
      expected: pages.length,
      captured: pageReports.filter(p => p.bytes && p.bytes > 5000).length,
    },
  };

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + "\n");
  process.exit(valid ? 0 : 2);
}

main().catch(err => {
  console.error("Fatal:", err);
  process.exit(2);
});
