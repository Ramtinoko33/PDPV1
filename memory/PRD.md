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
│   │   ├── auth.py          # Login, refresh token
│   │   ├── tickets.py       # Ticket CRUD, attachments, notes
│   │   ├── admin.py         # Settings, types, SLA, branding, reports, holidays
│   │   ├── quotes.py        # Quote options, links, public quote, PDF, branding
│   │   └── customers.py     # Customer management
│   ├── services/
│   │   ├── sla_service.py   # SLA calculation (business hours, weekends, holidays)
│   │   ├── storage_service.py # Emergent Object Storage integration
│   │   ├── ticket_service.py  # Business logic helpers
│   │   └── notification_service.py # Push, Telegram, email notifications
│   ├── core/
│   │   └── security.py      # JWT auth, password hashing
│   ├── schemas/
│   │   ├── user.py           # UserRole enum
│   │   └── ticket.py         # TicketStatus enum
│   ├── db.py                 # MongoDB connection
│   ├── server.py             # App bootstrap, webhooks, dashboard, remaining routes
│   └── tests/
│       ├── test_sla_logic.py # 17 SLA tests
│       └── test_quote_extraction_iteration17.py # 22 quote extraction tests
├── frontend/
│   └── src/
│       └── pages/
│           ├── AdminSettings.js  # Settings with holidays tab
│           ├── AdminReports.js   # Reports with tire analysis
│           ├── QuoteResponse.js  # Public quote approval page
│           └── ...
```

## Key DB Collections
- `tickets`, `users`, `customers`, `notes`, `attachments`
- `quote_options`, `quote_links`
- `holidays` (`{ id, date, name, is_recurring_annual, scope, active, created_at }`)
- `settings` (types: `email_config`, `branding_config`, `sla_config`, etc.)

## Key API Endpoints
### Public (No Auth)
- `GET /api/public/branding` - Branding config for public pages
- `GET /api/public/quote/{token}` - View quote details
- `POST /api/public/quote/{token}/respond` - Accept/reject quote
- `GET /api/public/quote/{token}/pdf` - Generate PDF
- `GET /api/public/reply/{token}` - Public reply page data

### Admin
- `GET /api/admin/reports/tire-analysis` - Tire size analysis
- `GET /api/admin/reports/rejection-reasons` - Rejection stats
- `POST /api/admin/reports` - General reports
- `GET /api/admin/holidays` - Holiday management
- `GET /api/admin/branding` - Branding settings

### Tickets
- `GET/POST /api/tickets` - CRUD
- `POST /api/tickets/{id}/generate-quote-link` - Generate quote link
- `GET/POST /api/tickets/{id}/quote-options` - Quote options CRUD

## Completed Features
- [x] Ticket CRUD with statuses, types, priorities
- [x] SLA engine (business hours, weekends, holidays)
- [x] Quote management with public approval links
- [x] PDF generation for quotes
- [x] Email notifications via Resend
- [x] Telegram bot notifications
- [x] Web Push notifications (VAPID)
- [x] Admin dashboard with stats
- [x] Customer management
- [x] Attachment upload via Object Storage
- [x] Holiday management for SLA
- [x] Reports: general, tire analysis, rejection reasons
- [x] Backend refactoring (server.py 4957→1865 lines)
- [x] Public branding endpoint

## Pending / Backlog
- [ ] P1: WhatsApp Business Cloud API integration (paused by user)
- [ ] P3: Excel import functionality
- [ ] P3: Dedicated client portal

## 3rd Party Integrations
- Emergent Object Storage (Emergent LLM Key)
- Resend (User API Key for emails)
- Telegram Bot (User API Key)
- WhatsApp Business Cloud API (paused)

## Admin Credentials
- Email: admin@pdpv.pt / Password: HCNMEnKMLq
