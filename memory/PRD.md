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

### 4. Email Real via Resend ✅
- Integração completa com Resend API
- Envio automático de email com link de orçamento
- Configuração via UI admin

### 5. Secção de Orçamento na Tab Conversa ✅ (REORGANIZADO)
- Orçamento agora integrado no formulário de resposta
- Campo valor + checkbox enviado + botão gerar link - tudo compacto
- Status de resposta do cliente visível inline

### 6. Permissões de Atribuição para Agentes ✅ (NEW)
- Agentes podem ver: tickets atribuídos a si + tickets não atribuídos
- Agentes podem apenas auto-atribuir (botão "Atribuir a mim")
- Agentes NÃO podem atribuir tickets a outros utilizadores
- Admin/Supervisor podem atribuir a qualquer pessoa

### 7. Histórico de Alterações de Orçamento ✅
- Log automático de todas as mudanças no valor
- Secção expansível no detalhe do ticket

### 8. Relatórios Administrativos ✅
- Página `/reports` com filtros completos
- Métricas: total tickets, taxa SLA, em atraso, valor total
- Distribuição por estado e tipo com gráficos
- Desempenho por agente

### 9. Pré-visualização Avançada de Anexos ✅
- Preview inline de imagens
- PDF viewer integrado

### 10. Aceitação de Orçamentos pelo Cliente ✅
- Link único gerado com validade de 7 dias
- Página pública sem autenticação
- Email automático enviado ao cliente

### 11. Admin CRUD ✅
- Tipos de Ticket, Estados, SLA, Email - tudo via UI

## Tech Stack
- **Backend**: FastAPI, MongoDB (motor), Pydantic, JWT, Resend, APScheduler
- **Frontend**: React, Tailwind CSS, shadcn/ui
- **Notifications**: Web Push (VAPID), WebSocket

## Key Changes This Session (15/02/2026)

### Bug Fixes Concluídos ✅
1. **Navegação na Lista de Tickets** - TableRow agora tem onClick handler para navegar para detalhe
2. **Auto-atribuição na Criação** - Agentes conseguem selecionar-se no dropdown "Atribuir a" ao criar ticket
3. **assigned_to_name** - Backend agora popula o nome do utilizador atribuído na criação

### Alterações Anteriores
- Orçamento movido para Tab Conversa (integrado com formulário de resposta)
- Permissões de Agentes: veem tickets atribuídos + não atribuídos, podem auto-atribuir

## Test Credentials
- Admin: admin@pdpv.pt / admin123
- Supervisor: supervisor@pdpv.pt / super123
- Agent: agente@pdpv.pt / agente123

## Pending Features (Backlog)
- [ ] P1: Filtros nos Relatórios Admin (data, cliente, agente, status)
- [ ] P2: Importação Excel com validação
- [ ] P3: VAPID Keys - configuração correta para Web Push
- [ ] P4: Portal do cliente (visualização de todos os tickets)

## Notes
- Email funciona apenas se RESEND_API_KEY estiver configurada no .env
- O sistema está 100% funcional e testado
