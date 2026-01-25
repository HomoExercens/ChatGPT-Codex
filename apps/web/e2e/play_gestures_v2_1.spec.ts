import { expect, test } from '@playwright/test';

test('play swipe pager + double-tap reaction (reduced motion)', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

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

  await page.goto('/play');
  await expect(page.getByRole('button', { name: /Beat This/i }).first()).toBeVisible({ timeout: 60_000 });

  const idEl = page.getByTestId('active-replay-id');
  await expect
    .poll(async () => (await idEl.getAttribute('data-replay-id')) || '', { timeout: 60_000 })
    .not.toBe('');
  const before = (await idEl.getAttribute('data-replay-id')) || '';

  const pager = page.getByTestId('gesture-pager');
  await expect(pager).toBeVisible({ timeout: 60_000 });
  const box = await pager.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;

  // Swipe up to next clip.
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.72);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.22, { steps: 12 });
  await page.mouse.up();

  await expect
    .poll(async () => (await idEl.getAttribute('data-replay-id')) || '', { timeout: 10_000 })
    .not.toBe(before);
  const after = (await idEl.getAttribute('data-replay-id')) || '';
  expect(after).not.toEqual(before);

  // Swipe down to previous clip.
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.9, { steps: 12 });
  await page.mouse.up();

  await expect
    .poll(async () => (await idEl.getAttribute('data-replay-id')) || '', { timeout: 10_000 })
    .toBe(before);
  const back = (await idEl.getAttribute('data-replay-id')) || '';
  expect(back).toEqual(before);

  // Double-tap reaction (uses last reaction type, defaults 👍).
  await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.35);
  await page.waitForTimeout(60);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.35);

  const burst = page.getByTestId('reaction-burst');
  await expect(burst).toBeVisible({ timeout: 2_000 });
  await expect(burst).toHaveAttribute('data-reduced', '1');

  // In reduced motion, chrome auto-hide is disabled (Beat This stays visible).
  await page.waitForTimeout(7200);
  await expect(page.getByRole('button', { name: /Beat This/i }).first()).toBeVisible();

  expect(consoleErrors).toEqual([]);
});
