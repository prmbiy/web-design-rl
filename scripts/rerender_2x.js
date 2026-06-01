#!/usr/bin/env node
/**
 * Re-renders all GT and agent screenshots at 2x deviceScaleFactor.
 * Replaces existing PNGs in-place.
 *
 * Usage: node scripts/rerender_2x.js [--concurrency 10]
 *
 * For each task:
 *   GT:    tasks/<task>/source/       → tasks/<task>/screenshots/
 *   Agent: tasks/<task>/agent_result/source/ → tasks/<task>/agent_result/agent_screenshots/
 */
const fs = require("fs");
const path = require("path");
const http = require("http");
const { chromium } = require("playwright");

const VIEWPORT_WIDTH = 1440;
const DEVICE_SCALE_FACTOR = 2;

function argValue(name, fallback) {
  const i = process.argv.indexOf(name);
  return i !== -1 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback;
}

const CONCURRENCY = parseInt(argValue("--concurrency", "10"), 10);
const TASKS_DIR = path.resolve(__dirname, "..", "tasks");

function findTasks() {
  return fs.readdirSync(TASKS_DIR)
    .filter(n => n.startsWith("task_"))
    .map(n => path.join(TASKS_DIR, n))
    .filter(p => fs.statSync(p).isDirectory())
    .sort();
}

function makeServer(sourceDir, port) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      let filePath = path.join(sourceDir, req.url === "/" ? "home.html" : req.url);
      filePath = filePath.split("?")[0];
      if (!path.extname(filePath)) filePath += ".html";
      fs.readFile(filePath, (err, data) => {
        if (err) { res.writeHead(404); res.end("not found"); return; }
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(data);
      });
    });
    server.once("error", reject);
    // port=0 lets the OS pick a free port
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

async function renderDir(browser, sourceDir, outDir) {
  if (!fs.existsSync(sourceDir)) return { rendered: 0, skipped: 0 };

  const htmlFiles = fs.readdirSync(sourceDir).filter(f => f.endsWith(".html"));
  if (!htmlFiles.length) return { rendered: 0, skipped: 0 };

  fs.mkdirSync(outDir, { recursive: true });
  const server = await makeServer(sourceDir);
  const port = server.address().port;
  let rendered = 0, skipped = 0;

  try {
    for (const file of htmlFiles) {
      const slug = file.replace(".html", "");
      const outPath = path.join(outDir, `${slug}.png`);
      try {
        const context = await browser.newContext({
          viewport: { width: VIEWPORT_WIDTH, height: 900 },
          deviceScaleFactor: DEVICE_SCALE_FACTOR,
        });
        const page = await context.newPage();
        await page.goto(`http://127.0.0.1:${port}/${file}`, { waitUntil: "domcontentloaded", timeout: 15000 });
        await page.waitForLoadState("load", { timeout: 15000 }).catch(() => {});
        await page.evaluate(async () => { if (document.fonts?.ready) await document.fonts.ready; }).catch(() => {});
        await page.waitForTimeout(800);
        await page.screenshot({ path: outPath, fullPage: true });
        await context.close();
        rendered++;
      } catch (err) {
        console.error(`    ERROR ${slug}: ${err.message}`);
        skipped++;
      }
    }
  } finally {
    server.close();
  }
  return { rendered, skipped };
}

async function processTask(taskDir) {
  const taskName = path.basename(taskDir);
  const browser = await chromium.launch({ headless: true });
  let totalRendered = 0, totalSkipped = 0;

  try {
    // GT screenshots
    const gtSource = path.join(taskDir, "source");
    const gtOut = path.join(taskDir, "screenshots");
    const gt = await renderDir(browser, gtSource, gtOut);
    totalRendered += gt.rendered;
    totalSkipped += gt.skipped;

    // Agent screenshots
    const agentSource = path.join(taskDir, "harbor", "solution", "site");
    const agentOut = path.join(taskDir, "agent_result", "agent_screenshots");
    const agent = await renderDir(browser, agentSource, agentOut);
    totalRendered += agent.rendered;
    totalSkipped += agent.skipped;
  } finally {
    await browser.close();
  }

  console.log(`  ${taskName}: ${totalRendered} rendered, ${totalSkipped} errors`);
  return { totalRendered, totalSkipped };
}

async function main() {
  const tasks = findTasks();
  console.log(`Found ${tasks.length} tasks, concurrency=${CONCURRENCY}`);

  let globalRendered = 0, globalSkipped = 0;
  const start = Date.now();

  // Process tasks in batches of CONCURRENCY
  for (let i = 0; i < tasks.length; i += CONCURRENCY) {
    const batch = tasks.slice(i, i + CONCURRENCY);
    const results = await Promise.all(
      batch.map((taskDir) => processTask(taskDir))
    );
    for (const r of results) {
      globalRendered += r.totalRendered;
      globalSkipped += r.totalSkipped;
    }
    console.log(`Batch ${Math.floor(i / CONCURRENCY) + 1} done (${i + batch.length}/${tasks.length} tasks)`);
  }

  const elapsed = ((Date.now() - start) / 1000).toFixed(1);
  console.log(`\nDone in ${elapsed}s — ${globalRendered} rendered, ${globalSkipped} errors`);
}

main().catch(err => { console.error("Fatal:", err); process.exit(1); });
