import { expect, test } from '@playwright/test';

test('share landing Beat This → Replay shows Reply share CTA, and Replies appear on original clip', async ({ page }) => {
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

  await page.goto('/s/clip/r_seed_001?start=0.0&end=2.0&v=1');
  await expect(page.locator('meta[property="og:title"]')).toHaveCount(1);

  const beatLink = page.getByRole('link', { name: 'Beat This' }).first();
  await expect(beatLink).toBeVisible({ timeout: 30_000 });
  await beatLink.click();

  await page.waitForURL('**/replay/**', { timeout: 180_000 });
  await expect(page.getByRole('button', { name: 'Share Reply Clip' })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('link', { name: 'View Original' })).toBeVisible({ timeout: 60_000 });

  // Reply-chain should show on the original share landing.
  await page.goto('/s/clip/r_seed_001?start=0.0&end=2.0&v=1');
  await expect(page.getByText('Replies')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('a.reply-card').first()).toBeVisible({ timeout: 60_000 });
});

