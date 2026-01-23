import { expect, test } from '@playwright/test';

test('share landing Remix → Forge shows lineage', async ({ page }) => {
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

  const remixLink = page.locator('a[href^="/remix?blueprint_id="]').first();
  await expect(remixLink).toBeVisible({ timeout: 30_000 });
  await remixLink.click();

  await page.waitForURL('**/forge/**', { timeout: 60_000 });
  await expect(page.getByRole('heading', { name: 'Lineage' })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('button', { name: 'View Parent' })).toBeVisible({ timeout: 60_000 });
});
