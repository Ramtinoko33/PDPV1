# PDPV Tickets - Product Requirements Document

## Problema Original
Sistema de gestão de pedidos para oficina automóvel (PDPV Tickets) com UI em português. Sistema de ticketing com controlo de acesso baseado em funções (RBAC), tracking de SLA, webhooks para WhatsApp/Telegram, e gestão de ficheiros.

## Arquitetura

### Backend (FastAPI + MongoDB)
- **Autenticação**: JWT com tokens de 24h
- **Base de Dados**: MongoDB com coleções para users, tickets, messages, notes, alerts, attachments, customers, notifications
- **APIs**: Todas com prefixo /api
- **Ficheiros**: Armazenamento local em /app/backend/uploads
- **WebSockets**: Notificações em tempo real
- **Health Check**: GET /health e GET /api/health

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

### 9. Gestão de Clientes e Veículos
- [x] Importação de dados de Excel (clientes e matrículas)
- [x] Auto-preenchimento na criação de tickets (por telefone ou matrícula)
- [x] Seleção de múltiplos contactos/veículos por cliente
- [x] Visualização do histórico completo do cliente

### 10. Notificações em Tempo Real
- [x] WebSocket para notificações push
- [x] Centro de notificações no cabeçalho
- [x] Marcação como lida (individual e todas)
- [x] Notificações para supervisores em novos tickets

### 11. Web Push Notifications
- [x] Service Worker registado em /sw.js
- [x] Chaves VAPID configuradas no backend
- [x] Endpoint GET /api/push/vapid-public-key
- [x] Endpoint POST /api/push/subscribe 
- [x] Endpoint DELETE /api/push/unsubscribe
- [x] UI para ativar/desativar no NotificationCenter
- [x] Notificações aparecem no sistema operativo (Windows/Mac/Android)
- [x] Click na notificação abre o ticket correspondente

### 12. Deployment Ready
- [x] Endpoint /health para Kubernetes health checks
- [x] Compatibilidade bcrypt/passlib corrigida (bcrypt==4.0.1)

## Utilizadores de Demonstração
- Admin: admin@pdpv.pt / admin123
- Supervisor: supervisor@pdpv.pt / super123
- Agente: agente@pdpv.pt / agente123
- Financeiro: financeiro@pdpv.pt / fin123

## Próximas Ações
### P1 - Prioridade Alta
1. Integração WhatsApp real (Twilio/API Business)

### P2 - Prioridade Média
2. Integração real com serviço de email (Resend/SendGrid)
3. Dashboard Kanban alternativo

### P3 - Backlog
4. Funcionalidades específicas para papel "Financeiro"
5. Jobs em background para verificação de SLAs
6. Refactoring do backend (modularizar server.py)

## Correções de Deployment (12/02/2026)
- Corrigido conflito bcrypt/passlib: bcrypt==4.0.1
- Adicionado endpoint GET /health para container orchestration

## Data de Implementação
- MVP: 10/02/2026
- Correções Deployment: 12/02/2026
