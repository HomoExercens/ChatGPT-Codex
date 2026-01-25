import { expect, test } from '@playwright/test';

test('ops gestures page renders (admin token)', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  const urls: string[] = [];
  await page.route('**/api/ops/metrics/experiments/gesture_thresholds_v1_summary**', async (route) => {
    urls.push(route.request().url());
    await route.continue();
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

  await page.goto('/ops/gestures');
  await expect(page.getByTestId('ops-gestures-page')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('Gesture Tuning')).toBeVisible({ timeout: 60_000 });

  // Segment filter should trigger a refetch with segment param.
  await page.getByRole('button', { name: /Android · Chrome/i }).click();
  await expect
    .poll(() => urls.some((u) => u.includes('segment=android_chrome')), { timeout: 10_000 })
    .toBe(true);

  expect(consoleErrors).toEqual([]);
});
