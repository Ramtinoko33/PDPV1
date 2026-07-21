# PRD — PDPV Tickets & CRM Finance

## Problema original
Plataforma interna full-stack para gestão de tickets de assistência e CRM Finance (cobranças) da PDPV. React + FastAPI + MongoDB, deploy em `garage-support.emergent.host`.

## O que está implementado
- Sistema de Tickets (backoffice + intake público + Telegram router com deduplicação)
- **CRM Finance completo**: importação em staging, regularizações, micro-saldos, segmentação, comunicação manual (Email via Resend + WhatsApp redirect), export Excel.
- **Motor de Tarefas de Hoje** baseado em regras (`task_engine.py`).
- **Dashboard de Eficácia de Tarefas** (`/api/finance/tasks/effectiveness`).
- **Reset admin** de Tarefas + Eficácia via `POST /api/finance/tasks/reset?confirm=RESET` (OWNER only) — Feb 2026.

## Roles Finance
- OWNER, FINANCE_REVIEWER, COLLECTIONS_AGENT.

## Backlog prioritizado
### P0 — Correções Críticas (Code Review pendente)
- Remover `eval()` em `modules/assistencias/routes.py:394` → `ast.literal_eval()`.
- Corrigir dependências de hooks em `QuickCommunicationPanel.js`, `TasksToday.js`, `TasksEffectiveness.js`, `Regularizations.js`.
- Rever armazenamento de JWT (`AuthContext.js`, `usePushNotifications.js`).

### P1 — Security Audit
- SEC-001: bloquear `role=ADMIN` em auto-register.
- SEC-002: reforçar JWT secret / algoritmo.
- SEC-004: autenticar webhooks legacy (WhatsApp inbound / Telegram transcribed).
- SEC-005: proteger endpoint público `/api/seed`.

### P2 — Refactor / UX
- Namespace obrigatório de callbacks Telegram (`renting:*`, etc.).
- Sub-view "por utilizador" no Dashboard de Eficácia.
- IA explicativa opcional no motor de Tarefas.
- Refactor de componentes gigantes: `TicketDetail.js` (2200+), `AdminSettings.js` (2000+), `IntakePage.js`, `parse_client_info`.
- Limpeza `console.log`, index-as-key.

### Futuro
- Relatórios financeiros semanais via Telegram.
- Integrações B2B (TecAlliance).

## Credenciais de teste
Ver `/app/memory/test_credentials.md`.

## Última alteração
- Feb 2026: Adicionado endpoint `POST /api/finance/tasks/reset` (OWNER only, requer `confirm=RESET`). Limpa `finance_tasks` completamente e apaga apenas actions de feedback de tarefas. Validado em Preview.
