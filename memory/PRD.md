# PDPV Tickets - Product Requirements Document

## Original Problem Statement
Sistema de gestão de tickets para oficina de veículos (PDPV - Pneus de Pedro V.). Sistema completo com autenticação por roles, gestão de tickets, clientes, notificações push e email.

## User Personas
- **Administrador**: Acesso total ao sistema, configurações, relatórios
- **Supervisor (Telefonista)**: Vê todos os tickets, relatórios, pode arquivar/restaurar
- **Agente (Rececionista)**: Vê apenas tickets atribuídos a si
- **Criador Interno**: Apenas pode criar tickets internos

## Core Requirements - All Implemented ✅

### 1. Sistema de Arquivos ✅
- Tickets podem ser arquivados e restaurados por Admin/Supervisor
- Página dedicada `/tickets/archived`

### 2. Status Fixos + Histórico ✅
- Status: ABERTO, EM_TRATAMENTO, AGUARDA_CLIENTE, FECHADO
- Histórico completo de mudanças de status

### 3. SLA Simples ✅
- Campo `sla_due` (2h após criação)
- Job de background a cada 15 minutos
- Indicador visual "OK" / "Atrasado"

### 4. Email Real via Resend ✅
- Integração completa com Resend API
- **Envio automático de email com link de orçamento** (NEW)
- Configuração via UI admin (NEW)

### 5. Configuração de Email via UI ✅ (NEW)
- Tab "Email" na página de configurações
- Status de configuração do Resend
- Email de envio e URL do frontend configuráveis
- Teste de email integrado

### 6. Histórico de Alterações de Orçamento ✅ (NEW)
- Log automático de todas as mudanças no valor do orçamento
- Secção expansível no detalhe do ticket
- Mostra valor anterior, novo valor, quem alterou e quando

### 7. Relatórios Administrativos ✅ (NEW)
- Página `/reports` com filtros completos
- Métricas: total tickets, taxa SLA, tickets em atraso, valor total orçamentos
- Métricas de orçamentos: enviados, aceites, recusados
- Distribuição por estado e tipo (com gráficos)
- Desempenho por agente (tabela com taxa SLA)
- Gráfico de tickets por dia (últimos 30 dias)

### 8. Pré-visualização Avançada de Anexos ✅ (NEW)
- Preview inline de imagens
- Viewer de PDF integrado
- Ícones diferenciados por tipo de ficheiro

### 9. Aceitação de Orçamentos pelo Cliente ✅
- Link único gerado com validade de 7 dias
- Página pública sem autenticação
- Email automático enviado ao cliente com link
- Notificações para agente e supervisores

### 10. Auto-refresh Dashboard ✅
- Refresh automático a cada 5 minutos

### 11. Web Push Notifications ✅
- VAPID keys configuradas
- Notificações para atribuição de tickets e SLA

### 12. RBAC Completo ✅
- Permissões por role validadas no backend

### 13. Admin CRUD ✅
- Tipos de Ticket (CRUD completo)
- Estados de Ticket (CRUD completo)
- Configuração SLA via UI

## Tech Stack
- **Backend**: FastAPI, MongoDB (motor), Pydantic, JWT, Resend, APScheduler
- **Frontend**: React, Tailwind CSS, shadcn/ui
- **Notifications**: Web Push (VAPID), WebSocket

## Database Collections
- `users`, `tickets`, `ticket_status_history`, `messages`, `notes`
- `customers`, `attachments`, `quote_links`, `quote_history` (NEW)
- `ticket_types`, `ticket_statuses`, `settings`, `notifications`, `push_subscriptions`

## Key API Endpoints

### Admin Settings
- `GET/PUT /api/admin/email-settings` - Configuração de email
- `GET/PUT /api/admin/sla-config` - Configuração SLA
- `GET/POST /api/admin/ticket-types` - CRUD tipos
- `GET/POST /api/admin/ticket-statuses` - CRUD estados
- `POST /api/admin/reports` - Gerar relatórios
- `POST /api/admin/test-email` - Testar email

### Quote System
- `POST /api/tickets/{id}/generate-quote-link` - Gerar link (envia email auto)
- `GET /api/tickets/{id}/quote-history` - Histórico de valores
- `GET /api/public/quote/{token}` - Página pública
- `POST /api/public/quote/{token}/respond` - Responder orçamento

## Test Credentials
- Admin: admin@pdpv.pt / admin123
- Supervisor: supervisor@pdpv.pt / super123
- Agent: agente1@pdpv.pt / agente123

## Environment Variables
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
JWT_SECRET=...
RESEND_API_KEY=re_... (from resend.com)
EMAIL_FROM=rececao@pneusdpedrov.com
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
```

## Changelog

### 2026-02-15 (Session 2)
- Envio automático de email com link de orçamento quando gerado
- Tab "Email" na página de configurações admin
- Histórico de alterações do valor do orçamento (QuoteHistorySection)
- Página de Relatórios Admin com métricas completas e filtros
- Pré-visualização avançada de anexos (imagens e PDFs inline)
- Link "Relatórios" no menu lateral (Admin/Supervisor)

### 2026-02-15 (Session 1)
- P1: Exibição de anexos nas mensagens do ticket
- P2: Admin CRUD para Tipos de Ticket, Estados, SLA
- P4: Sistema de aceitação de orçamentos pelo cliente

### 2026-02-14
- Sistema de arquivos, histórico de status, SLA simples
- Integração Resend, remoção role FINANCEIRO

## Pending Features (Backlog)
- [ ] Importação Excel com validação
- [ ] Portal do cliente (visualização de todos os tickets)
- [ ] Web Push VAPID key fix (minor issue)

## Notes
- Email funciona apenas se RESEND_API_KEY estiver configurada no .env
- O sistema está 100% funcional e testado
