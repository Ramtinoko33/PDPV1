import { Page, expect } from '@playwright/test';

export async function waitForAppReady(page: Page) {
  await page.waitForLoadState('domcontentloaded');
}

export async function dismissToasts(page: Page) {
  await page.addLocatorHandler(
    page.locator('[data-sonner-toast], .Toastify__toast, [role="status"].toast, .MuiSnackbar-root'),
    async () => {
      const close = page.locator('[data-sonner-toast] [data-close], [data-sonner-toast] button[aria-label="Close"], .Toastify__close-button, .MuiSnackbar-root button');
      await close.first().click({ timeout: 2000 }).catch(() => {});
    },
    { times: 10, noWaitAfter: true }
  );
}

export async function checkForErrors(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const errorElements = Array.from(
      document.querySelectorAll('.error, [class*="error"], [id*="error"]')
    );
    return errorElements.map(el => el.textContent || '').filter(Boolean);
  });
}

export async function login(page: Page, email: string, password: string) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="email-input"], input[type="email"]', { timeout: 10000 });
  
  // Fill email
  const emailInput = page.locator('[data-testid="email-input"], input[type="email"]').first();
  await emailInput.fill(email);
  
  // Fill password
  const passwordInput = page.locator('[data-testid="password-input"], input[type="password"]').first();
  await passwordInput.fill(password);
  
  // Click login button
  const loginButton = page.locator('[data-testid="login-btn"], button[type="submit"]').first();
  await loginButton.click();
  
  // Wait for redirect to dashboard
  await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
}

export async function navigateToTicketDetail(page: Page, ticketId: string) {
  await page.goto(`/tickets/${ticketId}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('[data-testid="back-to-tickets-btn"]', { timeout: 15000 });
}
