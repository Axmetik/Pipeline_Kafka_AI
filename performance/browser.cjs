// Run inside the pinned Linux Playwright image, on the API network namespace.
const { chromium } = require('/app/node_modules/playwright');
const fs = require('node:fs');
const out = process.env.PERF_OUTPUT;
const stream = fs.createWriteStream(out + '/browser.jsonl', { flags: 'a' });
const emit = (kind, data) => stream.write(JSON.stringify({ kind, ...data }) + '\n');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ timezoneId: 'Pacific/Honolulu' });
  const page = await context.newPage();
  const seen = new Set();
  await page.exposeFunction('__perfReceive', snapshot => {
    const first = snapshot.ids.filter(id => !seen.has(id));
    first.forEach(id => seen.add(id));
    emit('dom', { ...snapshot, firstIds: first });
  });
  if (process.env.PERF_ENABLED !== '0') {
    await page.addInitScript(() => {
      window.__energyPerformance = snapshot => { void window.__perfReceive(snapshot); };
    });
  }
  page.on('pageerror', error => emit('browser_error', { error: error.message }));
  await page.goto('http://127.0.0.1:8080/?run=' + encodeURIComponent(process.env.MVP_RUN_ID));
  async function clocks() {
    const rows = await page.evaluate(async () => {
      const result = [];
      for (let i = 0; i < 10; i++) {
        const start = performance.timeOrigin + performance.now();
        const response = await fetch('/api/performance-clock', { cache: 'no-store' });
        const server = await response.json();
        const end = performance.timeOrigin + performance.now();
        result.push({ startEpochMs:start,endEpochMs:end,serverEpochNs:server.epoch_ns });
      }
      return result;
    });
    rows.forEach(row => emit('clock', row));
  }
  await clocks();
  fs.writeFileSync(out + '/browser.ready', 'ready');
  let clock = Date.now();
  while (!fs.existsSync(out + '/browser.stop')) {
    await new Promise(resolve => setTimeout(resolve, 200));
    if (Date.now() - clock >= 60000) { await clocks(); clock = Date.now(); }
  }
  await clocks();
  await page.screenshot({ path:out + '/dashboard.png', fullPage:true });
  await browser.close();
  stream.end();
})().catch(error => {
  emit('fatal', { error:String(error) });
  stream.end(); process.exitCode = 1;
});
