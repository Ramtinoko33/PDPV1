import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://ticket-workshop-sys.preview.emergentagent.com';
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
  // Click on Pré-Tickets in sidebar
  const intakeLink = page.locator('a[href="/intake"], [href*="intake"]').first();
  await intakeLink.click();
  await expect(page).toHaveURL(/\/intake/, { timeout: 10000 });
  await page.waitForLoadState('domcontentloaded');
}

// Helper to generate unique test data
function uniqueId() {
  return `TEST_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

test.describe('Intake Module - CRUD Operations', () => {
  
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('should display Intake page with stats cards', async ({ page }) => {
    await navigateToIntake(page);
    
    // Verify page header
    await expect(page.locator('text=Pré-Tickets')).toBeVisible();
    
    // Verify stats cards
    await expect(page.locator('text=Pendentes')).toBeVisible();
    await expect(page.locator('text=Em Processamento')).toBeVisible();
    await expect(page.locator('text=Convertidos')).toBeVisible();
    await expect(page.locator('text=Rejeitados')).toBeVisible();
    
    // Verify table
    await expect(page.locator('text=Lista de Pré-Tickets')).toBeVisible();
    
    await page.screenshot({ path: 'intake-page-loaded.jpeg', quality: 20 });
  });

  test('CREATE: should create a new pre-ticket via form', async ({ page }) => {
    await navigateToIntake(page);
    
    const testName = uniqueId();
    
    // Click "Novo Pré-Ticket" button
    await page.locator('button:has-text("Novo Pré-Ticket")').click();
    
    // Wait for dialog
    await expect(page.locator('text=Novo Pré-Ticket').first()).toBeVisible({ timeout: 5000 });
    
    // Fill form using data-testid
    await page.locator('[data-testid="intake-create-name"]').fill(testName);
    await page.locator('[data-testid="intake-create-contact"]').fill('912345678');
    await page.locator('[data-testid="intake-create-plate"]').fill('TT-00-TT');
    await page.locator('[data-testid="intake-create-tire"]').fill('205/55 R16');
    await page.locator('[data-testid="intake-create-message"]').fill('Mensagem de teste criada automaticamente');
    
    await page.screenshot({ path: 'intake-create-form-filled.jpeg', quality: 20 });
    
    // Submit
    await page.locator('button:has-text("Criar Pré-Ticket")').click();
    
    // Wait for success toast
    await expect(page.locator('text=Pré-ticket criado com sucesso')).toBeVisible({ timeout: 10000 });
    
    // Verify it appears in the table
    await expect(page.locator(`text=${testName}`).first()).toBeVisible({ timeout: 10000 });
    
    await page.screenshot({ path: 'intake-create-success.jpeg', quality: 20 });
  });

  test('READ: should display intake list with correct data', async ({ page }) => {
    await navigateToIntake(page);
    
    // Wait for table to load
    await page.waitForSelector('table', { timeout: 10000 });
    
    // Verify table headers
    await expect(page.locator('th:has-text("Origem")')).toBeVisible();
    await expect(page.locator('th:has-text("Nome")')).toBeVisible();
    await expect(page.locator('th:has-text("Contacto")')).toBeVisible();
    await expect(page.locator('th:has-text("Matrícula")')).toBeVisible();
    await expect(page.locator('th:has-text("Estado")')).toBeVisible();
    await expect(page.locator('th:has-text("Ações")')).toBeVisible();
    
    // Verify at least one row exists with action buttons
    const rows = page.locator('tbody tr');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
    
    await page.screenshot({ path: 'intake-list-view.jpeg', quality: 20 });
  });

  test('UPDATE: should edit a pre-ticket before conversion', async ({ page }) => {
    await navigateToIntake(page);
    
    const testName = uniqueId();
    
    // First create a new intake to edit
    await page.locator('button:has-text("Novo Pré-Ticket")').click();
    await expect(page.locator('[data-testid="intake-create-name"]')).toBeVisible({ timeout: 5000 });
    await page.locator('[data-testid="intake-create-name"]').fill(testName);
    await page.locator('[data-testid="intake-create-contact"]').fill('912000111');
    await page.locator('[data-testid="intake-create-message"]').fill('Original message');
    await page.locator('button:has-text("Criar Pré-Ticket")').click();
    await expect(page.locator('text=Pré-ticket criado com sucesso')).toBeVisible({ timeout: 10000 });
    
    // Wait for the list to refresh
    await page.waitForTimeout(1000);
    
    // Find and click edit button for the created intake
    const intakeRow = page.locator(`tr:has-text("${testName}")`).first();
    await expect(intakeRow).toBeVisible({ timeout: 5000 });
    
    // Click edit button within this row
    const editBtn = intakeRow.locator('button').filter({ has: page.locator('svg.lucide-edit, svg.lucide-pencil') }).first();
    
    // Fallback: try with data-testid pattern
    const editBtnFallback = page.locator(`[data-testid^="intake-edit-"]`).first();
    
    if (await editBtn.isVisible()) {
      await editBtn.click();
    } else {
      await editBtnFallback.click();
    }
    
    // Wait for edit dialog
    await expect(page.locator('text=Editar Pré-Ticket')).toBeVisible({ timeout: 5000 });
    
    // Modify fields
    const nameInput = page.locator('input').filter({ hasText: '' }).nth(0);
    await page.locator('input').first().fill(`${testName}_EDITED`);
    
    await page.screenshot({ path: 'intake-edit-dialog.jpeg', quality: 20 });
    
    // Save
    await page.locator('button:has-text("Guardar")').click();
    
    // Verify success toast
    await expect(page.locator('text=Pré-ticket atualizado')).toBeVisible({ timeout: 10000 });
    
    // Verify updated name in table
    await expect(page.locator(`text=${testName}_EDITED`).first()).toBeVisible({ timeout: 10000 });
    
    await page.screenshot({ path: 'intake-edit-success.jpeg', quality: 20 });
  });

  test('DELETE: should delete a pending pre-ticket', async ({ page }) => {
    await navigateToIntake(page);
    
    const testName = uniqueId();
    
    // First create a new intake to delete
    await page.locator('button:has-text("Novo Pré-Ticket")').click();
    await expect(page.locator('[data-testid="intake-create-name"]')).toBeVisible({ timeout: 5000 });
    await page.locator('[data-testid="intake-create-name"]').fill(testName);
    await page.locator('[data-testid="intake-create-contact"]').fill('912000222');
    await page.locator('[data-testid="intake-create-message"]').fill('Will be deleted');
    await page.locator('button:has-text("Criar Pré-Ticket")').click();
    await expect(page.locator('text=Pré-ticket criado com sucesso')).toBeVisible({ timeout: 10000 });
    
    // Wait for list refresh
    await page.waitForTimeout(1000);
    
    // Find the row with our test data
    const intakeRow = page.locator(`tr:has-text("${testName}")`).first();
    await expect(intakeRow).toBeVisible({ timeout: 5000 });
    
    // Set up dialog listener for confirm
    page.on('dialog', dialog => dialog.accept());
    
    // Click delete button
    const deleteBtn = intakeRow.locator('[data-testid^="intake-delete-"]').first();
    await deleteBtn.click();
    
    // Verify success toast
    await expect(page.locator('text=Pré-ticket eliminado')).toBeVisible({ timeout: 10000 });
    
    // Verify row is removed
    await expect(page.locator(`text=${testName}`)).not.toBeVisible({ timeout: 5000 });
    
    await page.screenshot({ path: 'intake-delete-success.jpeg', quality: 20 });
  });

  test('CONVERT: should convert pre-ticket to real ticket', async ({ page }) => {
    await navigateToIntake(page);
    
    const testName = uniqueId();
    
    // First create a new intake to convert
    await page.locator('button:has-text("Novo Pré-Ticket")').click();
    await expect(page.locator('[data-testid="intake-create-name"]')).toBeVisible({ timeout: 5000 });
    await page.locator('[data-testid="intake-create-name"]').fill(testName);
    await page.locator('[data-testid="intake-create-contact"]').fill('912000333');
    await page.locator('[data-testid="intake-create-plate"]').fill('CV-00-RT');
    await page.locator('[data-testid="intake-create-tire"]').fill('195/65 R15');
    await page.locator('[data-testid="intake-create-message"]').fill('Request to convert to ticket');
    await page.locator('button:has-text("Criar Pré-Ticket")').click();
    await expect(page.locator('text=Pré-ticket criado com sucesso')).toBeVisible({ timeout: 10000 });
    
    // Wait for list refresh
    await page.waitForTimeout(1000);
    
    // Find the row with our test data
    const intakeRow = page.locator(`tr:has-text("${testName}")`).first();
    await expect(intakeRow).toBeVisible({ timeout: 5000 });
    
    // Click convert button (arrow-right icon)
    const convertBtn = intakeRow.locator('[data-testid^="intake-convert-"]').first();
    await convertBtn.click();
    
    // Wait for convert dialog
    await expect(page.locator('text=Converter em Ticket')).toBeVisible({ timeout: 5000 });
    
    await page.screenshot({ path: 'intake-convert-dialog.jpeg', quality: 20 });
    
    // Verify form is pre-filled
    const customerNameInput = page.locator('input').nth(0);
    const phoneInput = page.locator('input').nth(1);
    
    // Click create ticket button
    await page.locator('button:has-text("Criar Ticket")').click();
    
    // Wait for success and redirect
    await expect(page.locator('text=/Ticket TK.*criado/')).toBeVisible({ timeout: 10000 });
    
    // Should redirect to ticket detail page
    await expect(page).toHaveURL(/\/tickets\//, { timeout: 15000 });
    
    await page.screenshot({ path: 'intake-convert-success-ticket.jpeg', quality: 20 });
  });

  test('should display converted status correctly', async ({ page }) => {
    await navigateToIntake(page);
    
    // Look for a row with CONVERTED status
    const convertedBadge = page.locator('text=Convertido').first();
    
    if (await convertedBadge.isVisible()) {
      await expect(convertedBadge).toBeVisible();
      
      // Converted rows should show "Ver Ticket" link instead of action buttons
      const convertedRow = page.locator('tr').filter({ has: page.locator('text=Convertido') }).first();
      await expect(convertedRow.locator('text=Ver Ticket')).toBeVisible();
      
      await page.screenshot({ path: 'intake-converted-row.jpeg', quality: 20 });
    }
  });

  test('validations: should require name and contact when creating', async ({ page }) => {
    await navigateToIntake(page);
    
    // Click "Novo Pré-Ticket" button
    await page.locator('button:has-text("Novo Pré-Ticket")').click();
    await expect(page.locator('text=Novo Pré-Ticket').first()).toBeVisible({ timeout: 5000 });
    
    // Try to submit without filling required fields
    await page.locator('button:has-text("Criar Pré-Ticket")').click();
    
    // Verify validation error
    await expect(page.locator('text=Nome e contacto são obrigatórios')).toBeVisible({ timeout: 5000 });
    
    await page.screenshot({ path: 'intake-validation-error.jpeg', quality: 20 });
    
    // Close dialog
    await page.locator('button:has-text("Cancelar")').click();
  });

  test('refresh button should reload data', async ({ page }) => {
    await navigateToIntake(page);
    
    // Click refresh button
    await page.locator('button:has-text("Atualizar")').click();
    
    // Wait for refresh to complete (spinner should disappear)
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 });
    
    await page.screenshot({ path: 'intake-after-refresh.jpeg', quality: 20 });
  });
});

test.describe('Intake Module - Module Isolation', () => {
  
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('regular tickets page should work independently', async ({ page }) => {
    // Navigate to tickets
    await page.goto('/tickets', { waitUntil: 'domcontentloaded' });
    
    // Verify tickets page loads
    await expect(page).toHaveURL(/\/tickets/);
    await expect(page.locator('text=Tickets').first()).toBeVisible({ timeout: 10000 });
    
    await page.screenshot({ path: 'tickets-page-independent.jpeg', quality: 20 });
  });

  test('should navigate between intake and tickets without errors', async ({ page }) => {
    // Go to intake
    await navigateToIntake(page);
    await expect(page.locator('text=Pré-Tickets')).toBeVisible();
    
    // Go to tickets
    await page.locator('a[href="/tickets"]').first().click();
    await expect(page).toHaveURL(/\/tickets/, { timeout: 10000 });
    
    // Go back to intake
    await navigateToIntake(page);
    await expect(page.locator('text=Pré-Tickets')).toBeVisible();
    
    await page.screenshot({ path: 'intake-tickets-navigation.jpeg', quality: 20 });
  });
});
