import { expect, test } from '@playwright/test';

test('play feed loads and shows Beat This CTA', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  await page.goto('/');
  await page.evaluate(() => {
    try {
      localStorage.clear();
      localStorage.setItem(
        'neuroleague.settings',
        JSON.stringify({
          language: 'en',
          fontScale: 1,
          contrast: 1,
          reduceMotion: true,
          colorblind: false,
          soundEnabled: false,
          hapticsEnabled: false,
        }),
      );
    } catch {
      // ignore
    }
  });

  await page.goto('/play');
  const heroCount = await page.getByTestId('hero-badge').count();
  if (heroCount > 0) {
    await expect(page.getByTestId('hero-badge').first()).toBeVisible({ timeout: 60_000 });
  }
  await expect(page.getByTestId('today-quest-card').first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('button', { name: /Beat This/i }).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('clip-hud-outcome').first()).toBeVisible({ timeout: 60_000 });
  expect(consoleErrors).toEqual([]);
});

test('forge Auto Tune creates a new build and queues a match', async ({ page }) => {
  await page.addInitScript(() => {
    try {
      localStorage.clear();
      sessionStorage.clear();
      localStorage.setItem(
        'neuroleague.settings',
        JSON.stringify({
          language: 'en',
          fontScale: 1,
          contrast: 1,
          reduceMotion: true,
          colorblind: false,
          soundEnabled: false,
          hapticsEnabled: false,
        }),
      );
    } catch {
      // ignore
    }
  });

  await page.goto('/forge');

  const create = page.getByRole('button', { name: '+ New' });
  await expect(create).toBeVisible({ timeout: 60_000 });
  await create.click();

  const autoTune = page.getByRole('button', { name: 'Auto Tune' });
  await expect(autoTune).toBeVisible({ timeout: 60_000 });
  await expect(autoTune).toBeEnabled({ timeout: 60_000 });
  await autoTune.click();

  const dps = page.getByRole('button', { name: 'DPS' });
  await expect(dps).toBeVisible({ timeout: 60_000 });
  await dps.click();

  await expect(page.getByRole('button', { name: 'Open tuned build' })).toBeVisible({ timeout: 60_000 });

  const queue = page.getByRole('button', { name: 'Queue match' });
  await expect(queue).toBeVisible({ timeout: 60_000 });
  await queue.click();

  await page.waitForURL('**/ranked**', { timeout: 60_000 });
  await page.waitForURL('**/replay/**', { timeout: 180_000 });
});
