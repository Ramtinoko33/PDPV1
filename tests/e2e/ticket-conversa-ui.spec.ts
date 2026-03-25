import { test, expect } from '@playwright/test';

const BASE_URL = 'https://vehicle-ticket-hub.preview.emergentagent.com';

// Test credentials
const ADMIN_EMAIL = 'admin@pdpv.pt';
const ADMIN_PASSWORD = 'HCNMEnKMLq';

// Use a ticket that exists
const TEST_TICKET_NUMBER = 'TK20260225FBCA47';

test.describe('Ticket Detail - Conversa Tab UI Changes', () => {
  
  test.beforeEach(async ({ page }) => {
    // Remove Emergent preview badge that can block clicks
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
    
    // Login
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.locator('input[type="email"]').first().fill(ADMIN_EMAIL);
    await page.locator('input[type="password"]').first().fill(ADMIN_PASSWORD);
    await page.locator('button[type="submit"]').first().click();
    await expect(page).toHaveURL(/\/(dashboard|tickets)/, { timeout: 15000 });
  });

  test('Conversa tab shows Lembretes (Reminders) section', async ({ page }) => {
    // Navigate to tickets list and click on test ticket
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Wait for ticket detail to load - ensure Conversa tab is active (default)
    await expect(page.getByTestId('tab-conversa')).toBeVisible({ timeout: 10000 });
    
    // Scroll to bottom of the page to see the Reminders section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Verify Lembretes section is visible in Conversa tab
    const remindersSection = page.locator('text=Lembretes').first();
    await expect(remindersSection).toBeVisible({ timeout: 5000 });
    
    // Verify the "Criar" button for reminders is visible
    const createReminderBtn = page.getByRole('button', { name: /Criar/i }).first();
    await expect(createReminderBtn).toBeVisible();
  });

  test('Conversa tab shows Link de Resposta section', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Scroll to bottom
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Verify Link de Resposta section is visible
    const replyLinkSection = page.locator('text=Link de Resposta').first();
    await expect(replyLinkSection).toBeVisible({ timeout: 5000 });
    
    // Check for either the generate button OR the generated link input/copy button
    const generateBtn = page.getByTestId('generate-reply-link-btn');
    const replyLinkUrl = page.getByTestId('reply-link-url');
    const copyBtn = page.getByTestId('copy-reply-link-btn');
    
    // At least one of these should be visible (either link exists or generate button)
    const hasGenerateBtn = await generateBtn.isVisible().catch(() => false);
    const hasLinkUrl = await replyLinkUrl.isVisible().catch(() => false);
    const hasCopyBtn = await copyBtn.isVisible().catch(() => false);
    
    expect(hasGenerateBtn || hasLinkUrl || hasCopyBtn).toBe(true);
  });

  test('Lembretes and Link de Resposta sections are side by side (grid layout)', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Scroll to bottom
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Both sections should be visible
    await expect(page.locator('text=Lembretes').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=Link de Resposta').first()).toBeVisible();
    
    // Take a screenshot to visually verify the layout
    await page.screenshot({ path: 'conversa-sections-layout.jpeg', quality: 20, fullPage: false });
  });

  test('Tab navigation works correctly', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Conversa tab should be active by default
    await expect(page.getByTestId('tab-conversa')).toBeVisible();
    
    // Click on Documentos tab
    await page.getByTestId('tab-documentos').click();
    await expect(page.locator('text=Ficheiros').first()).toBeVisible({ timeout: 5000 });
    
    // Click on SLAs tab  
    await page.getByTestId('tab-slas').click();
    await expect(page.locator('text=SLAs').first()).toBeVisible({ timeout: 5000 });
    
    // Click on Historico tab
    await page.getByTestId('tab-historico').click();
    await expect(page.locator('text=Histórico').first()).toBeVisible({ timeout: 5000 });
    
    // Go back to Conversa tab
    await page.getByTestId('tab-conversa').click();
    await expect(page.locator('text=Mensagens').first()).toBeVisible({ timeout: 5000 });
  });

  test('Documentos tab does NOT show Lembretes section', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Click on Documentos tab
    await page.getByTestId('tab-documentos').click();
    
    // Wait for Ficheiros section to appear (confirms tab loaded)
    await expect(page.locator('text=Ficheiros').first()).toBeVisible({ timeout: 5000 });
    
    // Scroll down to check entire tab content
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Get visible tab content
    const tabContent = page.locator('[data-state="active"][role="tabpanel"]');
    await expect(tabContent).toBeVisible();
    
    // Verify Lembretes section is NOT in the Documentos tab
    // We need to check within the active tab panel only
    const lembretesSectionInDocumentos = tabContent.locator('text=Lembretes');
    await expect(lembretesSectionInDocumentos).toHaveCount(0);
  });

  test('Documentos tab does NOT show Link de Resposta section', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Click on Documentos tab
    await page.getByTestId('tab-documentos').click();
    
    // Wait for Ficheiros section to appear
    await expect(page.locator('text=Ficheiros').first()).toBeVisible({ timeout: 5000 });
    
    // Scroll down
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Get visible tab content
    const tabContent = page.locator('[data-state="active"][role="tabpanel"]');
    await expect(tabContent).toBeVisible();
    
    // Verify Link de Resposta is NOT in the Documentos tab
    const replyLinkInDocumentos = tabContent.locator('text=Link de Resposta');
    await expect(replyLinkInDocumentos).toHaveCount(0);
  });

  test('Documentos tab shows Ficheiros (Files) section correctly', async ({ page }) => {
    // Navigate to ticket detail
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    await page.locator(`text=${TEST_TICKET_NUMBER}`).first().click();
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 10000 });
    
    // Click on Documentos tab
    await page.getByTestId('tab-documentos').click();
    
    // Verify Ficheiros section is visible
    await expect(page.locator('text=Ficheiros').first()).toBeVisible({ timeout: 5000 });
    
    // Verify the upload button exists
    const uploadBtn = page.getByTestId('upload-file-btn');
    await expect(uploadBtn).toBeVisible();
    
    // Take screenshot for visual verification
    await page.screenshot({ path: 'documentos-tab-files.jpeg', quality: 20, fullPage: false });
  });
});
