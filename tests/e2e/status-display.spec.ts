import { test, expect } from '@playwright/test';

const API_URL = 'https://quote-management-4.preview.emergentagent.com';

// Test credentials
const ADMIN_EMAIL = 'admin@pdpv.pt';
const ADMIN_PASSWORD = 'HCNMEnKMLq';

// Test ticket IDs (provided by main agent)
const ACEITE_LINK_TICKET_ID = '45f94275-0164-40db-b3cc-6c658bf0cd70';
const EM_TRATAMENTO_TICKET_ID = '222daadb-f066-4098-b759-cd78d5a81073';

test.describe('Bug Fix: Status Display Tests', () => {
  
  test.beforeEach(async ({ page }) => {
    // Remove Emergent preview badge
    await page.addLocatorHandler(
      page.locator('[class*="emergent"], [id*="emergent-badge"]'),
      async () => {
        await page.evaluate(() => {
          const badge = document.querySelector('[class*="emergent"], [id*="emergent-badge"]');
          if (badge) badge.remove();
        });
      },
      { times: 5, noWaitAfter: true }
    );
  });

  test('Login as admin and navigate to dashboard', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    
    // Wait for login form
    await expect(page.locator('input[type="email"]').first()).toBeVisible({ timeout: 10000 });
    
    // Fill login form
    await page.locator('input[type="email"]').first().fill(ADMIN_EMAIL);
    await page.locator('input[type="password"]').first().fill(ADMIN_PASSWORD);
    
    // Click login button
    await page.locator('button[type="submit"]').first().click();
    
    // Wait for redirect to dashboard or tickets
    await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
    
    // Verify we're logged in - should see navigation
    await expect(page.locator('nav, [role="navigation"]').first()).toBeVisible();
  });

  test('Bug 1: ACEITE_LINK status displays correctly as a badge', async ({ page }) => {
    // Login first
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.locator('input[type="email"]').first().fill(ADMIN_EMAIL);
    await page.locator('input[type="password"]').first().fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
    
    // Navigate to ticket with ACEITE_LINK status
    await page.goto(`/tickets/${ACEITE_LINK_TICKET_ID}`, { waitUntil: 'domcontentloaded' });
    
    // Wait for ticket detail to load
    await expect(page.getByTestId('back-to-tickets-btn')).toBeVisible({ timeout: 15000 });
    
    // Bug fix verification: ACEITE_LINK should be displayed as a Badge, not a broken Select dropdown
    // Look for the status badge with auto status indicator
    const statusBadge = page.getByTestId('status-badge-auto');
    
    // Verify the badge is visible (not a dropdown/select)
    await expect(statusBadge).toBeVisible({ timeout: 10000 });
    
    // Verify the badge shows the correct label
    await expect(statusBadge).toContainText(/Aceite/i);
    
    // Take screenshot for visual verification
    await page.screenshot({ path: 'aceite-link-status.jpeg', quality: 20, fullPage: false });
  });

  test('Bug 1: Status badge shows correct label and has color styling', async ({ page }) => {
    // Login
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.locator('input[type="email"]').first().fill(ADMIN_EMAIL);
    await page.locator('input[type="password"]').first().fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
    
    // Navigate to ACEITE_LINK ticket
    await page.goto(`/tickets/${ACEITE_LINK_TICKET_ID}`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('back-to-tickets-btn')).toBeVisible({ timeout: 15000 });
    
    const statusBadge = page.getByTestId('status-badge-auto');
    await expect(statusBadge).toBeVisible();
    
    // Verify badge has some styling (background color should be set via inline style)
    // The component uses inline styles: backgroundColor, color, borderColor
    const styles = await statusBadge.evaluate(el => {
      const style = window.getComputedStyle(el);
      return {
        backgroundColor: style.backgroundColor,
        color: style.color
      };
    });
    
    // Badge should have some color styling applied (not transparent or default)
    expect(styles.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
    expect(styles.color).not.toBe('');
  });

  test('Manual status dropdown works for non-automatic statuses', async ({ page }) => {
    // Login
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.locator('input[type="email"]').first().fill(ADMIN_EMAIL);
    await page.locator('input[type="password"]').first().fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
    
    // Navigate to EM_TRATAMENTO ticket (not automatic, should have dropdown)
    await page.goto(`/tickets/${EM_TRATAMENTO_TICKET_ID}`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('back-to-tickets-btn')).toBeVisible({ timeout: 15000 });
    
    // For non-automatic statuses, should see a select dropdown
    const statusSelect = page.getByTestId('status-select');
    await expect(statusSelect).toBeVisible({ timeout: 10000 });
    
    // Click to open dropdown
    await statusSelect.click();
    
    // Should see status options
    await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 5000 });
    
    // Close dropdown by pressing Escape
    await page.keyboard.press('Escape');
    
    await page.screenshot({ path: 'manual-status-dropdown.jpeg', quality: 20, fullPage: false });
  });
});
