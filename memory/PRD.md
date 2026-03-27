# PDPV Tickets - Product Requirements Document

## Overview
Sistema completo de gestão de tickets para uma oficina de veículos (Pneus D. Pedro V).

## Architecture

### Backend Structure
```
/app/backend/
├── server.py              # Main FastAPI app (~4432 lines after refactor)
├── services/
│   ├── __init__.py        # Service exports
│   ├── sla_service.py     # SLA business logic
│   ├── storage_service.py # Object Storage operations
│   ├── ticket_service.py  # Ticket helpers
│   ├── notification_service.py # Web Push notifications
│   ├── auth_service.py    # Auth helpers
│   └── customer_service.py
├── routes/
│   ├── auth.py
│   ├── customers.py
│   ├── users.py
│   └── vehicles.py
├── modules/
│   ├── intake/            # Pre-ticket intake
│   ├── telegram/          # Telegram bot
│   └── whatsapp/          # WhatsApp (empty - pending implementation)
└── tests/
    └── test_sla_logic.py
```

### Frontend Structure
```
/app/frontend/src/
├── pages/
│   ├── Dashboard.js
│   ├── TicketDetail.js
│   ├── AdminSettings.js
│   ├── AdminReports.js
│   └── QuoteResponse.js
├── components/
│   └── ui/               # Shadcn components
└── contexts/
```

## Implemented Features

### Core Functionality
- [x] Ticket CRUD with channels (TELEFONE, EMAIL, PRESENCIAL, WHATSAPP, TELEGRAM)
- [x] Ticket types (ORCAMENTO_PNEUS, ORCAMENTO_MECANICA, INFORMACAO, RECLAMACAO, MARCACAO, INTERNO)
- [x] Customer/Vehicle management
- [x] User roles (ADMIN, SUPERVISOR, AGENT, INTERNAL_CREATOR)
- [x] JWT authentication with refresh tokens

### SLA System (2024-03)
- [x] Business hours configuration (08:30-18:30 weekdays, 08:30-13:00 Saturday)
- [x] SLA targets per ticket type (configurable in AdminSettings)
- [x] SLA pause when status = AGUARDA_CLIENTE
- [x] SLA breach detection and tracking
- [x] Unit tests for SLA logic (12 tests)

### Quote System
- [x] Quote options management
- [x] Public quote links with expiration
- [x] Quote acceptance/rejection flow
- [x] Rejection reason collection (preco_alto, vai_pedir_outra_opiniao, etc.)
- [x] Quote history tracking

### File Storage
- [x] Emergent Object Storage integration (persistent across deployments)
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

## Refactoring Status (2024-03-27)

### Phase 1 - Services Extraction (COMPLETE)
- [x] `sla_service.py` - SLA calculations, business hours
- [x] `storage_service.py` - Object Storage
- [x] `ticket_service.py` - Ticket helpers
- [x] `notification_service.py` - Web Push (partial - send_web_push_to_user)

### Phase 2 - Routes Extraction (PENDING)
- [ ] Extract ticket routes to `routes/tickets.py`
- [ ] Extract quote routes to `routes/quotes.py`
- [ ] Extract admin routes to `routes/admin.py`

## API Endpoints

### Auth
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/refresh
- GET /api/auth/me

### Tickets
- GET /api/tickets
- POST /api/tickets
- GET /api/tickets/{id}
- PUT /api/tickets/{id}
- POST /api/tickets/{id}/archive
- POST /api/tickets/{id}/restore

### Admin
- GET/PUT /api/admin/sla-config
- GET/POST/PUT/DELETE /api/admin/ticket-types
- GET/POST/PUT/DELETE /api/admin/ticket-statuses
- GET/POST/PUT/DELETE /api/admin/quote-options
- GET /api/admin/reports/*

### Public
- GET /api/quote/{token}
- POST /api/quote/{token}/respond

## Database Collections
- tickets
- users
- customers
- vehicles
- messages
- notes
- attachments
- notifications
- settings
- ticket_types
- ticket_statuses
- quote_options
- quote_history
- ticket_status_history
- push_subscriptions

## Environment Variables
- MONGO_URL
- DB_NAME
- JWT_SECRET_KEY
- RESEND_API_KEY
- TELEGRAM_BOT_TOKEN
- WHATSAPP_TOKEN
- WHATSAPP_VERIFY_TOKEN
- VAPID_PUBLIC_KEY
- VAPID_PRIVATE_KEY
- EMERGENT_LLM_KEY (for Object Storage)

## Test Credentials
- Admin: admin@pdpv.pt / HCNMEnKMLq

## Known Issues
- Files uploaded before Object Storage integration cannot be downloaded
- server.py still has ~4432 lines (needs more refactoring)
