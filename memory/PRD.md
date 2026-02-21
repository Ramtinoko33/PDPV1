# PDPV Tickets - Product Requirements Document

## Original Problem Statement
Sistema de gestão de tickets para oficina de veículos (PDPV - Pneus de Pedro V.). Sistema completo com autenticação por roles, gestão de tickets, clientes, notificações push e email.

## User Personas
- **Administrador**: Acesso total ao sistema, configurações, relatórios
- **Supervisor (Telefonista)**: Vê todos os tickets, relatórios, pode arquivar/restaurar
- **Agente (Rececionista)**: Vê tickets atribuídos a si + não atribuídos (para auto-atribuir)
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

### 4. Email com SMTP ✅ (ATUALIZADO 21/02/2026)
- Configuração completa SMTP via UI admin
- Campos: servidor, porta, username, senha, SSL/TLS
- Envio automático de email com link de orçamento
- Teste de email integrado

### 5. Secção de Orçamento na Tab Conversa ✅
- Orçamento integrado no formulário de resposta
- Campo valor + checkbox enviado + botão gerar link
- Status de resposta do cliente visível inline

### 6. Permissões de Atribuição para Agentes ✅
- Agentes veem: tickets atribuídos a si + tickets não atribuídos
- Agentes podem apenas auto-atribuir
- Admin/Supervisor podem atribuir a qualquer pessoa

### 7. Histórico de Alterações de Orçamento ✅
- Log automático de todas as mudanças no valor
- Secção expansível no detalhe do ticket

### 8. Relatórios Administrativos ✅
- Página `/reports` com métricas
- Distribuição por estado e tipo

### 9. Pré-visualização de Anexos ✅
- Preview inline de imagens
- PDF viewer integrado

### 10. Aceitação de Orçamentos pelo Cliente ✅
- Link único gerado com validade de 7 dias
- Página pública sem autenticação

### 11. Admin CRUD ✅
- Tipos de Ticket, Estados, SLA, Email

### 12. Edição de Ticket ✅ (NOVO 21/02/2026)
- Modal de edição completa no detalhe do ticket
- Permite editar: nome, telefone, email, matrícula, tipo, prioridade, descrição
- Permissões baseadas em role

### 13. Dashboard com Tickets Urgentes ✅ (NOVO 21/02/2026)
- Tickets urgentes destacados com sublinhado vermelho
- Borda lateral vermelha e fundo diferenciado
- Badge "URGENTE" visível

## Tech Stack
- **Backend**: FastAPI, MongoDB (motor), Pydantic, JWT, SMTP/Resend, APScheduler
- **Frontend**: React, Tailwind CSS, shadcn/ui
- **Notifications**: Web Push (VAPID), WebSocket

## Key Changes (21/02/2026)

### Funcionalidades Adicionadas
1. **Configuração SMTP Completa** - Servidor, porta, username, senha, SSL/TLS na UI
2. **Edição de Ticket** - Modal completo para editar todos os campos
3. **Dashboard Urgentes** - Tickets urgentes com destaque visual (sublinhado vermelho)

### Bug Fixes
- Navegação na lista de tickets
- Auto-atribuição de agentes na criação
- assigned_to_name preenchido na criação

## Test Credentials (ATUALIZADAS)
- Admin: admin@pdpv.pt / HCNMEnKMLq
- Supervisor: supervisor@pdpv.pt / f9pSIn6zRP
- Agent: agente@pdpv.pt / yHprFGvPUJ

## Pending Features (Backlog)
- [ ] P1: Filtros nos Relatórios Admin (data, cliente, agente, status)
- [ ] P2: Importação Excel com validação
- [ ] P3: VAPID Keys - configuração correta para Web Push
- [ ] P4: Portal do cliente (visualização de todos os tickets)

## Notes
- Email via SMTP configurável na UI admin (/admin/settings > Email)
- Sistema 100% funcional e testado
