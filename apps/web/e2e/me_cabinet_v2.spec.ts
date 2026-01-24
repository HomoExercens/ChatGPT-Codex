import { expect, test } from '@playwright/test';

test('me page renders badge cabinet', async ({ page }) => {
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

  await page.goto('/me');
  await expect(page.getByRole('heading', { name: /Badge Cabinet/i }).first()).toBeVisible({ timeout: 60_000 });
});

