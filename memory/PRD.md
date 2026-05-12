# PDPV Tickets - PRD

## Tech Stack
- Frontend: React + Shadcn UI + TailwindCSS
- Backend: FastAPI (Python)
- Database: MongoDB (Motor async)
- Storage: Emergent Object Storage
- AI Vision: GPT-5.2 via Emergent LLM Key
- Notifications: Telegram Bot + Web Push (VAPID) + Resend

## Completed Features
- [x] Ticket CRUD, SLA engine, Quote management, PDF generation
- [x] Public quote links (accept/reject), Acceptance questionnaire
- [x] Telegram Alerts module (bot, Vision, convert, notifications)
- [x] Telegram Alerts flow refined (Feb 2026): GENES screenshot → alert only (no ticket), explicit [Sim]/[Não] for problem photos, up to 4 problem_images compressed, then assignee. Conversion transfers problem_images to ticket (alert_image stays internal).
- [x] Telegram Alerts conversation state machine (Feb 2026): IDLE → WAITING_PROBLEM_PHOTO_CONFIRMATION → COLLECTING_PROBLEM_IMAGES (max 4, 10s inactivity) → WAITING_MECHANIC_NOTE_CONFIRMATION → COLLECTING_MECHANIC_NOTE (1 text up to 1000 chars OR 1 audio up to 60s with Whisper transcription) → WAITING_ASSIGNEE_SELECTION → IDLE. No duplicate alerts during collection. AI extraction runs only on first GENES image. /reset command for manual recovery. Alert detail UI has 3 sections (Imagem do alerta, Fotos das avarias, Comentário do mecânico). mechanic_comment transfers to ticket as internal-only.
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
- [ ] P1: WhatsApp module (blocked - needs Meta token)
- [ ] P3: Excel import
- [ ] P3: Client portal

## Environments
- Preview: https://quote-management-4.preview.emergentagent.com
- Production: https://tickets.pneusdpedrov.com
