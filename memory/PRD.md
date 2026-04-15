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
│   │   │   ├── AlertsPage.js (/alertas)
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
- [x] Admin dashboard, Customer management, Reports
- [x] Backend refactoring complete (62% reduction)
- [x] Vehicle plate suggestions in ticket creation
- [x] VAPID push notification sync fix
- [x] Telegram Alerts - Backend (webhook, CRUD, message buffer, GPT-5.2 Vision, conversion)
- [x] Telegram Alerts - Frontend (/alertas page, stats, SLA colors, detail modal, convert modal)
- [x] has_alerts_access field on User model + toggle in UserManagement
- [x] AI Prompt for CEINOR GENES screenshots (is_alert, license_plate, client_name, items)
- [x] Conversion UI reuses IntakePage pattern (customer search, auto-create, SLA compute)
- [x] Base64 storage limit 5MB, Object Storage via put_object
- [x] Webhook registered for @pdpv_alertas_bot on PRODUCTION (tickets.pneusdpedrov.com)
- [x] GPT-5.2 Vision tested and validated (extracts plate, name, items from CEINOR GENES screenshots)
- [x] Photo display in alert detail modal (base64 and Object Storage)
- [x] Bug fix: /tickets/{id}/alerts 500 (telegram_alerts collection conflict)
- [x] Bug fix: storage_service import (upload_object → put_object)
- [x] Bug fix: get_download_url → get_object for photo endpoint

## Bugs Fixed (Apr 2026)
- [x] VAPID push notifications not sending
- [x] Vehicle plates not showing in ticket creation
- [x] Public quote page "blocked:oth"
- [x] Reports tire-analysis 404
- [x] Seed admin password mismatch
- [x] /tickets/{id}/alerts 500 for alert-converted tickets
- [x] storage_service.upload_object → put_object
- [x] get_download_url → get_object for photo retrieval

## Pending / Backlog
- [ ] P1: WhatsApp Business Cloud API integration (paused, needs token)
- [ ] P3: Excel import functionality
- [ ] P3: Dedicated client portal

## Environments
- Preview: https://quote-management-4.preview.emergentagent.com
- Production: https://tickets.pneusdpedrov.com
