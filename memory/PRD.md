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

### 10. Aceitação de Orçamentos pelo Cliente ✅ (ATUALIZADO 21/02/2026)
- Link único gerado com validade de 7 dias
- Página pública sem autenticação
- Estados automáticos:
  - **ACEITE_LINK** - Quando cliente aceita via link
  - **REJEITADO_LINK** - Quando cliente recusa via link
- Estes estados NÃO aparecem no dropdown manual
- Após resposta, utilizador pode mudar para AGENDADO ou FECHADO

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

## Key Changes (24/02/2026)

### Nova Funcionalidade - PDF na Página Pública de Orçamento + Validade (25/02/2026)
- **Backend:**
  - `QuoteOptionCreate/Response`: adicionado `attachment_ids: List[str] = []`
  - Novo modelo `AttachmentPublicInfo` (id, original_filename)
  - Novo modelo `QuoteOptionPublicResponse` com `attachments: List[AttachmentPublicInfo]`
  - `QuoteResponseData` agora inclui `quote_valid_until` e `ticket_attachments`
  - `TicketResponse` inclui `quote_valid_until`
  - `generate_quote_link`: define `quote_valid_until = now + 15 dias` no ticket
  - `get_public_quote`: retorna opções enriquecidas com detalhes dos anexos
  - `respond_to_quote`: bloqueia aceitação se `quote_valid_until` ultrapassado (HTTP 400)
  - Novo endpoint: `GET /api/public/quote/{token}/attachments/{id}/download` (sem auth, valida token)
- **Frontend (QuoteResponse.js):**
  - Mostra "Válido até {data}" ou "Expirado em {data}" na secção de orçamento
  - Botão "Ver detalhes (PDF)" dentro de cada opção quando tem anexos
  - Secção geral "Orçamento detalhado (PDF)" quando ticket tem anexos mas as opções não
  - Banner "Orçamento expirado. Contacte a oficina." quando expirado
  - Botões aceitar/recusar desactivados quando expirado
- **Frontend (TicketDetail.js):**
  - Checkboxes para associar PDFs do ticket a cada opção de orçamento

### Bug Fixes Críticos (P0/P1) - 24/02/2026
1. **Status ACEITE_LINK em branco** - Corrigido display de statuses automáticos (is_auto=true) no TicketDetail.js. Agora mostra Badge em vez de Select vazio para statuses como ACEITE_LINK e REJEITADO_LINK
2. **Mudança automática de status ao atribuir** - Quando ticket é atribuído, status muda automaticamente de ABERTO para EM_TRATAMENTO
3. **Falso toast de erro no link de orçamento** - Separado tratamento de erro do clipboard para não mostrar erro quando link é gerado com sucesso
4. **Dropdown para mudar status automático** - Quando ticket tem status automático (ACEITE_LINK/REJEITADO_LINK), mostra Badge + dropdown "Alterar para..." para permitir mudança para Agendado/Fechado
5. **Status em branco na lista de tickets** - Adicionado ACEITE_LINK, REJEITADO_LINK e AGENDADO aos statusLabels em TicketList.js, Dashboard.js e ArchivedTickets.js

### Nova Funcionalidade - Múltiplas Opções de Orçamento (24/02/2026)
- **Backend:**
  - Nova collection `quote_options` com: id, ticket_id, description, amount, is_accepted, accepted_at
  - Endpoints: GET/POST `/api/tickets/{ticket_id}/quote-options`
  - Campos no ticket: accepted_total, accepted_count
- **Frontend (TicketDetail.js):**
  - Formulário para adicionar múltiplas opções (descrição + valor)
  - Botão "+ Adicionar Opção" (máx 10)
  - Total automático
  - Botão "Guardar" para persistir opções
- **Página Pública (QuoteResponse.js):**
  - Checkboxes para selecionar opções (múltipla escolha)
  - Total selecionado atualiza em tempo real
  - Botões "Recusar Tudo" e "Aceitar (n)"
  - Após aceite: mostra opções aceites vs recusadas
- **Fluxo:**
  - Funcionário cria opções → Gera link → Cliente seleciona opções → Aceita → Status ACEITE_LINK
  - Ticket mostra: total orçamento, total aceite, número de opções aceites

### Funcionalidades (21/02/2026)
1. **Configuração SMTP Completa** - Servidor, porta, username, senha, SSL/TLS na UI
2. **Edição de Ticket** - Modal completo para editar todos os campos
3. **Dashboard Urgentes** - Tickets urgentes com destaque visual (sublinhado vermelho)

### Bug Fixes Anteriores
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
- [x] P3: VAPID Keys - configuração correta para Web Push ✅ (21/02/2026)
- [ ] P4: Portal do cliente (visualização de todos os tickets)

## Notes
- Email via SMTP configurável na UI admin (/admin/settings > Email)
- Sistema 100% funcional e testado
