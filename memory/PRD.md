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

### 3. SLA Avançado ✅ (ATUALIZADO 25/03/2026)
- **Página de Configuração Admin (Nova UI):**
  - **Horário de Funcionamento**: Config por dia da semana (hora início/fim, toggle fechado)
  - **SLA por Tipo de Ticket**: Campos editáveis para cada tipo em horas
  - **SLA Default (Fallback)**: Valor usado quando tipo não tem SLA específico
  - **Opções de Cálculo**:
    - Toggle: Contar apenas em horário útil
    - Toggle: Pausar SLA em "Aguarda Cliente"
    - Toggle: Ativar verificação automática de SLA
- **Backend:**
  - Config persistida em `db.settings` (type: "sla_config")
  - Config carregada no startup e recarregada ao guardar
  - Valores usados pelo `compute_sla_due()` para cálculo real
- **Business Hours (Defaults):**
  - Seg-Sex: 08:30 - 18:30 (10 horas)
  - Sábado: 08:30 - 13:00 (4.5 horas)
  - Domingo: Fechado
- **SLAs por Tipo de Ticket (Defaults):**
  - ORCAMENTO_PNEUS: 8 horas úteis
  - ORCAMENTO_MECANICA: 8 horas úteis
  - INFORMACAO: 2 horas úteis
  - RECLAMACAO: 2 horas úteis
  - MARCACAO: 3 horas úteis
  - INTERNO: 8 horas úteis
- **Pausa/Retoma de SLA (se ativado):**
  - Pausa automática quando status = `AGUARDA_CLIENTE`
  - Retoma automática quando status volta para `EM_TRATAMENTO`, `ACEITE_LINK` ou `ABERTO`
  - SLA Due é recalculado adicionando o tempo pausado
- **Novos Campos no Ticket:**
  - `sla_started_at` - Quando o SLA começou a contar
  - `sla_paused_at` - Quando o SLA foi pausado
  - `sla_paused_minutes` - Total de minutos úteis pausados
  - `sla_breached` - Se o SLA foi violado
  - `sla_breached_at` - Quando a violação ocorreu
  - `sla_target_minutes` - Minutos alvo baseado no tipo
  - `sla_policy_key` - Identificador da política (ex: SLA_ORCAMENTO_PNEUS_480min)
- **Tickets Criados Fora de Horas (se business hours ativado):**
  - Se criado ao domingo, SLA começa segunda às 08:30
  - Se criado após 18:30, SLA começa no dia seguinte às 08:30
- **Notas de Sistema:**
  - "⏸️ SLA pausado - aguarda resposta do cliente"
  - "▶️ SLA retomado - pausa de X minutos úteis"
- **Testes:** 12/12 testes unitários passaram em `/app/backend/tests/test_sla_logic.py`

### 4. Orçamentos com Motivo de Rejeição ✅ (NOVO 25/03/2026)
- **Modal de Rejeição no Link do Cliente (QuoteResponse.js):**
  - Ao clicar "Recusar Tudo", abre modal com motivos estruturados
  - 7 motivos pré-definidos:
    - preco_alto: "Preço alto"
    - vai_pedir_outra_opiniao: "Vai pedir outra opinião/orçamento"
    - resolveu_noutro_local: "Já resolveu noutro local"
    - nao_quer_avancar: "Não quer avançar para já"
    - nao_entendeu: "Não entendeu o orçamento"
    - quer_falar_primeiro: "Quer falar com a oficina primeiro"
    - outro: "Outro" (observação obrigatória)
  - Campo de observação adicional (opcional/obrigatório para "outro")
- **Dados Guardados no Ticket:**
  - `rejection_reason_code`: Código do motivo
  - `rejection_reason_label`: Label legível
  - `rejection_reason_note`: Observação adicional
  - `rejected_at`: Data/hora da rejeição
  - `rejected_via`: "link" ou outro
- **Visualização no TicketDetail.js:**
  - Card "Motivo da Rejeição" com motivo, observação e data
  - Só aparece se ticket foi rejeitado com motivo
- **Endpoint de Relatório (GET /api/admin/reports/rejection-reasons):**
  - Total de rejeições, contagem com/sem motivo
  - Breakdown por motivo, tipo de ticket e utilizador
  - Filtros: start_date, end_date, ticket_type, assigned_to
- **Validação Backend:** Código deve ser válido; "outro" requer observação
- **Compatibilidade:** Tickets antigos sem motivo continuam a funcionar

### 5. Email com SMTP ✅ (ATUALIZADO 21/02/2026)
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

### Nova Funcionalidade - Portal Público de Resposta do Cliente (25/02/2026)
- **Backend:**
  - `MessageResponse` agora inclui `from_customer: bool = False`
  - `TicketResponse` inclui `reply_link_token: Optional[str] = None`
  - Novo modelo `PublicReplyTicketData`
  - Helper `get_or_create_reply_token(ticket_id)` - gera/reutiliza token por ticket (validade 1 ano)
  - Novo endpoint: `POST /api/tickets/{id}/generate-reply-link` (autenticado)
  - Novo endpoint: `GET /api/public/reply/{token}` - dados do ticket para página pública (sem auth)
  - Novo endpoint: `POST /api/public/reply/{token}/submit` - aceita mensagem + ficheiros (multipart, sem auth); atualiza status AGUARDA_CLIENTE→EM_TRATAMENTO
  - Email de resposta ao cliente agora inclui botão "Responder / Enviar documentos" com link para o portal
- **Frontend:**
  - Nova página `TicketReplyPage.js` em `/ticket/reply/:token` (rota pública, sem auth)
  - `App.js` atualizado com nova rota
  - `TicketDetail.js`: componente `ReplyLinkSection` agora no tab Conversa (movido de Documentos em 25/02/2026)
  - `TicketDetail.js`: badge "Via Portal" nas mensagens INBOUND com `from_customer=true`
  - Bug corrigido: `Optional[List[UploadFile]]` → `List[UploadFile] = File(default=[])` para upload de ficheiros

### Melhoria UI - Lembretes e Link de Resposta no Tab Conversa (25/02/2026)
- **Alteração:**
  - Secções "Lembretes" e "Link de Resposta" movidas do tab "Documentos" para o tab "Conversa"
  - Layout em grid de 2 colunas para mostrar as duas secções lado a lado
  - `ReplyLinkSection` convertido para usar componente Card para consistência visual
- **Objetivo:** Facilitar acesso rápido às ações mais comuns sem precisar mudar de tab
- **Testes:** 12/12 testes passaram (100%) - verificado navegação, criação de lembretes, geração de links


- **Backend:**
  - `UserResponse` agora inclui `dashboard_default_types`, `dashboard_default_states`, `dashboard_only_mine`
  - Novo modelo `DashboardConfigUpdate`
  - Novo endpoint: `PUT /api/users/me/dashboard` - guarda preferências do dashboard
  - `GET /api/dashboard/stats`: aplica `dashboard_default_types` ($in) e `dashboard_only_mine` ao base_query
- **Frontend (AuthContext.js):**
  - `login()` agora chama `GET /api/auth/me` após login para incluir campos de preferências
  - Adicionada função `refreshUser()` exportada
- **Frontend (Dashboard.js):**
  - Botão "Configurar Dashboard" (ícone de engrenagem) no cabeçalho
  - Modal de configuração: checkboxes de tipos de ticket, checkboxes de estados, checkbox "Mostrar apenas meus tickets"
  - Barra de filtros rápidos: selects "Tipo" e "Estado" (nível de sessão)
  - `useEffect` que aplica filtros de preferências + filtros rápidos ao `allFetchedTickets` para derivar listas
  - `fetchData` chamado após guardar preferências para atualizar contadores imediatamente


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

### Quote Immutability + One-Time Decision (26/02/2026)
1. **Backoffice Locking:**
   - Novos campos: `quote_locked_at`, `quote_decided_at`, `quote_decision`
   - Orçamento bloqueado automaticamente ao gerar link
   - Edição retorna 409 quando locked
   - Inputs ficam read-only, badge mostra estado
2. **Public Quote One-Time Decision:**
   - Primeira resposta aceite, segunda bloqueada (409)
   - Página pública mostra "Decisão registada em [data]"
   - Checkboxes disabled após decisão
3. **New Version Workflow:**
   - Botão "Nova Versão" desbloqueia orçamento
   - Gera novo link, mantém histórico

### Bug Fixes Anteriores
- Navegação na lista de tickets
- Auto-atribuição de agentes na criação
- assigned_to_name preenchido na criação
- URLs em texto convertidos em links clicáveis nos emails (26/02/2026)
- Email duplicado removido - "Gerar Link" não envia email automático (26/02/2026)

## Test Credentials (ATUALIZADAS)
- Admin: admin@pdpv.pt / HCNMEnKMLq
- Supervisor: supervisor@pdpv.pt / f9pSIn6zRP
- Agent: agente@pdpv.pt / yHprFGvPUJ

## Pending Features (Backlog)
- [x] P1: Refatorar backend server.py em estrutura modular (/routes, /models, /services) ✅ (02/03/2026)
- [x] P1: Filtros nos Relatórios Admin (data, cliente, agente, status) ✅ (Já existia - verificado 02/03/2026)
- [ ] P2: Importação Excel com validação
- [x] P3: VAPID Keys - configuração correta para Web Push ✅ (21/02/2026)
- [ ] P4: Portal do cliente (visualização de todos os tickets)

## Refatoração do Backend (02/03/2026)
### Estrutura Modular Completa
```
backend/
  db.py              ✅ Conexão MongoDB centralizada
  server.py          ✅ Reduzido de 4896 → 3800 linhas (-1096 linhas)
  
  core/
    __init__.py      ✅
    security.py      ✅ JWT tokens, passwords, get_current_user
  
  routes/
    __init__.py      ✅
    auth.py          ✅ /register, /login, /refresh, /logout, /me
    customers.py     ✅ CRUD clientes + /search + /history + /import
    users.py         ✅ CRUD utilizadores + /me/dashboard
    vehicles.py      ✅ DELETE veículos
  
  services/
    __init__.py      ✅
    auth_service.py  ✅ Rate limiting
  
  schemas/
    __init__.py      ✅
    user.py          ✅ UserRole, UserCreate, UserLogin, UserResponse, UserUpdate
    ticket.py        ✅ TicketCreate, TicketResponse, MessageCreate, etc. (todos os enums)
    customer.py      ✅ CustomerCreate, CustomerResponse, VehicleCreate, etc.
```

### Endpoints movidos para módulos:
- **routes/auth.py**: POST /register, /login, /refresh, /logout; GET /me
- **routes/customers.py**: GET/POST/PUT/DELETE /customers, /customers/{id}, /customers/search, /customers/{id}/history, /customers/import, /customers/{id}/vehicles
- **routes/users.py**: GET/POST/PUT/DELETE /users, PUT /users/me/dashboard
- **routes/vehicles.py**: DELETE /vehicles/{id}

## Notes
- Email via SMTP configurável na UI admin (/admin/settings > Email)
- Sistema 100% funcional e testado
- Quote immutability implementado com decisão única do cliente (26/02/2026)

## Módulo Intake (Pré-Tickets) - COMPLETO (09/03/2026)

### Descrição
Sistema modular para pré-tickets que permite gerir pedidos antes de se tornarem tickets oficiais.

### Funcionalidades Implementadas ✅

#### CRUD Básico
1. **CREATE** - Criar pré-tickets manualmente
   - Campos: origem, source_type, nome, contacto, matrícula, medida pneu, mensagem
   - Validação: nome e contacto obrigatórios
2. **READ** - Listar e visualizar pré-tickets
   - Estatísticas: Pendentes, Em Processamento, Convertidos, Rejeitados
   - Tabela com todas as informações
   - **Pesquisa global** em nome, contacto, matrícula, medida, mensagem
   - **Filtros** por status e origem
   - **Paginação** para grandes volumes
3. **UPDATE** - Editar pré-tickets
   - Permite editar todos os campos antes da conversão
   - Não permite editar após conversão
4. **DELETE** - Eliminar pré-tickets
   - Apenas permite eliminar pré-tickets não convertidos
   - Não afeta tickets reais
5. **CONVERT** - Converter para ticket real
   - Cria ticket com todos os dados do pré-ticket
   - Marca pré-ticket como CONVERTED
   - Mapeia source para channel (telegram→TELEGRAM, etc.)
   - Redireciona para o ticket criado

#### Campos Auxiliares (v2)
- **source_type**: Enum com valores: `manual`, `bot_telegram`, `bot_whatsapp`, `api`, `import`
- **review_notes**: Lista de notas de revisão com autor e data
- **reviewed_by**: ID do último revisor
- **reviewed_at**: Data/hora da última revisão
- **converted_by**: Quem converteu o pré-ticket

#### Rastreabilidade Bidirecional ✅
- **Intake → Ticket**: `converted_ticket_id`, `converted_ticket_number`, `converted_at`, `converted_by`
- **Ticket → Intake**: `intake_request_id`, `intake_source`, `intake_source_type`

### Isolamento do Módulo ✅
- Pode ser ativado/desativado via `/backend/config/modules.json`
- Com módulo desativado: mostra "Módulo Desativado"
- Não afeta resto do sistema

### API Endpoints
- `GET /api/intake` - Lista com filtros, pesquisa e paginação
- `GET /api/intake/stats` - Estatísticas
- `GET /api/intake/{id}` - Detalhe
- `POST /api/intake` - Criar
- `PUT /api/intake/{id}` - Editar
- `DELETE /api/intake/{id}` - Eliminar
- `POST /api/intake/{id}/notes` - Adicionar nota
- `POST /api/intake/{id}/convert_to_ticket` - Converter

### Arquitetura
```
backend/
  config/
    modules.json     # {"intake": true/false, ...}
  modules/
    intake/
      __init__.py
      models.py      # IntakeRequestCreate, IntakeRequestResponse, ReviewNote, etc.
      routes.py      # Endpoints com paginação e notas
      service.py     # Business logic

frontend/
  src/pages/
    IntakePage.js    # UI com pesquisa, filtros, notas, paginação
```

### Testes Automatizados
- **24 testes backend** em `/app/backend/tests/test_intake_module.py`
- Cobertura: CRUD, conversão, isolamento, mapeamento source→channel, paginação

### Próximos Passos (Future)
- [x] P2: Integração com Telegram para criação automática ✅ (14/03/2026)
- [ ] P2: Integração com WhatsApp para criação automática
- [ ] P3: OCR para extração de matrículas/medidas de imagens
- [ ] P3: Reconhecimento de áudio

---

## Módulo Telegram v3 - ATUALIZADO (18/03/2026)

### Descrição
Bot Telegram que recebe mensagens de clientes e cria automaticamente pré-tickets no sistema Intake.
Agora usa **Emergent LLM Key** com GPT-5.2 para análise de texto e imagens.

### Funcionalidades
1. **Webhook** - Recebe updates do Telegram em `/api/telegram/webhook`
2. **Sistema de Buffering (v3)** - Aguarda 15 segundos para coletar múltiplas mensagens antes de processar
3. **Análise de Texto** - Usa GPT-5.2 (via Emergent LLM Key) para extrair matrícula, medida, tipo de serviço
4. **Análise de Imagens (Vision)** - Usa GPT-5.2 Vision para analisar fotos de pneus e matrículas
5. **Transcrição de Áudio** - Usa OpenAI Whisper para transcrever mensagens de voz
6. **Fallback Regex** - Se LLM falhar, usa regex para extrair dados
7. **Lookup de Cliente** - Procura cliente existente pela matrícula
8. **Confirmação** - Envia mensagem de confirmação ao utilizador

### Endpoints
- `POST /api/telegram/webhook` - Webhook público (sem auth) com buffering
- `GET /api/telegram/status` - Status do bot, LLM e features
- `POST /api/telegram/webhook/setup` - Configurar webhook (admin)
- `DELETE /api/telegram/webhook` - Remover webhook (admin)

### Configuração (.env)
```
TELEGRAM_BOT_TOKEN=xxx
EMERGENT_LLM_KEY=sk-emergent-xxx
```

### Webhook URL
`https://[seu-dominio]/api/telegram/webhook`
