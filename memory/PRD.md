# PDPV Tickets - Product Requirements Document

## Overview
Sistema completo de gestão de tickets para uma oficina de veículos (Pneus D. Pedro V).

## Architecture (After Refactoring)

### Refactoring Summary
| Metric | Before | After | Change |
|--------|--------|-------|--------|
| server.py | 4957 lines | 2563 lines | **-48%** |
| Modular routes | 0 | 2 files | +1390 lines |
| Services | 1 | 6 files | +1091 lines |

### Backend Structure
```
/app/backend/
├── server.py              # Main FastAPI app (~2563 lines - orchestration)
├── services/
│   ├── __init__.py        (89 lines)
│   ├── sla_service.py     (379 lines) - SLA business logic
│   ├── storage_service.py (77 lines)  - Object Storage operations
│   ├── ticket_service.py  (78 lines)  - Ticket helpers
│   ├── notification_service.py (193 lines) - Web Push
│   ├── auth_service.py    (85 lines)  - Auth helpers
│   └── customer_service.py (190 lines)
├── routes/
│   ├── auth.py            (203 lines) - Authentication
│   ├── customers.py       (529 lines) - Customer management
│   ├── users.py           (100 lines) - User management
│   ├── vehicles.py        (18 lines)  - Vehicle management
│   ├── tickets.py         (623 lines) - Ticket CRUD, archive, status
│   └── admin.py           (767 lines) - Admin settings, reports
├── modules/
│   ├── intake/            - Pre-ticket intake
│   ├── telegram/          - Telegram bot
│   └── whatsapp/          - WhatsApp (pending)
├── schemas/
│   ├── ticket.py
│   ├── user.py
│   └── customer.py
└── tests/
    └── test_sla_logic.py  (12 tests passing)
```

### What Remains in server.py
- Messages, Notes, Alerts, Reminders routes
- Attachments routes (upload/download)
- Dashboard routes
- Webhooks (Telegram)
- Quote system routes (options, public links, PDF generation)
- Export routes (CSV)
- Seed data
- Notifications API
- Web Push routes
- WebSocket management
- Startup/shutdown events

## Implemented Features

### Core Functionality
- [x] Ticket CRUD with channels (TELEFONE, EMAIL, PRESENCIAL, WHATSAPP, TELEGRAM)
- [x] Ticket types (ORCAMENTO_PNEUS, ORCAMENTO_MECANICA, INFORMACAO, RECLAMACAO, MARCACAO, INTERNO)
- [x] Customer/Vehicle management
- [x] User roles (ADMIN, SUPERVISOR, AGENT, INTERNAL_CREATOR)
- [x] JWT authentication with refresh tokens

### SLA System
- [x] Business hours configuration (08:30-18:30 weekdays, 08:30-13:00 Saturday)
- [x] SLA targets per ticket type (configurable in AdminSettings)
- [x] SLA pause when status = AGUARDA_CLIENTE
- [x] SLA breach detection and tracking
- [x] Unit tests for SLA logic (12 tests)

### Quote System
- [x] Quote options management
- [x] Public quote links with expiration
- [x] Quote acceptance/rejection flow
- [x] Rejection reason collection
- [x] Quote history tracking
- [x] PDF generation

### File Storage
- [x] Emergent Object Storage integration (persistent)
- [x] PDF generation for quotes
- [x] Attachment upload/download

### Notifications
- [x] Web Push notifications (VAPID)
- [x] In-app notifications
- [x] WebSocket real-time updates
- [x] Email notifications via Resend

### Integrations
- [x] Telegram Bot
- [ ] WhatsApp Business Cloud API (pending - tokens not configured)

## API Endpoints

### Auth (routes/auth.py)
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/refresh
- GET /api/auth/me

### Tickets (routes/tickets.py)
- GET /api/tickets - List active tickets
- POST /api/tickets - Create ticket
- GET /api/tickets/archived - List archived tickets
- GET /api/tickets/{id} - Get ticket details
- PUT /api/tickets/{id} - Update ticket
- POST /api/tickets/{id}/archive - Archive ticket
- POST /api/tickets/{id}/restore - Restore ticket
- GET /api/tickets/{id}/status-history - Get status history

### Admin (routes/admin.py)
- GET/POST/PUT/DELETE /api/admin/ticket-types
- GET/POST/PUT/DELETE /api/admin/ticket-statuses
- GET/PUT /api/admin/sla-config
- GET/PUT /api/admin/email-config
- GET/PUT /api/admin/branding
- POST /api/admin/reports
- GET /api/admin/reports/rejection-reasons

### Tickets (still in server.py)
- POST/GET /api/tickets/{id}/messages
- POST/GET /api/tickets/{id}/notes
- GET /api/tickets/{id}/alerts
- POST/GET /api/tickets/{id}/reminders
- POST/GET /api/tickets/{id}/attachments
- GET/POST /api/tickets/{id}/quote-options
- POST /api/tickets/{id}/generate-quote-link

### Public (server.py)
- GET /api/quote/{token}
- POST /api/quote/{token}/respond
- GET /api/quote/{token}/pdf

## Database Collections
- tickets, users, customers, vehicles
- messages, notes, attachments
- notifications, settings
- ticket_types, ticket_statuses
- quote_options, quote_history
- ticket_status_history
- push_subscriptions

## Environment Variables
- MONGO_URL, DB_NAME
- JWT_SECRET_KEY
- RESEND_API_KEY
- TELEGRAM_BOT_TOKEN
- WHATSAPP_TOKEN, WHATSAPP_VERIFY_TOKEN
- VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY
- EMERGENT_LLM_KEY

## Test Credentials
- Admin: admin@pdpv.pt / HCNMEnKMLq

## Known Issues
- Files uploaded before Object Storage integration cannot be downloaded
