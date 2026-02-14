# PDPV Tickets - Product Requirements Document

## Original Problem Statement
Sistema de gestão de tickets para oficina de veículos (PDPV - Pneus de Pedro V.). Sistema completo com autenticação por roles, gestão de tickets, clientes, notificações push e email.

## User Personas
- **Administrador**: Acesso total ao sistema, configurações, arquivar/restaurar
- **Supervisor (Telefonista)**: Vê todos os tickets, pode arquivar/restaurar, atribuir tickets
- **Agente (Rececionista)**: Vê apenas tickets atribuídos a si
- **Criador Interno**: Apenas pode criar tickets internos

## Core Requirements

### Funcionalidades Implementadas

#### 1. Sistema de Arquivos (P0) ✅
- Campos `archived_at` e `archived_by` no modelo Ticket
- Tickets arquivados não aparecem no dashboard/lista principal
- Página dedicada `/tickets/archived` para Admin/Supervisor
- Botões Arquivar/Restaurar com validação de permissões na API

#### 2. Status Fixos + Histórico (P0) ✅
- Status limitados: ABERTO, EM_TRATAMENTO, AGUARDA_CLIENTE, FECHADO
- Coleção `TicketStatusHistory` para logging de mudanças
- Endpoint `/tickets/{id}/status-history` para consultar histórico

#### 3. SLA Simples (P0) ✅
- Campo `sla_due` (2h após criação)
- Campo `first_response_done` para marcar primeira resposta
- Job de background a cada 15 minutos para identificar tickets atrasados
- Indicador visual "OK" / "Atrasado" nas listas e dashboard
- Notificações automáticas para tickets em atraso

#### 4. Email Real via Resend (P0) ✅
- Integração com Resend API implementada
- Subject inclui `[Ticket #TK...]`
- Variáveis de ambiente: `RESEND_API_KEY`, `EMAIL_FROM`
- Endpoint `/api/admin/test-email` para testar configuração
- Endpoint `/api/admin/email-config` para verificar status

#### 5. Auto-refresh Dashboard (P0) ✅
- Refresh automático a cada 5 minutos

#### 6. Web Push Notifications ✅
- VAPID keys configuradas
- Service worker implementado
- Notificações para atribuição de tickets e SLA

#### 7. RBAC (P0) ✅
- ADMIN: acesso total
- SUPERVISOR: todos tickets + arquivar/restaurar
- AGENT: apenas tickets atribuídos
- Permissões validadas no backend (API)

### Funcionalidades Pendentes

#### P2 - Organização
- [ ] CRUD de estados (atualmente fixos no código)
- [ ] CRUD de tipologias (urgente, normal, etc.)
- [ ] Configuração de SLA via admin

#### P3 - Comunicação
- [ ] Configuração SMTP via UI (atualmente via .env)

#### P4 - Operacional
- [ ] Importação Excel com validação
- [ ] Pré-visualização de anexos (atualmente só download)
- [ ] Histórico de orçamento
- [ ] Relatórios completos
- [ ] Portal do cliente

## Tech Stack
- **Backend**: FastAPI, MongoDB (motor), Pydantic, JWT, Resend
- **Frontend**: React, Tailwind CSS, shadcn/ui
- **Notifications**: Web Push (VAPID), WebSocket

## Database Schema

### Collections
- `users`: {id, email, password_hash, name, role, created_at}
- `tickets`: {id, ticket_number, status, type, channel, priority, customer_*, sla_due, first_response_done, archived_at, archived_by, ...}
- `ticket_status_history`: {id, ticket_id, old_status, new_status, changed_by_user_id, changed_at}
- `messages`: {id, ticket_id, direction, channel, body, attachment_ids, ...}
- `notes`: {id, ticket_id, body, is_system, ...}
- `customers`: {id, customer_code, name, nif, phones, emails, vehicles}
- `notifications`: {id, user_id, title, body, type, read, ...}
- `push_subscriptions`: {id, user_id, endpoint, keys, ...}

## API Endpoints

### Auth
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me

### Tickets
- GET /api/tickets
- POST /api/tickets
- GET /api/tickets/{id}
- PUT /api/tickets/{id}
- GET /api/tickets/archived (Admin/Supervisor only)
- POST /api/tickets/{id}/archive (Admin/Supervisor only)
- POST /api/tickets/{id}/restore (Admin/Supervisor only)
- GET /api/tickets/{id}/status-history

### Messages/Notes
- GET/POST /api/tickets/{id}/messages
- GET/POST /api/tickets/{id}/notes

### Admin
- GET /api/admin/email-config
- POST /api/admin/test-email

### Dashboard
- GET /api/dashboard/stats

## Test Credentials
- Admin: admin@pdpv.pt / admin123
- Supervisor: supervisor@pdpv.pt / super123
- Agent: agente@pdpv.pt / agente123

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

### 2026-02-14
- Implementado sistema de arquivos (P0)
- Migrado status para: ABERTO, EM_TRATAMENTO, AGUARDA_CLIENTE, FECHADO
- Implementado histórico de mudança de status
- Implementado SLA simples com job de 15 minutos
- Integração Resend para envio de emails
- Botão de teste de email na página de administração
- Removido role FINANCEIRO
- Migração de dados antigos para novos status

### Anteriormente
- Sistema base de tickets
- Autenticação JWT
- Gestão de clientes
- Web Push notifications
- Auto-refresh dashboard 5 min
- Anexos em mensagens
