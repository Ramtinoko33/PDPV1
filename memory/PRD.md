# PDPV Tickets - Product Requirements Document

## Overview
Sistema completo de gestão de tickets para uma oficina de veículos (Pneus D. Pedro V).

## Architecture

### Backend Structure (After Refactoring)
```
/app/backend/
├── server.py              # Main FastAPI app (~3819 lines - reduced from 4957)
├── services/
│   ├── __init__.py        # Service exports
│   ├── sla_service.py     # SLA business logic (~380 lines)
│   ├── storage_service.py # Object Storage operations
│   ├── ticket_service.py  # Ticket helpers
│   ├── notification_service.py # Web Push notifications
│   ├── auth_service.py    # Auth helpers
│   └── customer_service.py
├── routes/
│   ├── auth.py            # Authentication routes
│   ├── customers.py       # Customer management
│   ├── users.py           # User management
│   ├── vehicles.py        # Vehicle management
│   └── tickets.py         # NEW - Ticket CRUD routes (~600 lines)
├── modules/
│   ├── intake/            # Pre-ticket intake
│   ├── telegram/          # Telegram bot
│   └── whatsapp/          # WhatsApp (pending implementation)
├── schemas/
│   ├── ticket.py
│   ├── user.py
│   └── customer.py
└── tests/
    └── test_sla_logic.py
```

### Refactoring Progress
| Phase | Lines Removed | Status |
|-------|---------------|--------|
| Phase 1 - Services | ~525 lines | ✅ Complete |
| Phase 2 - Tickets Router | ~614 lines | ✅ Complete |
| **Total** | **~1138 lines** | **23% reduction** |

### Remaining in server.py
- Messages, Notes, Alerts, Reminders routes
- Attachments routes
- Dashboard routes
- Webhooks (Telegram, WhatsApp)
- Admin settings routes
- Quote routes (options, public links, PDF)
- Export routes
- Notifications routes
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

### Auth
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

### Tickets (still in server.py)
- POST/GET /api/tickets/{id}/messages
- POST/GET /api/tickets/{id}/notes
- GET /api/tickets/{id}/alerts
- POST/GET /api/tickets/{id}/reminders
- POST/GET /api/tickets/{id}/attachments

### Admin
- GET/PUT /api/admin/sla-config
- GET/POST/PUT/DELETE /api/admin/ticket-types
- GET/POST/PUT/DELETE /api/admin/ticket-statuses

### Public
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
