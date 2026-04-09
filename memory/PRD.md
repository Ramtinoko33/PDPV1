# PDPV Tickets - PRD (Product Requirements Document)

## Original Problem Statement
Sistema completo de gestão de tickets para oficina de veículos (Pneus D. Pedro V), com gestão de orçamentos, SLA baseado em horário útil, notificações (email, Telegram, Web Push), e links públicos para aprovação/rejeição de orçamentos.

## Tech Stack
- **Frontend**: React + Shadcn UI + TailwindCSS
- **Backend**: FastAPI (Python)
- **Database**: MongoDB (Motor async driver)
- **Storage**: Emergent Object Storage
- **Emails**: Resend API
- **Notifications**: Telegram Bot + Web Push (VAPID)

## Code Architecture
```
/app
├── backend/
│   ├── routes/
│   │   ├── auth.py, tickets.py, admin.py, quotes.py, customers.py
│   ├── services/
│   │   ├── sla_service.py, storage_service.py, ticket_service.py, notification_service.py
│   ├── schemas/
│   │   ├── user.py, ticket.py (TicketResponse includes acceptance_intent fields)
│   ├── server.py (~1880 lines, down from 4957)
```

## Completed Features
- [x] Ticket CRUD, statuses, types, priorities
- [x] SLA engine (business hours, weekends, holidays)
- [x] Quote management with public approval links
- [x] **Acceptance questionnaire** (agendar/avançar/contactar + date/period)
- [x] **Rejection questionnaire** (7 reason codes)
- [x] PDF generation, Email/Telegram/Web Push notifications
- [x] Admin dashboard, Customer management, Reports (tire analysis, rejection)
- [x] Backend refactoring complete (62% reduction)
- [x] Vehicle plate suggestions in ticket creation
- [x] VAPID push notification sync fix

## Bugs Fixed (Apr 2026)
- [x] VAPID push notifications not sending (notification_service.py VAPID_KEYS_VALID never synced)
- [x] Vehicle plates not showing in ticket creation (search returned plates[] not vehicles[])
- [x] Public quote page "blocked:oth" (missing /api/public/branding)
- [x] Reports tire-analysis 404, rejection reasons model mismatch
- [x] Seed admin password mismatch

## Pending / Backlog
- [ ] P1: WhatsApp Business Cloud API integration (paused by user)
- [ ] P3: Excel import functionality
- [ ] P3: Dedicated client portal

## 3rd Party Integrations
- Emergent Object Storage (Emergent LLM Key)
- Resend (User API Key), Telegram Bot (User API Key)
- WhatsApp Business Cloud API (paused)

## Environments
- Preview: https://quote-management-4.preview.emergentagent.com
- Production: https://tickets.pneusdpedrov.com
