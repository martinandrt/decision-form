#!/usr/bin/env node
/*
 * End-to-end check and demo recording: serves examples/repo-cleanup.html, fills it like a person on a phone,
 * sends it, checks the answers file, and writes frames + screenshots for docs/.
 *
 *   PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core node dev/record-demo.js
 *   (CHROME=/path/to/chrome to override the browser; default is Google Chrome on macOS)
 *
 * Output in $DEMO_OUT (default: <tmp>/decision-form-demo): frames/*.png, frames.txt (ffmpeg concat list),
 * shot-*.png, server.txt, answers.json.
 * Needs to bind 127.0.0.1 (the local server). The browser runs with a fresh temporary profile.
 */
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const ROOT = path.resolve(__dirname, '..');
const OUT = process.env.DEMO_OUT || path.join(require('os').tmpdir(), 'decision-form-demo');
const FRAMES = path.join(OUT, 'frames');
const PAGE = path.join(ROOT, 'examples', 'repo-cleanup.html');
const ANSWERS = path.join(OUT, 'answers.json');

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(FRAMES, { recursive: true });

function startServer() {
  return new Promise((resolve, reject) => {
    const p = spawn('python3', ['-u', path.join(ROOT, 'skills/decision-form/scripts/serve_form.py'), PAGE,
      '--out', ANSWERS, '--timeout', '3'], { stdio: ['ignore', 'pipe', 'inherit'] });
    let out = '';
    p.stdout.on('data', d => {
      out += d;
      const m = out.match(/Open: (\S+)/);
      if (m && !p.url) { p.url = m[1]; resolve(p); }
    });
    p.output = () => out;
    p.on('exit', code => { p.code = code; if (!p.url) reject(new Error('server exited ' + code + '\n' + out)); });
  });
}

const TAP_CSS = `.tap{position:fixed;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;
  background:rgba(29,110,119,.35);border:2px solid rgba(29,110,119,.8);pointer-events:none;z-index:99;
  transition:transform .35s ease-out,opacity .35s ease-out}`;

(async () => {
  const server = await startServer();
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
    isMobile: true, hasTouch: true, colorScheme: 'light' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(server.url);
  await page.addStyleTag({ content: TAP_CSS });

  const list = [];
  let n = 0;
  async function shot(ms) {
    const f = path.join(FRAMES, String(n++).padStart(3, '0') + '.png');
    await page.screenshot({ path: f });
    list.push(`file '${f}'\nduration ${(ms / 1000).toFixed(3)}`);
  }
  async function scrollTo(selector, offset = 90) {
    const target = await page.$eval(selector, (el, o) => el.getBoundingClientRect().top + scrollY - o, offset);
    const start = await page.evaluate(() => scrollY);
    const steps = 9;
    for (let i = 1; i <= steps; i++) {
      const t = i / steps, e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      await page.evaluate(y => window.scrollTo(0, y), start + (target - start) * e);
      await shot(45);
    }
  }
  async function tap(selector, hold = 650) {
    const el = page.locator(selector);
    await el.scrollIntoViewIfNeeded();
    // Keep the target above the fixed bottom bar, or the tap lands on the Send button.
    const barTop = await page.$eval('.bar', b => b.getBoundingClientRect().top);
    let b = await el.boundingBox();
    if (selector !== '#send' && b.y + b.height > barTop - 12) {
      await page.evaluate(d => window.scrollBy(0, d), b.y + b.height - barTop + 40);
      b = await el.boundingBox();
    }
    const x = b.x + Math.min(40, b.width / 2), y = b.y + b.height / 2;
    await page.evaluate(([x, y]) => {
      const d = document.createElement('div'); d.className = 'tap'; d.style.left = x + 'px'; d.style.top = y + 'px';
      document.body.appendChild(d); setTimeout(() => { d.style.transform = 'scale(1.6)'; d.style.opacity = '0'; }, 30);
      setTimeout(() => d.remove(), 450);
    }, [x, y]);
    await page.touchscreen.tap(x, y);
    const radio = selector.match(/^#(q\d+[a-z])/);
    if (radio && !(await page.isChecked('#' + radio[1]))) throw new Error('tap missed ' + selector);
    await shot(120);
    await page.waitForTimeout(450);
    await shot(hold);
  }
  async function type(selector, text) {
    for (let i = 1; i <= text.length; i++) {
      await page.fill(selector, text.slice(0, i));
      if (i % 3 === 0 || i === text.length) await shot(70);
    }
    await page.dispatchEvent(selector, 'input');
  }

  await shot(1800);                                   // title and first card
  await tap('#q1a >> xpath=..');    // 1a recommended
  await tap('#questions section:nth-of-type(2) summary', 1700);  // Explain
  await tap('#q2a >> xpath=..');
  await scrollTo('#questions section:nth-of-type(3)');
  await tap('#q3b >> xpath=..');
  await scrollTo('#questions section:nth-of-type(4)');
  await tap('#q4a >> xpath=..');
  await tap('#q5a >> xpath=..');
  await scrollTo('#questions section:nth-of-type(6)');
  await tap('#q6x >> xpath=..', 300);
  await type('#t6', 'Ask the QA team first');
  await shot(500);
  await scrollTo('#questions section:nth-of-type(7)');
  await tap('#q7a >> xpath=..', 900);
  await tap('#send', 300);
  await page.waitForFunction(() => document.getElementById('status').textContent.startsWith('Sent'));
  await shot(2600);

  // Server must have written the answers and exited 0.
  await new Promise(r => { if (server.code !== undefined) r(); else server.on('exit', r); });
  const saved = JSON.parse(fs.readFileSync(ANSWERS, 'utf8'));
  const expected = { 1: 'a', 2: 'a', 3: 'b', 4: 'a', 5: 'a', 6: 'x', 7: 'a' };
  const okAnswers = JSON.stringify(saved.answers) === JSON.stringify(expected) && saved.notes['6'] === 'Ask the QA team first';
  fs.writeFileSync(path.join(OUT, 'server.txt'), server.output());
  fs.writeFileSync(path.join(OUT, 'frames.txt'), list.join('\n') + `\nfile '${path.join(FRAMES, String(n - 1).padStart(3, '0') + '.png')}'\n`);

  // Static screenshots: phone light/dark (top of page) and desktop light.
  for (const [name, opts] of [['phone-light', { colorScheme: 'light' }], ['phone-dark', { colorScheme: 'dark' }]]) {
    const c = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, ...opts });
    const p = await c.newPage(); await p.goto('file://' + PAGE);
    await p.click('#questions section:nth-of-type(2) summary');
    await p.screenshot({ path: path.join(OUT, `shot-${name}.png`) }); await c.close();
  }
  const d = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'light' });
  const dp = await d.newPage(); await dp.goto('file://' + PAGE);
  await dp.screenshot({ path: path.join(OUT, 'shot-desktop.png') }); await d.close();
  const copyCtx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const cp = await copyCtx.newPage(); await cp.goto('file://' + PAGE);
  const copyLabel = await cp.textContent('#send'); await copyCtx.close();

  await browser.close();
  console.log(JSON.stringify({ frames: n, serverExit: server.code, answersOk: okAnswers, saved: saved.code,
    fileModeButton: copyLabel, errors }, null, 1));
  process.exit(okAnswers && server.code === 0 && !errors.length && copyLabel === 'Copy answers' ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
