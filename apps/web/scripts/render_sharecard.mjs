#!/usr/bin/env node
import { chromium } from '@playwright/test';
import process from 'node:process';

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const k = argv[i];
    if (!k.startsWith('--')) continue;
    const v = argv[i + 1];
    if (v && !v.startsWith('--')) {
      out[k.slice(2)] = v;
      i += 1;
    } else {
      out[k.slice(2)] = true;
    }
  }
  return out;
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const outPath = args.out;
  const width = Number(args.width || 1200);
  const height = Number(args.height || 630);

  if (!outPath) {
    throw new Error('Missing --out <path>');
  }
  if (!Number.isFinite(width) || !Number.isFinite(height)) {
    throw new Error('Invalid --width/--height');
  }

  const html = await readStdin();
  if (!html.trim()) throw new Error('Empty HTML input');

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width, height },
      deviceScaleFactor: 1,
    });
    await page.setContent(html, { waitUntil: 'load' });
    await page.waitForTimeout(25);
    await page.screenshot({ path: outPath, type: 'png' });
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(String(err?.stack || err));
  process.exit(1);
});

