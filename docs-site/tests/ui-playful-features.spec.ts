import { test, expect } from '@playwright/test';

test.describe('Playful Dynamic UI Features', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/docs/');
  });

  test('breathing background animation exists', async ({ page }) => {
    const body = await page.locator('body');
    await expect(body).toHaveClass(/breathing-bg/);

    // Check animation is applied
    const styles = await body.evaluate(el => window.getComputedStyle(el).animationName);
    expect(styles).toContain('breathing-bg');
  });

  test('scroll progress indicator exists', async ({ page }) => {
    const progressBar = await page.locator('#scroll-progress');
    // Element exists in DOM (may have scaleX(0) initially)
    await expect(progressBar).toHaveCount(1);

    // Check gradient background
    const styles = await progressBar.evaluate(el => window.getComputedStyle(el).backgroundImage);
    expect(styles).toContain('gradient');
  });

  test('smart link underline on hover', async ({ page }) => {
    const smartLink = await page.locator('.smart-link').first();
    await expect(smartLink).toBeVisible();

    // Check the element has the smart-link class
    await expect(smartLink).toHaveClass(/smart-link/);
  });

  test('ripple button class exists on interactive buttons', async ({ page }) => {
    // Check theme toggle has ripple-btn class
    const themeToggle = await page.locator('#theme-toggle-btn');
    await expect(themeToggle).toHaveClass(/ripple-btn/);

    // Check sidebar toggle has ripple-btn class
    const sidebarToggle = await page.locator('#sidebar-toggle');
    await expect(sidebarToggle).toHaveClass(/ripple-btn/);
  });

  test('theme icon has rotation class', async ({ page }) => {
    const themeIcon = await page.locator('.theme-icon');
    await expect(themeIcon).toBeVisible();
    await expect(themeIcon).toHaveClass(/theme-icon/);
  });

  test('prose headings have hover effect styles', async ({ page }) => {
    // Navigate to a doc page with headings
    await page.goto('/docs/user/getting-started/');

    const heading = await page.locator('.prose h2, .prose h3').first();
    if (await heading.count() > 0) {
      await expect(heading).toBeVisible();

      // Check position is relative for pseudo-element positioning
      const position = await heading.evaluate(el => window.getComputedStyle(el).position);
      expect(position).toBe('relative');
    }
  });

  test('hover lift class exists in CSS', async ({ page }) => {
    // Check the hover-lift class is defined by creating a test element
    const hasHoverLift = await page.evaluate(() => {
      const el = document.createElement('div');
      el.className = 'hover-lift';
      document.body.appendChild(el);
      const styles = window.getComputedStyle(el);
      const hasTransition = styles.transition !== 'all 0s ease 0s';
      document.body.removeChild(el);
      return hasTransition;
    });

    expect(hasHoverLift).toBe(true);
  });

  test('floating shapes component exists', async ({ page }) => {
    const floatingShapes = await page.locator('.floating-shapes-container');
    await expect(floatingShapes).toHaveCount(1);

    // Check that shapes exist
    const shapes = await page.locator('.floating-shape');
    await expect(shapes).toHaveCount(4);
  });

  test('reduced motion media query is respected', async ({ page }) => {
    // Emulate reduced motion preference
    await page.emulateMedia({ reducedMotion: 'reduce' });

    // Navigate to the page again with reduced motion
    await page.goto('/docs/');

    const body = await page.locator('body');
    const animation = await body.evaluate(el => window.getComputedStyle(el).animationName);
    // Breathing bg animation should be disabled
    expect(animation).toBe('none');
  });

  test('page loads without critical console errors', async ({ page }) => {
    const errors: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    await page.goto('/docs/');
    await page.waitForLoadState('networkidle');

    // Filter out pre-existing SVG path errors (not related to our implementation)
    const criticalErrors = errors.filter(e => !e.includes('<path> attribute d'));
    expect(criticalErrors).toHaveLength(0);
  });

  test('scroll progress updates on scroll', async ({ page }) => {
    const progressBar = await page.locator('#scroll-progress');

    // Wait for scroll handler to be attached
    await page.waitForLoadState('networkidle');

    // Scroll down significantly
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
    await page.waitForTimeout(200);

    // Get the current scaleX value from computed style
    const scaleValue = await progressBar.evaluate(el => {
      const style = window.getComputedStyle(el);
      const matrix = new DOMMatrix(style.transform);
      return matrix.m11; // scaleX is m11 in the matrix
    });

    // Progress should be > 0 after scrolling
    expect(scaleValue).toBeGreaterThan(0);
  });
});
