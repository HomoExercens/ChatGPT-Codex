import { expect, test } from '@playwright/test';

test('play swipe pager + double-tap reaction (reduced motion)', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  const tracked: string[] = [];
  await page.route('**/api/events/track', async (route) => {
    const req = route.request();
    if (req.method() === 'POST') {
      try {
        const body = JSON.parse(req.postData() || '{}');
        if (body?.type) tracked.push(String(body.type));
      } catch {
        // ignore
      }
    }
    await route.continue();
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

  // Pressed feedback shows immediately on pointer down (even though single-tap action is delayed).
  const press = page.getByTestId('press-feedback');
  await expect(press).toBeVisible();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.45);
  await page.mouse.down();
  expect(await press.getAttribute('data-active')).toBe('1');
  await page.mouse.up();

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

  // Gesture attempt telemetry should be emitted (best-effort).
  await expect
    .poll(() => tracked.includes('swipe_attempt') && tracked.includes('tap_attempt'), { timeout: 10_000 })
    .toBe(true);

  // In reduced motion, chrome auto-hide is disabled (Beat This stays visible).
  await page.waitForTimeout(7200);
  await expect(page.getByRole('button', { name: /Beat This/i }).first()).toBeVisible();

  expect(consoleErrors).toEqual([]);
});

test('play double-tap does not trigger single-tap chrome toggle (normal motion)', async ({ page }) => {
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
          reduceMotion: false,
          colorblind: false,
          soundEnabled: false,
          hapticsEnabled: false,
        }),
      );
      localStorage.setItem('neuroleague.ftue.play.v1.dismissed', '1');
      localStorage.setItem('neuroleague.play.gesture_hints.v2_1_1.dismissed', '1');
    } catch {
      // ignore
    }
  });

  await page.goto('/play');

  const cta = page.getByRole('button', { name: /Beat This/i }).first();
  await expect(cta).toBeVisible({ timeout: 60_000 });

  const pager = page.getByTestId('gesture-pager');
  const box = await pager.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;

  // Double-tap within the arbitration window should NOT hide chrome (single-tap toggle is canceled).
  await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.35);
  await page.waitForTimeout(60);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.35);

  // Wait beyond any configured double-tap window (clamped <= 420ms) and ensure CTA is still visible.
  await page.waitForTimeout(650);
  await expect(cta).toBeVisible();
});
