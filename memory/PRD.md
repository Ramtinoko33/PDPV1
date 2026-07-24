# PRD — PDPV Tickets & CRM Finance

## Problema original
Plataforma interna full-stack para gestão de tickets de assistência e CRM Finance (cobranças) da PDPV. React + FastAPI + MongoDB, deploy em `garage-support.emergent.host`.

## O que está implementado
- Sistema de Tickets (backoffice + intake público + Telegram router com deduplicação)
- CRM Finance completo (importação staging, regularizações, micro-saldos, segmentação, comunicação manual)
- Motor de Tarefas de Hoje baseado em regras + Dashboard de Eficácia
- Reset admin de Tarefas + Eficácia + Promessas
- Role `FINANCE_ONLY` (auto-atribui `finance_role=OWNER`, backend com middleware que bloqueia acesso fora de Finance)
- **Sprint 1 (Feb 2026) — Consolidação Telegram Fase 0 + 0B**: adapter unificado, persistência renting em MongoDB, transições críticas de alerts com await.

## Sprint 1 Telegram — detalhe
- Todas as chamadas outbound Telegram passam por `modules/telegram_internal/bot_api.py` com `TELEGRAM_INTERNAL_BOT_TOKEN`.
- Tokens legacy (`TELEGRAM_RENTING_BOT_TOKEN`, `TELEGRAM_ALERTS_BOT_TOKEN`, `TELEGRAM_ASSISTENCIAS_BOT_TOKEN`) só existem como placeholders para `git revert`.
- Nova coleção `renting_bot_state` (transitional; ver docstring). Índices: uniq_chat_id, idx_updated_at, ttl_expires_at_inert (1 ano, inerte).
- Alerts `_transition` agora `async` com `await _persist_current_state` antes de responder ao utilizador.
- Adapter tem retry único em 5xx, log estruturado sem tokens/URLs/bytes/file_paths.
- 18 testes automáticos verdes (3 estáticos + 10 adapter + 2 renting restart + 3 alerts await).

## Backlog prioritizado
### P0 — Sprint 1 Telegram, remanescente
- Checklist E2E manual em Preview (pré-ticket, renting, assistência com PDF, alerta com foto/áudio, restart durante fluxo, 2 utilizadores paralelos).
- Deploy S1-A + S1-B em conjunto.

### P0 — Correções críticas do Code Review
- `eval()` em `modules/assistencias/routes.py:394` → `ast.literal_eval()`.
- Stale closures nos hooks React de `QuickCommunicationPanel`, `TasksToday`, `TasksEffectiveness`, `Regularizations`.
- JWT storage: `localStorage` → cookies httpOnly.

### Sprint 2 Telegram (aprovado, aguarda Sprint 1 em produção)
- **Fase 1**: fonte única de utilizadores (`user_id` obrigatório em `telegram_internal_authorized_users`); migração de `assistencias_bot_users`; endpoints `/api/assistencias/bot/*` → 410 Gone.
- **Fase 2**: menu com 3 sub-páginas em Administração → Telegram (Visão Geral, Utilizadores e Permissões, Logs e Manutenção). Remover `TelegramPage.js` e `AdminAssistenciasUsers.js`.
- **Fase 3**: legacy webhooks 410 Gone; `setup-webhook` só ADMIN; TTL 30d em `telegram_internal_logs`; nova coleção `telegram_internal_audit` TTL 90d.

### P1 — Security Audit residual
- SEC-001: bloquear `role=ADMIN` em auto-register.
- SEC-002: reforçar JWT secret / algoritmo.
- SEC-004: autenticar webhooks legacy (WhatsApp inbound / Telegram transcribed).
- SEC-005: proteger endpoint público `/api/seed`.

### P2 — Refactor / UX
- Namespacing dos callbacks (`renting:*`, `mech:*`, `assist:*`) — sprint dedicado.
- Refactor de componentes gigantes: `TicketDetail.js` (2200+), `AdminSettings.js` (2000+), `IntakePage.js`, `parse_client_info`.
- Sub-view "por utilizador" no Dashboard de Eficácia.
- Migração eventual de `renting_bot_state` → `telegram_internal_states` (consolidação de state schema).

### Futuro
- Relatórios financeiros semanais via Telegram.
- Integrações B2B (TecAlliance).
- IA explicativa opcional no motor de Tarefas.

## Credenciais de teste
Ver `/app/memory/test_credentials.md`.

## Últimas alterações
- **Feb 2026 (iter 48) — InfoClientes + Evolução Crédito Fix (bug produção)**:
  - **Fix parsers**: `client_info_parser.py` e `evolution_parser.py` agora reconhecem `Conta` como coluna de código de cliente (era `CodCliente`/`CODCLIENTE` apenas → ficheiros reais GENES não passavam). Bug produção: ficheiros infocliente_24_07 (28.641 linhas) e evolucaocredito3em3meses_24_07 (580 linhas) mostravam 0/0 em Importado (import silencioso).
  - **Guard silent-zero**: `process_client_info_import` e `process_credit_evolution_import` rejeitam com status='rejected' se >10 linhas processadas resultarem em 0 clientes. Mensagem clara "Nenhum cliente encontrado."
  - **Enriquecimento completo InfoClientes**: `saldo_conta`, `saldo_efec`, `saldo_desc`, `saldo_dev`, `carteira`, `domiciliacoes`, `risco_raw`, `risco_validado`, `risco_placeholder` (detecta >1M€), `albaranado`, `forma_pagamento`, `eventos_raw`, `last_infoclientes_import_id`.
  - **Persistência Evolução**: coleção `finance_credit_evolution` com formato `{genes_code, client_name, periods:{03-2025:..., ..., 06-2026:...}, last_import_id, updated_at}`.
  - **Novo endpoint** `GET /api/finance/clients/{id}/credit-evolution` → devolve series ordenada, peak, quarter_diff_abs/pct, trend (up/down/stable).
  - **Card na ficha do cliente**: "Evolução Crédito (trimestral)" com mini-gráfico Recharts 6 pontos, 4 métricas (Último, Δ abs, Δ pct, Maior exposição) e badge de tendência.
  - **Counters detalhados no histórico**: `rows_processed`, `clients_found`, `clients_matched`, `clients_updated`, `clients_ignored`, `documents_created`, `periods`. `ImportTotals` Pydantic com `extra='allow'` para serializar tudo. Frontend `FinanceImports.js` mostra `clients_updated` (não 0).
  - Testes: `test_iteration_48_infoclientes_evolucao.py` (7/7 verdes com ficheiros REAIS). Regressão iter 43+44+46+47: 30/30. Bug_testing_agent: 100% backend + 100% frontend após 2 iterações.
- **Feb 2026 (iter 47) — Dashboard de Anomalias**: página + badge + validação com comentário.
- **Feb 2026 (iter 46) — Import UX Hardening**: cleanup + modal pré-aprovação + detecção de tipo.
- **Feb 2026 (iter 45) — Frontend Hardening**: stale-closure em `QuickCommunicationPanel.js`.
- **Feb 2026 (iter 44) — Safety guard OVERDUE_BALANCES**.
- **Feb 2026 (iter 43) — Safety guards OPEN_DOCUMENTS + fix wipe catastrófico**.
- **Feb 2026 Sprint 1 Telegram Fase 0 + 0B**: consolidação de tokens de saída + persistência renting + await crítico em alerts. 18 testes verdes. Requer redeploy.
- Feb 2026: Reset expandido de tarefas + bloqueio hard quando dados desatualizados (HTTP 409).
- Feb 2026: Novo role `FINANCE_ONLY`.
