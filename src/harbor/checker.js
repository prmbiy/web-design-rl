/**
 * Completeness checker for web-design-rl Harbor tasks.
 *
 * Copied into environment/checker/run.js for each packaged task.
 * Runs as root inside the verifier container after the agent has finished.
 *
 * Usage:
 *   node run.js \
 *     --agent-site /app/site \
 *     --ground-truth-screenshots /task/screenshots \
 *     --captures-out /logs/verifier/agent_screenshots \
 *     --reward-out /logs/verifier/reward.json
 */

const fs = require("fs");
const http = require("http");
const path = require("path");

function parseArgs() {
  const args = {};
  for (let i = 2; i < process.argv.length; i += 2) {
    args[process.argv[i].replace(/^--/, "")] = process.argv[i + 1];
  }
  return args;
}

function getSlugs(screenshotsDir) {
  return fs
    .readdirSync(screenshotsDir)
    .filter((f) => f.endsWith(".png"))
    .map((f) => f.replace(".png", ""))
    .sort();
}

function startServer(siteDir, port) {
  const server = http.createServer((req, res) => {
    const filePath = path.join(siteDir, req.url === "/" ? "/index.html" : req.url);
    fs.readFile(filePath, (err, data) => {
      if (err) { res.writeHead(404); res.end("Not found"); }
      else { res.writeHead(200); res.end(data); }
    });
  });
  server.listen(port, "127.0.0.1");
  return server;
}

async function checkPages(slugs, siteDir, baseUrl, capturesOut) {
  const { chromium } = require("playwright");
  fs.mkdirSync(capturesOut, { recursive: true });

  const browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const results = [];

  for (const slug of slugs) {
    const htmlPath = path.join(siteDir, `${slug}.html`);
    const result = { slug, file_exists: false, rendered: false, screenshot: null };

    if (!fs.existsSync(htmlPath)) { results.push(result); continue; }

    const stat = fs.statSync(htmlPath);
    if (stat.size < 200) { result.file_exists = true; results.push(result); continue; }

    result.file_exists = true;
    try {
      const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      await page.goto(`${baseUrl}/${slug}.html`, { waitUntil: "networkidle", timeout: 15000 });
      const bodyText = await page.innerText("body");
      if (bodyText.trim().length >= 50) {
        const capturePath = path.join(capturesOut, `${slug}.png`);
        await page.screenshot({ path: capturePath, fullPage: true });
        result.rendered = true;
        result.screenshot = capturePath;
      }
      await page.close();
    } catch (e) {
      result.error = e.message;
    }
    results.push(result);
  }

  await browser.close();
  return results;
}

async function main() {
  const args = parseArgs();
  const siteDir = args["agent-site"];
  const gtScreenshots = args["ground-truth-screenshots"];
  const capturesOut = args["captures-out"];
  const rewardOut = args["reward-out"];

  const slugs = getSlugs(gtScreenshots);

  if (slugs.length === 0) {
    fs.mkdirSync(path.dirname(rewardOut), { recursive: true });
    fs.writeFileSync(rewardOut, JSON.stringify({ score: 0.0, checker: "completeness-v1", error: "no ground truth screenshots found" }, null, 2));
    return;
  }

  const port = 9731;
  const server = startServer(siteDir, port);
  await new Promise((r) => setTimeout(r, 200));

  let results;
  try {
    results = await checkPages(slugs, siteDir, `http://127.0.0.1:${port}`, capturesOut);
  } finally {
    server.close();
  }

  const rendered = results.filter((r) => r.rendered).length;
  const score = rendered / slugs.length;

  const reward = { score: Math.round(score * 1e6) / 1e6, checker: "completeness-v1", total_pages: slugs.length, rendered_pages: rendered, results };
  fs.mkdirSync(path.dirname(rewardOut), { recursive: true });
  fs.writeFileSync(rewardOut, JSON.stringify(reward, null, 2));
  fs.writeFileSync(path.join(path.dirname(rewardOut), "reward.txt"), `${score.toFixed(6)}\n`);

  console.log(`Checker done: ${rendered}/${slugs.length} pages rendered. Score: ${score.toFixed(4)}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
