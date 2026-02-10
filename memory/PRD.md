# PDPV Tickets - Product Requirements Document

## Problema Original
Sistema de gestão de pedidos para oficina automóvel (PDPV Tickets) com UI em português. Sistema de ticketing com controlo de acesso baseado em funções (RBAC), tracking de SLA, webhooks para WhatsApp/Telegram, e gestão de ficheiros.

## Arquitetura

### Backend (FastAPI + MongoDB)
- **Autenticação**: JWT com tokens de 24h
- **Base de Dados**: MongoDB com coleções para users, tickets, messages, notes, alerts, attachments
- **APIs**: Todas com prefixo /api
- **Ficheiros**: Armazenamento local em /app/backend/uploads

### Frontend (React + Tailwind + shadcn/ui)
- **Design**: Industrial Pilot com cores Safety Orange e Mechanic Blue
- **Fontes**: Chivo (títulos), Manrope (corpo), JetBrains Mono (dados)
- **Componentes**: shadcn/ui customizados

## Funcionalidades Implementadas

### 1. Autenticação e RBAC
- [x] Login com JWT
- [x] 5 funções: ADMIN, SUPERVISOR, AGENT, FINANCEIRO, INTERNAL_CREATOR
- [x] Proteção de rotas baseada em funções

### 2. Dashboard
- [x] Estatísticas: Novos, Atrasados SLA, Aguarda Cliente, Em Orçamento
- [x] Pesquisa global (telefone, matrícula, nº ticket)
- [x] Tickets recentes e atrasados

### 3. Gestão de Tickets
- [x] Criação rápida (<60s) com campos: telefone, nome, email, matrícula, tipo, canal, prioridade, descrição
- [x] Lista com filtros: estado, tipo, canal, SLA, atribuição
- [x] Detalhes com tabs: Conversa, Documentos, SLAs/Alertas, Histórico
- [x] Alteração inline de estado e atribuição (Supervisor)

### 4. Comunicação
- [x] Mensagens de email (MOCK - apenas log)
- [x] Notas internas
- [x] Timeline de mensagens

### 5. Ficheiros
- [x] Upload de PDFs/imagens por ticket
- [x] Download de anexos
- [x] Marcação de orçamento enviado + valor

### 6. SLAs e Alertas
- [x] Cálculo automático de SLAs na criação
- [x] Indicadores visuais (verde/laranja/vermelho)
- [x] Sistema de alertas com resolução

### 7. Webhooks
- [x] WhatsApp: cria/atualiza tickets (reutiliza ticket aberto 48h)
- [x] Telegram: cria tickets internos

### 8. Administração
- [x] Gestão de utilizadores (CRUD)
- [x] Exportação CSV de tickets

## Utilizadores de Demonstração
- Admin: admin@pdpv.pt / admin123
- Supervisor: supervisor@pdpv.pt / super123
- Agente: agente@pdpv.pt / agente123
- Financeiro: financeiro@pdpv.pt / fin123

## Próximas Ações (P1)
1. Integração real com serviço de email (Resend/SendGrid)
2. Jobs em background para verificação de SLAs
3. Notificações em tempo real (WebSockets)
4. Dashboard Kanban alternativo
5. Integração WhatsApp real (API Business)

## Data de Implementação
- MVP: 10/02/2026
