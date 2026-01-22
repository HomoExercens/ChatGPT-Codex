import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const SCREENSHOTS_DIR = path.resolve(__dirname, '../../../docs/screenshots');

test.describe.configure({ mode: 'serial' });

async function ensureScreenshotsDir(): Promise<void> {
  await fs.promises.mkdir(SCREENSHOTS_DIR, { recursive: true });
}

test('first win in 45s (share → guest → replay → ranked)', async ({ page }) => {
  await ensureScreenshotsDir();

  await page.goto('/');
  await page.evaluate(() => {
    try {
      localStorage.clear();
      localStorage.setItem(
        'neuroleague.settings',
        JSON.stringify({ language: 'en', fontScale: 1, contrast: 1, reduceMotion: true, colorblind: false })
      );
    } catch {
      // ignore
    }
  });

  // Start from a public share landing.
  await page.goto('/s/clip/r_seed_001?start=0.0&end=2.0&v=1');
  await expect(page.locator('meta[property="og:title"]')).toHaveCount(1);

  const openInApp = page.getByRole('link', { name: 'Open in App' });
  await expect(openInApp).toBeVisible({ timeout: 30_000 });
  await openInApp.click();

  // /start auto-creates a guest and lands on the replay.
  await page.waitForURL('**/replay/**', { timeout: 60_000 });
  await expect(page.evaluate(() => localStorage.getItem('neuroleague.token'))).resolves.toBeTruthy();
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'e2e_01_replay_from_share.png'), fullPage: true });

  // One-tap starter build -> ranked queue.
  const queueStarter = page.getByRole('button', { name: /Queue with Mech Counter/i });
  await expect(queueStarter).toBeVisible({ timeout: 60_000 });
  await queueStarter.click();

  await page.waitForURL('**/ranked**', { timeout: 60_000 });
  await page.waitForURL('**/replay/**', { timeout: 180_000 });
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'e2e_02_ranked_done.png'), fullPage: true });
});
