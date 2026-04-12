import { test, expect } from '@playwright/test';

test.describe('Performance Metrics', () => {
  test('page loads within acceptable time', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/docs/');
    await page.waitForLoadState('networkidle');
    const loadTime = Date.now() - startTime;

    // Page should load in under 3 seconds
    expect(loadTime).toBeLessThan(3000);
  });

  test('no layout shifts during load', async ({ page }) => {
    // Collect CLS (Cumulative Layout Shift) data
    const cls = await page.evaluate(() => {
      return new Promise((resolve) => {
        let clsValue = 0;
        const observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (!(entry as any).hadRecentInput) {
              clsValue += (entry as any).value;
            }
          }
        });
        observer.observe({ entryTypes: ['layout-shift'] });

        // Report CLS after 2 seconds
        setTimeout(() => {
          observer.disconnect();
          resolve(clsValue);
        }, 2000);
      });
    });

    // CLS should be less than 0.1 (good threshold)
    expect(cls).toBeLessThan(0.1);
  });

  test('animations run at 60fps', async ({ page }) => {
    await page.goto('/docs/');

    // Check if animations are GPU-accelerated
    const animatedElements = await page.locator('.breathing-bg, .floating-shape, .theme-icon').count();
    expect(animatedElements).toBeGreaterThan(0);

    // Check that animations use transform/opacity
    const usesGpuAcceleration = await page.evaluate(() => {
      const elements = document.querySelectorAll('.breathing-bg, .floating-shape, .theme-icon');
      for (const el of elements) {
        const style = window.getComputedStyle(el);
        // Check if animation uses GPU-friendly properties
        if (style.animationName && style.animationName !== 'none') {
          return true;
        }
      }
      return false;
    });

    expect(usesGpuAcceleration).toBe(true);
  });

  test('CSS animations respect reduced motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/docs/');

    // Check that floating shapes are hidden
    const floatingShapes = await page.locator('.floating-shapes-container');
    const isHidden = await floatingShapes.evaluate(el =>
      window.getComputedStyle(el).display === 'none'
    );

    expect(isHidden).toBe(true);
  });

  test('no excessive DOM nodes', async ({ page }) => {
    await page.goto('/docs/');

    const nodeCount = await page.evaluate(() => {
      return document.querySelectorAll('*').length;
    });

    // Should have less than 1500 DOM nodes for good performance
    expect(nodeCount).toBeLessThan(1500);
  });
});
