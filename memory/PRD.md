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
- **Feb 2026 (iter 51) — CodPersona banido + merge de duplicados**:
  - **Bug reportado**: PROEF Eurico Ferreira aparecia como 3 clientes distintos (`163` correcto com docs, `2111100163` errado com Carteira/Evolução, `120` errado do CodPersona) porque parsers usavam CodPersona ou Conta inteira como `genes_code`.
  - **Fix parsers**: novo `parsers/account_normalizer.py` com regex `^21111(\d+)$` + lstrip('0'). `documents_parser.py` deixa de usar CodPersona; `client_info_parser.py` e `evolution_parser.py` só aceitam Conta normalizada ou CodCliente explícito (que não começa por 21111). CodPersona banido de fallback.
  - **Filtro `GET /clients`**: exclui `is_merged_duplicate=True`.
  - **Script `merge_duplicate_finance_clients.py`**: dry-run/--confirm + backup JSON em `/tmp/finance_merge_backup_<ts>.json`. Detecta duplicados por (a) `genes_code` padrão 21111NNN, (b) fallback via `account`/`genes_account`/`conta` do doc (cobre o caso PROEF `genes_code='120'` + `account='2111100163'` → master `163`). Migra 7 colecções (`finance_credit_evolution`, `finance_documents`, `finance_actions`, `finance_promises`, `finance_regularizations`, `finance_tasks`, `finance_block_requests`), preserva valores do master em conflitos, colapsa evoluções duplicadas mantendo a mais recente. Marca duplicados com `is_merged_duplicate=True` + `merged_into` + `merged_at` + `merge_conflicts` (nunca apaga).
  - **Testes**: `test_iteration_51_conta_merge.py` (7/7 verdes incl. cenário PROEF exacto). Iters 43+48 actualizados para o novo formato numérico. Regressão total: **43/43**. Bug_testing_agent 2 iterações: 1ª detectou 3 gaps, 2ª verdict `fixed` 100% backend.
- **Feb 2026 (iter 50) — Code Review Hardening Leve**.
- **Feb 2026 (iter 49) — Hash bypass reimport + cleanup silent-zero**.
- **Feb 2026 (iter 48) — InfoClientes + Evolução Crédito Fix**.
- **Feb 2026 (iter 47) — Dashboard de Anomalias**.
- **Feb 2026 (iter 46) — Import UX Hardening**.
- **Feb 2026 (iter 45) — Frontend Hardening**.
- **Feb 2026 (iter 44) — Safety guard OVERDUE_BALANCES**.
- **Feb 2026 (iter 43) — Safety guards OPEN_DOCUMENTS + fix wipe catastrófico**.
  - **`eval()` confirmado falso positivo**: grep em `assistencias/routes.py` mostra 0 ocorrências (linha 386 é apenas o header do endpoint `/records/{id}/photo/{kind}`). CI guard `test_no_dangerous_eval.py` continua verde. Nenhuma alteração runtime.
  - **Hooks stale closures**: revisão de `TasksEffectiveness.js`, `Regularizations.js`, `NotificationContext.js` — todos com `useCallback`/`useEffect`/`useMemo` correctos. Avisos originais eram falsos positivos do linter (deps estáticas como `axios`/`API_URL`/`URLSearchParams` que são constantes de módulo). ESLint limpo. Nenhuma alteração.
  - **Empty catch em `FinanceClients.js:262`**: substituído por `console.warn` + `toast.error` amigável no fluxo de exportação Excel. Import `toast` de sonner adicionado.
  - **Array-index key em `TasksEffectiveness.js:477`**: substituído `key={i}` por `key={r.reason || 'item-${i}'}` no `ReasonList` (id natural do próprio motivo). Outros sítios apontados são casos legítimos (listas append-only de formulário com `eslint-disable` documentado ou display read-only) — não alterados.
  - **Nested ternaries críticos em `TicketDetail.js`**: user pediu para NÃO fazer refactor do TicketDetail (fica para sprint técnico separado). Nested ternaries não afectam funcionalidade — apenas legibilidade. Adiado.
  - **Rejeitado explicitamente pelo user**: split de AdminSettings/TicketDetail/IntakePage/Layout/NotificationContext, refactor de `parse_client_info()` (acabou de ser tocado na iter 48), migração localStorage→httpOnly cookies (breaking auth), alteração de credenciais de teste (preview-only, sem risco).
  - Testes regressão iter 43+44+49+eval CI: **14/14 verdes**. Frontend HTTP 200. Nenhuma alteração funcional.
- **Feb 2026 (iter 49) — Hash bypass reimport + cleanup silent-zero**.
- **Feb 2026 (iter 53) — Endpoints OWNER-only para Merge de Duplicados (utilizador sem consola PROD)**.
  - Extraiu a lógica de merge de `scripts/merge_duplicate_finance_clients.py` para novo serviço partilhado `modules/finance/services/merge_service.py` (`build_plan(db)`, `apply_plan(db, plan, actor)`).
  - Novos endpoints em `modules/finance/routes.py`, todos protegidos por `require_finance_owner`:
    - `POST /api/finance/merge-duplicates/dry-run` → gera plano, persiste em `finance_merge_reports` com `id`, `expires_at` (TTL 30 min), `status='pending'`; devolve `report_id`, `summary`, `conflicts[]`, `groups[]`. NUNCA escreve em `finance_clients`/`finance_open_documents`/`finance_credit_evolution`.
    - `GET /api/finance/merge-duplicates/reports` → últimos 20 (sem payload grande).
    - `GET /api/finance/merge-duplicates/reports/{id}` → detalhe completo com `plan`.
    - `POST /api/finance/merge-duplicates/confirm` (body `{report_id, confirmation}`) → aplica o plano gravado. Guardrails: `confirmation` tem de ser exactamente `"APROVAR"`; `report_id` válido; report em `status='pending'`; TTL ainda válido. `actor` gravado como `owner_confirm:<uid>:<name>`. Report actualizado para `applied` com `applied_at`, `applied_by`, `apply_stats`.
  - CLI `scripts/merge_duplicate_finance_clients.py` reescrito como wrapper fino sobre o novo serviço; mesmo backup JSON `/tmp/finance_merge_backup_<ts>.json`.
  - Testes: `test_iteration_53_merge_endpoints.py` (8/8 verdes): dry-run OWNER-only + intocado, 401/403 anónimo, confirm exige "APROVAR" literal, rejeita report inexistente, rejeita expirado (marca `expired`), não permite duplo confirm (409), aplica plano correctamente + soft-mark + remap `finance_open_documents` com doc_key rebuild + report `status='applied'`, listagem esconde payload e detalhe expõe.
  - Regressão iter 51+52+53 = **21/21 verdes**.

- **Feb 2026 (iter 52) — Merge Script P0 hardening (pré-deploy PROD)**.
  - `backend/scripts/merge_duplicate_finance_clients.py` agora inclui `finance_open_documents` no remapeamento por `genes_code` **e reconstrói `doc_key = "<genes_code>_<document_number>"`** com o code do master, garantindo consistência para importações posteriores.
  - Precedência do master é ABSOLUTA em todos os campos sensíveis (saldo_conta/efec/desc/dev, carteira, domiciliações, risco_raw/validado/placeholder, albaranado, forma_pagamento, eventos_raw, finance_email/mobile/phone/contact_*, customer_segment, portfolio, risk_*, credit_trend_*, annual_revenue, insured_risk_value, risk_percentage, genes_account, last_infoclientes_import_id): master vazio + dup preenchido → migra; master preenchido + dup diferente → preserva master + regista conflict; master preenchido + dup vazio → não mexe.
  - Conflitos são estruturados como `{field, master_value, duplicate_value, action:'preserved_master', reason}` e ficam no `merge_conflicts` do duplicado, no relatório stdout (`MIGRATE→MASTER` + `CONFLICT`) e no dump JSON de auditoria (`/tmp/finance_merge_backup_<ts>.json` com `summary/conflicts/groups`).
  - Contador `remap_stats` no final do `--confirm` reporta quantos docs foram remapeados por colecção+chave.
  - Testes: `test_iteration_52_merge_open_docs_and_master_precedence.py` (6/6 verdes: docs+doc_key, precedência+conflicts estruturados, credit_evolution migrada, dup escondido em `/api/finance/clients`, backup JSON auditável, master intocado quando dup vazio) + regressão iter 51 (7/7). Soft-merge preservado.

- **Feb 2026 (iter 48) — InfoClientes + Evolução Crédito Fix**.
- **Feb 2026 (iter 47) — Dashboard de Anomalias**.
- **Feb 2026 (iter 46) — Import UX Hardening**.
- **Feb 2026 (iter 45) — Frontend Hardening**.
- **Feb 2026 (iter 44) — Safety guard OVERDUE_BALANCES**.
- **Feb 2026 (iter 43) — Safety guards OPEN_DOCUMENTS + fix wipe catastrófico**.
  - **Fix cirúrgico do duplicate-check**: `POST /api/finance/imports/{type}` refactoriza a verificação de hash. Antes bloqueava qualquer duplicado; agora só bloqueia se existir um import prévio ÚTIL (status IN {imported, accepted_with_warnings} E `clients_updated>0` OU `clients_found>0` OU `clients>0` OU `documents_created>0` OU `documents>0`). Imports silenciosos antigos (bug iter 48 com 0/0) deixam de bloquear reimports legítimos. Query directa em Mongo com filtro composto (não dependente de find_one arbitrário) — resolveu edge case identificado no primeiro retest onde silent-zero + útil coexistiam.
  - **Script cleanup produção**: `backend/scripts/mark_silent_zero_imports.py` (dry-run/--confirm). Marca imports com rows_processed>10 + clients_updated=0 + documents_created=0 como `status='rejected_silent_zero'` preservando file_hash, original_file_path, totals, warnings. Dump JSON audit sempre em `/tmp/finance_silent_zero_backup_<ts>.json`. Nunca toca `finance_clients`/`finance_documents`/`finance_credit_evolution`.
  - Confirmado que NÃO existe unique index em `file_hash` — só check aplicacional (sem risco de colisão técnica ao reimportar).
  - Testes: `test_iteration_49_hash_bypass.py` (5/5 verdes: bypass, block, edge case, dry-run, confirm). Regressão total: **35/35 verdes**. Bug_testing_agent 2 iterações: 1ª detectou edge case, 2ª verdict `fixed` 100%.
- **Feb 2026 (iter 48) — InfoClientes + Evolução Crédito Fix (bug produção)**: parsers reconhecem `Conta`, guard silent-zero, enriquecimento de 13 campos incluindo `risco_placeholder`, persistência em `finance_credit_evolution`, card na ficha do cliente, counters detalhados.
- **Feb 2026 (iter 47) — Dashboard de Anomalias**: página + badge + validação com comentário.
- **Feb 2026 (iter 46) — Import UX Hardening**: cleanup + modal pré-aprovação + detecção de tipo.
- **Feb 2026 (iter 45) — Frontend Hardening**: stale-closure em `QuickCommunicationPanel.js`.
- **Feb 2026 (iter 44) — Safety guard OVERDUE_BALANCES**.
- **Feb 2026 (iter 43) — Safety guards OPEN_DOCUMENTS + fix wipe catastrófico**.
- **Feb 2026 Sprint 1 Telegram Fase 0 + 0B**: consolidação de tokens de saída + persistência renting + await crítico em alerts. 18 testes verdes. Requer redeploy.
- Feb 2026: Reset expandido de tarefas + bloqueio hard quando dados desatualizados (HTTP 409).
- Feb 2026: Novo role `FINANCE_ONLY`.
