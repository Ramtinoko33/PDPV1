import { test, expect } from '@playwright/test';

const BASE_URL = 'https://workshop-hub-37.preview.emergentagent.com';

// Test credentials
const ADMIN_EMAIL = 'admin@pdpv.pt';
const ADMIN_PASSWORD = 'HCNMEnKMLq';
const SUPERVISOR_EMAIL = 'supervisor@pdpv.pt';
const SUPERVISOR_PASSWORD = 'f9pSIn6zRP';

// Use a ticket that exists
const TEST_TICKET_NUMBER = 'TK20260225FBCA47';

test.describe('Ticket Detail - Reminders & Reply Link Functionality', () => {
  
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
    
    // Login as admin
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.locator('input[type="email"]').first().fill(ADMIN_EMAIL);
    await page.locator('input[type="password"]').first().fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
  });

  test('Create a new reminder from Conversa tab', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Scroll to Reminders section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Click Criar button to show reminder form
    const createBtn = page.getByRole('button', { name: /Criar/i }).first();
    await expect(createBtn).toBeVisible({ timeout: 5000 });
    await createBtn.click();
    
    // Wait for form to appear
    const descriptionInput = page.locator('input[placeholder*="Ligar ao cliente"]');
    await expect(descriptionInput).toBeVisible({ timeout: 5000 });
    
    // Fill the reminder form with unique test data
    const timestamp = Date.now();
    const reminderDescription = `TEST_Reminder_${timestamp}`;
    await descriptionInput.fill(reminderDescription);
    
    // Set a date/time (tomorrow)
    const dateInput = page.locator('input[type="datetime-local"]').first();
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateValue = tomorrow.toISOString().slice(0, 16);
    await dateInput.fill(dateValue);
    
    // Click "Criar Lembrete" button to submit
    const submitBtn = page.getByRole('button', { name: /Criar Lembrete/i });
    await expect(submitBtn).toBeVisible();
    await submitBtn.click();
    
    // Wait for success toast or the reminder to appear in list
    // The form should close after successful creation
    await expect(descriptionInput).toBeHidden({ timeout: 10000 });
    
    // Verify the reminder was created by checking the list
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect(page.locator(`text=${reminderDescription}`).first()).toBeVisible({ timeout: 5000 });
  });

  test('Reminder Criar button opens creation form', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Scroll to Reminders section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Click Criar button
    const createBtn = page.getByRole('button', { name: /Criar/i }).first();
    await createBtn.click();
    
    // Verify form elements appear
    await expect(page.locator('input[placeholder*="Ligar ao cliente"]')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('input[type="datetime-local"]').first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Criar Lembrete/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Cancelar/i })).toBeVisible();
    
    // Screenshot the form
    await page.screenshot({ path: 'reminder-form.jpeg', quality: 20, fullPage: false });
  });

  test('Reply Link section shows generate button or existing link', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Scroll to Reply Link section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Check for Reply Link section
    await expect(page.locator('text=Link de Resposta').first()).toBeVisible({ timeout: 5000 });
    
    // Either the generate button or the link should be visible
    const generateBtn = page.getByTestId('generate-reply-link-btn');
    const linkUrl = page.getByTestId('reply-link-url');
    
    const hasGenerateBtn = await generateBtn.isVisible().catch(() => false);
    const hasLink = await linkUrl.isVisible().catch(() => false);
    
    // At least one should exist
    expect(hasGenerateBtn || hasLink).toBe(true);
    
    // Screenshot
    await page.screenshot({ path: 'reply-link-section.jpeg', quality: 20, fullPage: false });
  });

  test('Reply Link copy button works when link exists', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Scroll to Reply Link section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // If link already exists, test the copy button
    const copyBtn = page.getByTestId('copy-reply-link-btn');
    const hasLink = await copyBtn.isVisible().catch(() => false);
    
    if (hasLink) {
      // Click copy button
      await copyBtn.click();
      
      // Should show a success toast (sonner toast library)
      await expect(page.locator('[data-sonner-toast]').first()).toBeVisible({ timeout: 5000 });
    } else {
      // If no link, the generate button should be visible
      await expect(page.getByTestId('generate-reply-link-btn')).toBeVisible();
    }
  });
});

test.describe('Ticket Detail - Reply Link Generation', () => {
  
  test.beforeEach(async ({ page }) => {
    // Remove Emergent badge
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

  test('Generate Reply Link creates link and shows copy button', async ({ page }) => {
    // Login as supervisor
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.locator('input[type="email"]').first().fill(SUPERVISOR_EMAIL);
    await page.locator('input[type="password"]').first().fill(SUPERVISOR_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
    
    // Navigate to tickets and find one without reply link (create new ticket would be ideal)
    // For this test, we use an existing ticket
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Scroll to Reply Link section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Check current state
    const generateBtn = page.getByTestId('generate-reply-link-btn');
    const linkUrl = page.getByTestId('reply-link-url');
    
    const needsGeneration = await generateBtn.isVisible().catch(() => false);
    
    if (needsGeneration) {
      // Generate the link
      await generateBtn.click();
      
      // Wait for link to appear
      await expect(page.getByTestId('copy-reply-link-btn')).toBeVisible({ timeout: 10000 });
      await expect(page.getByTestId('reply-link-url')).toBeVisible();
      
      // Verify the link URL format
      const linkValue = await page.getByTestId('reply-link-url').inputValue();
      expect(linkValue).toContain('/ticket/reply/');
    } else {
      // Link already exists, verify it's visible
      await expect(linkUrl).toBeVisible();
      const linkValue = await linkUrl.inputValue();
      expect(linkValue).toContain('/ticket/reply/');
    }
  });
});
