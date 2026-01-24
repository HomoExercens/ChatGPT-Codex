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
  await expect(page.getByRole('button', { name: 'Share Reply Clip' }).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('link', { name: 'View Original' }).first()).toBeVisible({ timeout: 60_000 });
  const outcome = page.getByTestId('reply-result-outcome').first();
  await expect(outcome).toBeVisible({ timeout: 60_000 });
  const outcomeText = ((await outcome.textContent()) || '').trim();
  if (outcomeText === 'LOSE') {
    await expect(page.getByRole('button', { name: /Auto Tune/i }).first()).toBeVisible({ timeout: 60_000 });
  }

  // v3: reactions on reply clip.
  const upReaction = page.getByRole('button', { name: /👍/ }).first();
  await expect(upReaction).toBeVisible({ timeout: 60_000 });
  await upReaction.click();

  // Reply-chain should show on the original share landing.
  await page.goto('/s/clip/r_seed_001?start=0.0&end=2.0&v=1');
  await expect(page.getByRole('heading', { name: 'Replies' })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('a.reply-card').first()).toBeVisible({ timeout: 60_000 });

  // v3: notifications badge for the original clip owner (login as demo).
  const login = await page.request.post('/api/auth/login', { data: { username: 'demo' } });
  expect(login.ok()).toBeTruthy();
  const loginJson = await login.json();
  expect(loginJson.access_token).toBeTruthy();
  await page.evaluate((tok) => {
    localStorage.setItem('neuroleague.token', String(tok));
  }, loginJson.access_token);

  await page.goto('/inbox');
  await expect(page.getByRole('heading', { name: /Inbox/i }).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('div.divide-y').locator('button').first()).toBeVisible({ timeout: 60_000 });
});
