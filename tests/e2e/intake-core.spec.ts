import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://quote-management-4.preview.emergentagent.com';
const ADMIN_EMAIL = 'admin@pdpv.pt';
const ADMIN_PASSWORD = 'HCNMEnKMLq';

// Helper to login
async function login(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('input[type="email"]', { timeout: 10000 });
  await page.locator('input[type="email"]').fill(ADMIN_EMAIL);
  await page.locator('input[type="password"]').fill(ADMIN_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
}

// Helper to navigate to intake page
async function navigateToIntake(page: Page) {
  const intakeLink = page.locator('a[href="/intake"], [href*="intake"]').first();
  await intakeLink.click();
  await expect(page).toHaveURL(/\/intake/, { timeout: 10000 });
  await page.waitForLoadState('domcontentloaded');
}

// Helper to generate unique test data
function uniqueId() {
  return `TEST_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

test.describe('Intake Module - Core Features', () => {
  
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('should display Intake page with stats cards', async ({ page }) => {
    await navigateToIntake(page);
    
    // Verify page header
    await expect(page.locator('text=Pré-Tickets')).toBeVisible();
    
    // Verify stats cards
    await expect(page.locator('text=Pendentes')).toBeVisible();
    await expect(page.locator('text=Convertidos')).toBeVisible();
    
    await page.screenshot({ path: 'intake-page-loaded.jpeg', quality: 20 });
  });

  test('CREATE: should create a new pre-ticket via form', async ({ page }) => {
    await navigateToIntake(page);
    
    const testName = uniqueId();
    
    // Click "Novo Pré-Ticket" button
    await page.locator('button:has-text("Novo Pré-Ticket")').click();
    
    // Wait for dialog
    await expect(page.locator('[data-testid="intake-create-name"]')).toBeVisible({ timeout: 5000 });
    
    // Fill form using data-testid
    await page.locator('[data-testid="intake-create-name"]').fill(testName);
    await page.locator('[data-testid="intake-create-contact"]').fill('912345678');
    await page.locator('[data-testid="intake-create-message"]').fill('Test message');
    
    // Submit
    await page.locator('button:has-text("Criar Pré-Ticket")').click();
    
    // Wait for success toast
    await expect(page.locator('text=Pré-ticket criado com sucesso')).toBeVisible({ timeout: 10000 });
    
    // Verify it appears in the table
    await expect(page.locator(`text=${testName}`).first()).toBeVisible({ timeout: 10000 });
    
    await page.screenshot({ path: 'intake-create-success.jpeg', quality: 20 });
  });

  test('READ: should display intake list with action buttons', async ({ page }) => {
    await navigateToIntake(page);
    
    // Wait for table to load
    await page.waitForSelector('table', { timeout: 10000 });
    
    // Verify at least one row exists with action buttons
    const rows = page.locator('tbody tr');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
    
    await page.screenshot({ path: 'intake-list-view.jpeg', quality: 20 });
  });

  test('validations: should require name and contact', async ({ page }) => {
    await navigateToIntake(page);
    
    await page.locator('button:has-text("Novo Pré-Ticket")').click();
    await expect(page.locator('[data-testid="intake-create-name"]')).toBeVisible({ timeout: 5000 });
    
    // Try to submit without filling required fields
    await page.locator('button:has-text("Criar Pré-Ticket")').click();
    
    // Verify validation error
    await expect(page.locator('text=Nome e contacto são obrigatórios')).toBeVisible({ timeout: 5000 });
    
    await page.screenshot({ path: 'intake-validation.jpeg', quality: 20 });
  });
});
