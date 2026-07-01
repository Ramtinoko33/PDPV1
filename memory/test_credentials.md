# Test Credentials - PDPV Tickets

## Admin Account
- **Email:** admin@pdpv.pt
- **Password:** HCNMEnKMLq
- **Role:** ADMIN
- **Finance Role:** OWNER (acesso completo ao CRM Finance)

## Test Accounts
- **Rececionista:** rececionista@pdpv.pt
  - Finance Role: null (sem acesso ao CRM Finance)

## Finance Module Access
Para aceder ao módulo CRM Finance, o utilizador precisa de ter `finance_role` atribuído:
- OWNER: Acesso total, pode aprovar bloqueios
- FINANCE_REVIEWER: Pode ver e criar ações
- COLLECTIONS_AGENT: Pode registar contactos

## API Test Token
Para testes de API, usar login:
```bash
TOKEN=$(curl -s -X POST "https://pdpv-whatsapp.preview.emergentagent.com/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pdpv.pt","password":"HCNMEnKMLq"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")
```
