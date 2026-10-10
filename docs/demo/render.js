// Renders docs/demo/demo.html to PNG frames, then encodes demo.mp4 and demo.gif with ffmpeg.
// Usage: node docs/demo/render.js   (needs playwright + ffmpeg)
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');

const FPS = 30;
(async () => {
  const here = __dirname;
  const frames = fs.mkdtempSync(path.join(os.tmpdir(), 'jev-demo-'));
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto('file://' + path.join(here, 'demo.html') + '?capture=1');
  const duration = await page.evaluate(() => window.DURATION);
  const n = Math.round(duration * FPS);
  for (let i = 0; i < n; i++) {
    const url = await page.evaluate(t => { render(t); return document.getElementById('c').toDataURL('image/png'); }, i / FPS);
    fs.writeFileSync(path.join(frames, `f${String(i).padStart(4, '0')}.png`), Buffer.from(url.split(',')[1], 'base64'));
  }
  await browser.close();
  const input = path.join(frames, 'f%04d.png');
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', input,
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-movflags', '+faststart', path.join(here, 'demo.mp4')]);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', input, '-vf',
    'fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle',
    path.join(here, 'demo.gif')]);
  fs.rmSync(frames, { recursive: true });
  console.log(`rendered ${n} frames -> demo.mp4, demo.gif`);
})();
