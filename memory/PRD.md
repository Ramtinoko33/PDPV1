# PDPV Tickets - Product Requirements Document

## Overview
Sistema completo de gestão de tickets para uma oficina de veículos (Pneus D. Pedro V).

## Architecture (After Full Refactoring)

### Refactoring Summary
| Metric | Before | After | Change |
|--------|--------|-------|--------|
| server.py | 4957 lines | 2574 lines | **-48%** |
| Modular routes | 0 | 2 files | +1500 lines |
| Services | 1 | 6 files | +1150 lines |

### Backend Structure
```
/app/backend/
├── server.py              # Main FastAPI app (~2574 lines - orchestration)
├── services/
│   ├── __init__.py        
│   ├── sla_service.py     (~430 lines) - SLA + Holidays logic
│   ├── storage_service.py - Object Storage
│   ├── ticket_service.py  - Ticket helpers
│   ├── notification_service.py - Web Push
│   ├── auth_service.py    - Auth helpers
│   └── customer_service.py
├── routes/
│   ├── auth.py            - Authentication
│   ├── customers.py       - Customer management
│   ├── users.py           - User management
│   ├── vehicles.py        - Vehicle management
│   ├── tickets.py         (~623 lines) - Ticket CRUD, archive, status
│   └── admin.py           (~900 lines) - Types, statuses, SLA, email, branding, reports, HOLIDAYS
├── modules/
│   ├── intake/            - Pre-ticket intake
│   ├── telegram/          - Telegram bot
│   └── whatsapp/          - WhatsApp (pending)
├── schemas/
│   ├── ticket.py
│   ├── user.py
│   └── customer.py
└── tests/
    └── test_sla_logic.py  (17 tests passing)
```

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
- [x] **NEW: Holiday management** - Fixed and recurring annual holidays
- [x] Unit tests for SLA logic (17 tests including 5 holiday tests)

### Holiday System (NEW)
- [x] CRUD for holidays via `/api/admin/holidays`
- [x] Toggle active/inactive status
- [x] Fixed holidays (specific date)
- [x] Recurring annual holidays (repeat every year)
- [x] Scope: nacional/local
- [x] Integration with SLA calculation (holidays excluded)
- [x] Admin UI in Settings > Feriados tab

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
- GET /api/tickets
- POST /api/tickets
- GET /api/tickets/archived
- GET /api/tickets/{id}
- PUT /api/tickets/{id}
- POST /api/tickets/{id}/archive
- POST /api/tickets/{id}/restore
- GET /api/tickets/{id}/status-history

### Admin (routes/admin.py)
- GET/POST/PUT/DELETE /api/admin/ticket-types
- GET/POST/PUT/DELETE /api/admin/ticket-statuses
- GET/PUT /api/admin/sla-config
- GET/PUT /api/admin/email-config
- GET/PUT /api/admin/branding
- POST /api/admin/reports
- GET /api/admin/reports/rejection-reasons
- **GET /api/admin/holidays** - List all holidays
- **POST /api/admin/holidays** - Create holiday
- **PUT /api/admin/holidays/{id}** - Update holiday
- **DELETE /api/admin/holidays/{id}** - Delete holiday
- **POST /api/admin/holidays/{id}/toggle** - Toggle active status

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
- **holidays** (NEW)

## Holiday Document Schema
```json
{
  "id": "uuid",
  "date": "YYYY-MM-DD",
  "name": "string",
  "is_recurring_annual": "boolean",
  "scope": "nacional|local",
  "active": "boolean",
  "created_at": "ISO datetime"
}
```

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

## Tests
- 17 tests passing in `tests/test_sla_logic.py`:
  - 12 original SLA tests
  - 5 holiday tests:
    - test_fixed_holiday
    - test_recurring_annual_holiday
    - test_sla_across_holiday
    - test_saturday_plus_holiday
    - test_sunday_still_closed

## Known Issues
- Files uploaded before Object Storage integration cannot be downloaded
