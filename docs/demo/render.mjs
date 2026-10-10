// Renders docs/demo/demo.html to demo.mp4 and demo.gif.
// Needs Node with Playwright (Chromium) and ffmpeg on PATH.
//   node docs/demo/render.mjs
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const FPS = 30;
const frames = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'jev-demo-'));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(join(here, 'demo.html')).href + '?capture');
await page.evaluate(() => document.fonts.ready);
const duration = await page.evaluate(() => window.DURATION);
const canvas = page.locator('canvas');
const n = Math.round(duration * FPS);
for (let i = 0; i < n; i++) {
  await page.evaluate(t => window.drawFrame(t), i / FPS);
  await canvas.screenshot({ path: join(frames, `f${String(i).padStart(4, '0')}.png`) });
  if (i % 60 === 0) console.log(`frame ${i}/${n}`);
}
await browser.close();

const ff = args => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...args], { stdio: 'inherit' });
const input = ['-framerate', String(FPS), '-i', join(frames, 'f%04d.png')];
ff([...input, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'slow', '-movflags', '+faststart', join(here, 'demo.mp4')]);
ff([...input, '-vf',
  'fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle',
  join(here, 'demo.gif')]);
copyFileSync(join(frames, `f${String(Math.round(7.6 * FPS)).padStart(4, '0')}.png`), join(here, 'poster.png'));
rmSync(frames, { recursive: true, force: true });
console.log('wrote demo.mp4, demo.gif, poster.png');
