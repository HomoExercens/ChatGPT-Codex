import { expect, test } from '@playwright/test';

test('playtest page → demo clip → Quick Remix → Replay → Replies visible', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => {
    try {
      localStorage.clear();
      sessionStorage.clear();
      localStorage.setItem(
        'neuroleague.settings',
        JSON.stringify({ language: 'en', fontScale: 1, contrast: 1, reduceMotion: true, colorblind: false })
      );
    } catch {
      // ignore
    }
  });

  await page.goto('/playtest');
  await expect(page.getByText('NeuroLeague Playtest')).toBeVisible({ timeout: 30_000 });
  const start = page.getByRole('link', { name: 'Start Playtest' }).first();
  await expect(start).toBeVisible({ timeout: 30_000 });
  await start.click();

  // Server-rendered share landing should include OG meta.
  await page.waitForURL('**/s/clip/**', { timeout: 30_000 });
  await expect(page.locator('meta[property="og:title"]')).toHaveCount(1);

  // Prefer Quick Remix path (one-click preset).
  const quick = page.getByRole('link', { name: 'Quick Remix: Tankier' }).first();
  await expect(quick).toBeVisible({ timeout: 30_000 });
  await quick.click();

  await page.waitForURL('**/replay/**', { timeout: 180_000 });
  await expect(page.getByRole('button', { name: 'Share Reply Clip' }).first()).toBeVisible({ timeout: 60_000 });

  // v3: reactions on reply clip.
  const upReaction = page.getByRole('button', { name: /👍/ }).first();
  await expect(upReaction).toBeVisible({ timeout: 60_000 });
  await upReaction.click();

  // Reply-chain should show on the original share landing.
  await page.goto('/s/clip/r_seed_001?start=0.0&end=2.0&v=1');
  await expect(page.getByRole('heading', { name: 'Replies' })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('a.reply-card').first()).toBeVisible({ timeout: 60_000 });
});
