import { expect, test } from '@playwright/test';

test('ops hero candidates page renders (admin token)', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  await page.addInitScript(() => {
    try {
      localStorage.clear();
      localStorage.setItem('neuroleague.admin_token', 'admintest');
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

  await page.goto('/ops/hero');
  await expect(page.getByText('Hero Auto-curator v2')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('button', { name: /Recompute now/i })).toBeVisible({ timeout: 60_000 });

  expect(consoleErrors).toEqual([]);
});

