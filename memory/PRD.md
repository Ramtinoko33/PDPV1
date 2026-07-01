# PDPV Tickets - PRD

## Tech Stack
- Frontend: React + Shadcn UI + TailwindCSS
- Backend: FastAPI (Python)
- Database: MongoDB (Motor async)
- Storage: Emergent Object Storage
- AI Vision: GPT-5.2 via Emergent LLM Key
- Notifications: Telegram Bot + Web Push (VAPID) + Resend

## Chat Migration Notice (Feb 2026)
- **This chat (`pdpv-whatsapp`) hosted WhatsApp Fase 1 + 1.5 development.**
- **Migration outcome:** work pushed to GitHub branch `feature/whatsapp-fase-1.5` and merged into the parallel chat `intake-ai-gateway` (which had Finance module).
- **Deploy source going forward:** the other chat. Do NOT deploy from this chat after migration or you will overwrite Finance work.

## Completed Features
- [x] **WhatsApp Phase 1.5 — go-live hardening (Feb 2026):** (a) `WHATSAPP_ENABLED` env hard kill-switch (503 "disabled" se !=true) aplicado em webhook GET/POST e em ambos endpoints de envio. (b) Slot novo `WHATSAPP_BUSINESS_ACCOUNT_ID` em `.env`/`.env.example`. (c) Índice MongoDB único+sparse em `ticket_messages.external_message_id` (dedupe enforced at DB) + handler de `DuplicateKeyError` no `save_ticket_message`. (d) Bug crítico corrigido: webhook estava a gravar intakes com `status="NEW"` (não-enum) e sem `source`, partindo `/api/intake` com 500. Agora grava `status="PENDING"`, `source="whatsapp"`, `source_type="bot_whatsapp"`, `origin_channel="WHATSAPP"`. (e) `/api/tickets` e `/api/intake` (list+detail) agora têm helpers resilientes (`_safe_ticket_response`/`_safe_intake_response`) que skipam docs malformados em listas (log + skip) e devolvem 422 claro em detalhe. Status legados mapeados (NEW→PENDING, REVIEW/TRIAGED→PROCESSING). (f) Smoke-test script `/app/backend/scripts/whatsapp_smoke_test.py` valida 6 cenários pós-deploy (verify, inbound→intake, dedup, 2nd msg attach, signature opcional). (g) Testes pytest: 17/17 (13 originais + 4 novos `test_whatsapp_phase1_5.py`). Tester resilience garantido vs docs malformados.
- [x] **WhatsApp Phase 1 (Feb 2026):** Canal WhatsApp integrado no detalhe do ticket. Webhook reescrito para nunca criar tickets finais — apenas pré-tickets (`intake_requests`) ou associação a ticket/intake aberto. Endpoints novos: `GET /api/whatsapp/tickets/{id}/window` (janela 24h), `GET /api/whatsapp/intake/{id}/window`, `GET /api/whatsapp/templates` (4 templates internos), `POST /api/whatsapp/tickets/{id}/messages` (enforcement 503/409), `POST /api/whatsapp/tickets/{id}/send-quote-link`. Schema `ticket_messages` expandido (`channel, phone_to, status, raw_payload_id, template_name, error, intake_id`). Nova coleção `whatsapp_raw_payloads` com TTL 90 dias. Dedupe por `external_message_id`. Status updates (sent/delivered/read/failed) propagados. Frontend: `WhatsAppPanel.js` injetado como tab em `TicketDetail.js` com thread tipo bolha, badge da janela, templates rápidos, botão "Enviar link de orçamento". Validado por testing_agent_v3_fork (13/13 backend pytest + frontend OK — iteration_22.json).
- [x] **Módulo Assistências - Fase 2 (Feb 2026):**
  - Notificações push aos office users (admin+supervisor) ao criar nova assistência via bot (`notify_supervisors`).
  - Endpoint `GET /api/assistencias/stats/advanced` — totais, por funcionário, por status, por mês (com € faturado).
  - Endpoint `GET /api/assistencias/export/csv` — exportação CSV com BOM UTF-8 e separador `;` (compatível Excel PT).
  - Admin UI `/admin/assistencias-users` — gestão do bot (estado, configurar webhook) + autorizar funcionários (linka telegram_user_id ↔ User).
  - Sidebar: "Assistências" passou a grupo colapsável com sub-items "Lista" + "Bot & Utilizadores".
  - Frontend: botões "Estatísticas" (modal) e "CSV" (download) na AssistenciasPage (admin/supervisor only).
- [x] **Módulo Assistências - Fase 1 (Feb 2026):** Novo módulo independente para gerir assistências externas de campo, com ciclo de vida completo Funcionário → Bot Telegram → Faturação → Confirmação de Entrega.
  - **Backend** (`/app/backend/modules/assistencias/`): models.py (status flow + 7 estados + transições válidas), service.py (state machine bot 6 passos, OCR matrícula via GPT-4o, audit logs por ação), routes.py (`/api/assistencias/*`), pdf_extraction.py (extração de fatura via GPT-4o vision, PyMuPDF para render), bot_api.py (Telegram API wrapper).
  - **Schema MongoDB**: coleção `assistencias` (registo + audit_logs[]), `assistencias_bot_users` (autorizações).
  - **Permissão nova**: `has_assistencias_access` no perfil User (toggle em UserManagement).
  - **Bot Telegram (dedicado novo bot)**: `/nova_assistencia` → localização → matrícula (foto+OCR ou texto) → folha de obra → fotos adicionais (até 6) → notas (texto/voz com transcrição Whisper) → criar registo. Vars `TELEGRAM_ASSISTENCIAS_BOT_TOKEN` + `TELEGRAM_ASSISTENCIAS_WEBHOOK_SECRET` em backend/.env (token a aguardar).
  - **Frontend**: AssistenciasPage (6 cards stats + filtros + lista), AssistenciasDetail (anexos, timeline, upload PDF, modal de revisão de extração IA, envio Telegram, confirmar entrega, marcar não faturável, eliminar admin). Sidebar item novo com ícone Truck.
  - **Fluxo de faturação**: Office uploadFatura → GPT-4o extrai → modal de confirmação → envio automático ao funcionário via Telegram com botão inline "Entreguei ao cliente" → status FATURADA_CONCLUIDA.
- [x] **Code quality safe fixes round 2 (Feb 2026):** 2 catch blocks silenciosos em RentingDetail.js → `console.error`. AuthContext/NotificationContext: `value` envolvido em `useMemo` (+ `getAuthHeaders` em `useCallback`) para evitar re-render churn em consumers. App.js: 12 arrays inline `allowedRoles` movidos para 4 constantes module-level (`ROLES_ALL`, `ROLES_ALL_WITH_CREATOR`, `ROLES_MANAGERS`, `ROLES_ADMIN_ONLY`). NormalizationSettings.js: index-key com eslint-disable justificado.
- [x] **Code quality safe fixes (Feb 2026):** Resolveu 7 catch blocks silenciosos (TicketDetail.js, RentingPage.js) → `console.error`. Substituiu 9 `key={index}` por keys estáveis (CreateTicket: valor único; IntakePage: composite; CustomerManagement: eslint-disable justificado). Movidos secrets hardcoded de 5 ficheiros de teste para `os.environ.get()` com defaults. Substituído `is True/False` por `==` em test_ticket_statuses_iteration8.py.
- [x] **SLA pause on AGENDADO (Feb 2026):** `routes/tickets.py` — status AGENDADO agora pausa o SLA (igual a AGUARDA_CLIENTE) em vez de o terminar como "final". Resume automaticamente ao voltar a EM_TRATAMENTO/ABERTO/ACEITE_LINK, com nota de sistema diferenciada ("aguarda resposta do cliente" vs "ticket agendado").
- [x] **Renting admin delete (Feb 2026):** `RentingDetail.js` — botão vermelho "Eliminar" visível apenas a ADMIN, com `AlertDialog` de confirmação (mostra matrícula, avisa que é irreversível). Reaproveita endpoint existente `DELETE /api/renting/records/{id}` (já admin-only no backend).
- [x] **Sidebar Telegram grouped (Feb 2026):** Layout.js — "Telegram" e "Telegram Users" fundidos num único grupo colapsável (sub-items Configuração + Utilizadores), com auto-expand quando rota filha está ativa.
- [x] **Reports - Accepted quotes per agent (Feb 2026):** `POST /api/admin/reports` enriched with `metrics.total_accepted_value` (sum of `quote_value` where `quote_response_status=ACCEPTED`) and per-agent `quotes_accepted_count` + `quotes_accepted_value`. Frontend `/admin/reports`: "Orçamentos Aceites" card shows count + green € value; "Desempenho por Agente" table gained "Aceites (Qtd)" and "Valor Aceite" columns. **Clickable column sorting on all 6 columns** (toggle asc/desc, default Valor Aceite ↓ for top performers first) with visual arrow indicators.
- [x] **Pré-tickets unification (Feb 2026):** PDPV Bot Interno (`@PDPV_INTERNAL_BOT`, TELEGRAM_INTERNAL_BOT_TOKEN) deixou de criar em `pre_tickets`; passa a gravar em **`intake_requests`** (módulo `/intake` existente). `source=telegram, source_type=telegram_internal_bot, source_bot=PDPV_INTERNAL_BOT, origin_channel=TELEGRAM_INTERNAL_BOT`. `sender_name` = cliente (extraído pela IA); `created_by_name` = funcionário Telegram. Coleção `pre_tickets` mantida intocada (0 docs) por enquanto. `/intake` enriquecido com painel IA (confidence_score, missing_fields, mensagens originais, transcrições, image_hints), proxy de anexos `GET /api/intake/{id}/attachments/{aid}` (descarrega via Telegram CDN com bot token), badges discriminadoras (Bot Interno indigo / Bot Antigo azul). Convert dialog pré-preenche a partir de `ai_extracted`. Conversão para ticket continua 100% manual via `/convert_to_ticket`. Página admin `/admin/telegram-users` para gerir `telegram_internal_authorized_users` (ADMIN-only).
- [x] Ticket CRUD, SLA engine, Quote management, PDF generation
- [x] Public quote links (accept/reject), Acceptance questionnaire
- [x] Telegram Alerts module (bot, Vision, convert, notifications)
- [x] Telegram Alerts flow refined (Feb 2026): GENES screenshot → alert only (no ticket), explicit [Sim]/[Não] for problem photos, up to 4 problem_images compressed, then assignee. Conversion transfers problem_images to ticket (alert_image stays internal).
- [x] Telegram Alerts conversation state machine (Feb 2026): IDLE → WAITING_PROBLEM_PHOTO_CONFIRMATION → COLLECTING_PROBLEM_IMAGES (max 4, 10s inactivity) → WAITING_MECHANIC_NOTE_CONFIRMATION → COLLECTING_MECHANIC_NOTE (1 text up to 1000 chars OR 1 audio up to 60s with Whisper transcription) → WAITING_ASSIGNEE_SELECTION → IDLE. No duplicate alerts during collection. AI extraction runs only on first GENES image. /reset command for manual recovery. Alert detail UI has 3 sections (Imagem do alerta, Fotos das avarias, Comentário do mecânico). mechanic_comment transfers to ticket as internal-only.
- [x] Telegram Alerts UX tolerance (Feb 2026): Text fallback for Yes/No (sim/s/ok/não/n/...), photo in WAIT_PROBLEM_PHOTO_CONF auto-treats as YES + appends, photo in other active states asks "Add to current / Create new alert" via inline keyboard. 10-min global inactivity watchdog clears stuck state. `/restart` and `/cancel` aliases for `/reset`. State transitions logged to `telegram_alerts_state_logs` collection (chat_id, prev/new state, action, alert_id, timestamp).
- [x] Telegram Alerts comment step rebuild (Feb 2026): Three-button choice [📝 Texto] / [🎤 Áudio] / [Sem comentário] in WAITING_MECHANIC_COMMENT. New states COLLECTING_TEXT_COMMENT and COLLECTING_AUDIO_COMMENT (separate). `mechanic_comment.internal_only = True` flag. UI label renamed "Fotos da avaria" (singular). Photo confirmation message: "Quer adicionar fotos da avaria para anexar ao alerta?". Audio sent directly in WAITING_MECHANIC_COMMENT auto-transitions to audio collection.
- [x] Renting module Phase 1 (Feb 2026) — NEW isolated module `/api/renting/*`:
  - Separate Telegram bot (TELEGRAM_RENTING_BOT_TOKEN) with `/novo_renting`, `/cancelar`
  - Full state machine: driver → phone → renting company → plate photo (GPT-5.2 OCR) → KM photo (OCR) → 4 wheels in order (FE/FD/TD/TE) each with 3 photos (full/DOT/tread) + AI extraction (size/brand/model/load_speed/dot/tread_mm) → service type (6 options) → observations (text/audio with Whisper) → completed
  - Collections: `renting_records` (drafts + completed)
  - Object Storage integration via `services/storage_service` (MongoDB stores only URLs)
  - New permission `has_renting_access` (User edit toggle)
  - Frontend: `/renting` (list with filters/search + stats), `/renting/:id` (detail with editable fields, wheel photos grid, observations audio player + transcription)
  - Sidebar entry "Renting" (Car icon)
- [x] Renting Phase 2 — Reception desk + audit history (Feb 2026):
  - New `RentingStatus` value `in_progress` ("Em tratamento"). Bot finalizes as `in_progress` (not `completed`).
  - Server-side transition validation: draft→in_progress, in_progress↔completed; cannot mark `completed` without `authorization_number`.
  - New fields `proposed_tires` (textarea) + `authorization_number` (input) on detail page.
  - Audit history array embedded in `renting_records.history[]` — tracks every PUT change with `{field, old_value, new_value, changed_at, changed_by, changed_by_name}`. Telegram-driven status changes use `changed_by="telegram_bot"`.
  - UI: 3-state badge + transition buttons (Marcar Em tratamento / Concluir / Reabrir), warning when auth_number missing, History timeline card on detail.
  - Stats endpoint returns `in_progress` counter; list filter supports `in_progress`.
- [x] Renting Phase 3 — PDF + Copiar resumo (Feb 2026):
  - New endpoint `GET /api/renting/records/{id}/pdf` returns a technical PDF (ReportLab) with header navy+yellow, info table (Renting/Matrícula/Condutor/Telefone/KM/Serviço), tire technical table (medida/marca/modelo/índice/DOT/piso), 3 photos per wheel (flanco/DOT/piso), and matrícula+KM photos. Multi-page with footer pagination. Excludes internal fields: observations, history, proposed_tires, authorization_number.
  - Frontend: "📄 PDF" button (blob download with auth headers, opens in new tab) and "📋 Copiar resumo" button (client-side `buildSummaryText`, copies a clean WhatsApp/SMS-ready summary using `navigator.clipboard` with `document.execCommand` fallback).
- [x] Renting Phase 4 — Notificações internas de receção (Feb 2026):
  - New fields in `renting_records`: `seen_by_reception` (bool), `seen_by_reception_at`, `seen_by_reception_user_id`, `seen_by_reception_user_name`.
  - New endpoint `GET /api/renting/pending-count` returns unseen `in_progress` count. Sidebar polls every 30s and shows red badge ao lado de "Renting".
  - `GET /api/renting/records/{id}` now auto-marks the record as seen by current user on first detail open (idempotent; adds 1 history entry).
  - Stats endpoint exposes `pending_unseen`.
  - List filter `status=unseen` returns only `in_progress AND seen_by_reception != true`.
  - Frontend `/renting`: dedicated red "Pendentes por tratar" card section at top with quick "Abrir" button per item; list rows highlighted in pink with "Novo" badge when unseen.
  - "Por ler" added to status filter dropdown.
- [x] Quote normalizer v2 (packages, tires, priorities, commercial copy)
- [x] Client preview in quote creation (real-time debounced)
- [x] Tire brand tiers (premium/mid/budget) with taglines + Recomendado badge
- [x] Quote context system (diagnostic vs customer_request)
- [x] Smart suggestion engine (scoring: technical wording, packages, attachments, expansion)
- [x] Passive learning system (events + aggregated stats + admin view)
- [x] Context display text on public quote page

## Key Endpoints - Quote Context
- GET /api/tickets/{id}/quote-context - Get auto-detected or manual context
- PUT /api/tickets/{id}/quote-context - Set context manually
- POST /api/tickets/{id}/quote-suggestion - Compute suggestion score
- POST /api/tickets/{id}/quote-context-learn - Record learning event
- GET /api/admin/quote-context-stats - Admin stats view

## Pending
- [ ] P3: Excel import
- [ ] P3: Client portal
- [ ] P3: Estatísticas por empresa de renting + exportação CSV
- [ ] Future: WhatsApp module (blocked - needs Meta token)
- [ ] Future: Mover fluxos Renting/Alertas inline no bot interno (desligar 2 bots antigos)
- [ ] Cleanup: apagar endpoints DEPRECATED `pre_tickets` em `telegram_internal/routes.py`

## Status
**Sistema considerado pronto pelo utilizador (Feb 2026).** Backlog acima é opcional/futuro.

## Environments
- Preview: https://intake-ai-gateway.preview.emergentagent.com
- Production: https://tickets.pneusdpedrov.com
