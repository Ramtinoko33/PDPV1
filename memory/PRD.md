# PDPV Tickets - PRD (Product Requirements Document)

## Original Problem Statement
Sistema completo de gestão de tickets para oficina de veículos (Pneus D. Pedro V), com gestão de orçamentos, SLA baseado em horário útil, notificações (email, Telegram, Web Push), links públicos para aprovação/rejeição de orçamentos, e alertas de mecânicos via Telegram.

## Tech Stack
- **Frontend**: React + Shadcn UI + TailwindCSS
- **Backend**: FastAPI (Python)
- **Database**: MongoDB (Motor async driver)
- **Storage**: Emergent Object Storage
- **Emails**: Resend API
- **Notifications**: Telegram Bot + Web Push (VAPID)
- **AI Vision**: GPT-5.2 via Emergent LLM Key

## Code Architecture
```
/app
├── backend/
│   ├── modules/
│   │   ├── telegram_alerts/  (models.py, routes.py, service.py, __init__.py)
│   │   ├── telegram/
│   │   ├── whatsapp/
│   │   └── intake/
│   ├── routes/
│   │   ├── auth.py, tickets.py, admin.py, quotes.py, customers.py, users.py
│   ├── services/
│   │   ├── sla_service.py, storage_service.py, ticket_service.py, notification_service.py, customer_service.py
│   ├── schemas/
│   │   ├── user.py (has_alerts_access field), ticket.py, customer.py
│   ├── config/modules.json (intake, telegram, telegram_alerts enabled; whatsapp disabled)
│   ├── server.py (~1880 lines)
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── AlertsPage.js (NEW - /alertas)
│   │   │   ├── QuoteResponse.js, TicketDetail.js, IntakePage.js, etc.
│   │   ├── components/Layout.js (sidebar with alerts badge)
│   │   ├── App.js (routes including /alertas)
```

## Completed Features
- [x] Ticket CRUD, statuses, types, priorities
- [x] SLA engine (business hours, weekends, holidays)
- [x] Quote management with public approval links
- [x] Acceptance questionnaire (agendar/avançar/contactar + date/period)
- [x] Rejection questionnaire (7 reason codes)
- [x] PDF generation, Email/Telegram/Web Push notifications
- [x] Admin dashboard, Customer management, Reports (tire analysis, rejection)
- [x] Backend refactoring complete (62% reduction)
- [x] Vehicle plate suggestions in ticket creation
- [x] VAPID push notification sync fix
- [x] **Telegram Alerts Module - Backend** (webhook, CRUD, message buffer, GPT-5.2 Vision, conversion)
- [x] **Telegram Alerts Module - Frontend** (/alertas page, stats, SLA colors, detail modal, convert modal)
- [x] **has_alerts_access** field on User model + toggle in UserManagement
- [x] **AI Prompt updated** for CEINOR GENES software screenshots
- [x] **Conversion UI** reuses IntakePage pattern (customer search, auto-create, SLA compute)
- [x] **Base64 storage limit** bumped to 5MB

## Bugs Fixed (Apr 2026)
- [x] VAPID push notifications not sending
- [x] Vehicle plates not showing in ticket creation
- [x] Public quote page "blocked:oth"
- [x] Reports tire-analysis 404, rejection reasons model mismatch
- [x] Seed admin password mismatch

## Pending / Backlog
- [ ] P0: Register Telegram webhook for @pdpv_alertas_bot (setup-webhook endpoint ready, needs production URL)
- [ ] P1: WhatsApp Business Cloud API integration (paused by user, needs token)
- [ ] P3: Excel import functionality
- [ ] P3: Dedicated client portal

## 3rd Party Integrations
- Emergent Object Storage (Emergent LLM Key)
- Resend (User API Key)
- Telegram Bot for notifications (User API Key)
- Telegram Bot for Alerts (Bot: 8660518959)
- OpenAI GPT-5.2 Vision (Emergent LLM Key) - for alert image analysis
- WhatsApp Business Cloud API (paused)

## Key API Endpoints - Telegram Alerts
- POST /api/telegram-alerts/webhook - Receive bot updates
- POST /api/telegram-alerts/setup-webhook - Register webhook (admin)
- GET /api/telegram-alerts/alerts - List alerts (filters: status, assigned_to, pagination)
- GET /api/telegram-alerts/alerts/stats - Stats (pending/converted/dismissed/total)
- GET /api/telegram-alerts/alerts-count - Pending count for sidebar badge
- GET /api/telegram-alerts/alerts/{id} - Alert detail
- PUT /api/telegram-alerts/alerts/{id} - Update alert fields
- POST /api/telegram-alerts/alerts/{id}/convert - Convert to ticket (full form)
- POST /api/telegram-alerts/alerts/{id}/dismiss - Dismiss alert
- DELETE /api/telegram-alerts/alerts/{id} - Delete (admin only)
- GET /api/telegram-alerts/alerts/{id}/photo/{att_id} - Get photo

## Environments
- Preview: https://quote-management-4.preview.emergentagent.com
- Production: https://tickets.pneusdpedrov.com
