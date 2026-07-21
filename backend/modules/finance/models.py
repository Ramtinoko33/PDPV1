"""
CRM Finance Module - Pydantic Models & Enums
Gestão operacional de cobranças baseada em dados importados do GENES/ERP
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import date, datetime


# ============== ENUMS ==============

class FinanceRole(str, Enum):
    """Roles específicos do módulo financeiro"""
    OWNER = "OWNER"
    FINANCE_REVIEWER = "FINANCE_REVIEWER"
    COLLECTIONS_AGENT = "COLLECTIONS_AGENT"


class FinancialStatus(str, Enum):
    """Estados financeiros do cliente"""
    OK = "OK"
    EM_COBRANCA = "EM_COBRANCA"
    PROMESSA_ATIVA = "PROMESSA_ATIVA"
    PROMESSA_FALHADA = "PROMESSA_FALHADA"
    EM_DISPUTA = "EM_DISPUTA"
    REGULARIZACAO_TECNICA = "REGULARIZACAO_TECNICA"
    BLOQUEIO_SUGERIDO = "BLOQUEIO_SUGERIDO"
    BLOQUEADO = "BLOQUEADO"


class TrafficLight(str, Enum):
    """Semáforo financeiro"""
    GREEN = "GREEN"      # Sem vencidos relevantes
    YELLOW = "YELLOW"    # Vencido até 30 dias ou risco baixo
    ORANGE = "ORANGE"    # 31-60 dias ou índice elevado
    RED = "RED"          # +60 dias, promessa falhada, valor relevante
    CRITICAL = "CRITICAL"  # +90 dias, bloqueio, acima limite crédito


class ImportType(str, Enum):
    """Tipos de importação"""
    OVERDUE_BALANCES = "overdue_balances"      # Saldos vencidos diário
    OPEN_DOCUMENTS = "open_documents"          # Mapa documentos em aberto
    CLIENT_INFO = "client_info"                # InfoClientes semanal
    CREDIT_EVOLUTION = "credit_evolution"      # Evolução trimestral (futuro)


class ImportStatus(str, Enum):
    """Estados da importação"""
    RECEIVED = "received"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    ACCEPTED_WITH_WARNINGS = "accepted_with_warnings"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    OUTDATED = "outdated"
    PENDING_APPROVAL = "pending_approval"
    IMPORTED = "imported"
    FAILED = "failed"


class ImportSourceMethod(str, Enum):
    """Origem do ficheiro"""
    MANUAL_UPLOAD = "manual_upload"
    RPA_FOLDER = "rpa_folder"


class DocumentClassification(str, Enum):
    """Classificação de documentos"""
    COLLECTABLE = "collectable"           # Cobrável normal
    RESIDUAL = "residual"                 # Saldo residual (<= 1€)
    RESIDUAL_ACCUMULATED = "residual_accumulated"  # Residual acumulado (> 5€ total)
    MICRO_OLD = "micro_old"               # Micro-saldo antigo (<= 5€ e > 365 dias vencidos)
    CREDIT = "credit"                     # Nota de crédito
    DISPUTE = "dispute"                   # Em disputa
    PAYMENT_PLAN = "payment_plan"         # Em plano de pagamento
    RESOLVED_OPERATIONALLY = "resolved_operationally"  # Marcado como resolvido operacionalmente
    UNKNOWN = "unknown"


class DocumentActionType(str, Enum):
    """Ações aplicáveis a documentos residuais/micro-old/em disputa"""
    MARK_COLLECTABLE = "mark_collectable"                   # Forçar cobrança normal
    MARK_DISPUTE = "mark_dispute"                           # Marcar como em disputa
    MARK_RESOLVED_OPERATIONALLY = "mark_resolved_operationally"  # Sem cobrança, sem regularização
    REGULARIZE_INTERNALLY = "regularize_internally"         # Pedir regularização à contabilidade
    KEEP_IN_COLLECTIONS = "keep_in_collections"             # Reverter marcação e voltar a cobrar
    RESET = "reset"                                         # Limpar overrides manuais


class ActionType(str, Enum):
    """Tipos de ação/contacto"""
    PHONE_CALL = "phone_call"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    NOTE = "note"
    PROMISE_CREATED = "promise_created"
    PROMISE_UPDATED = "promise_updated"
    DISPUTE_MARKED = "dispute_marked"
    PAYMENT_PLAN_MARKED = "payment_plan_marked"
    BLOCK_SUGGESTED = "block_suggested"
    BLOCK_APPROVED = "block_approved"
    BLOCK_REJECTED = "block_rejected"
    UNBLOCKED = "unblocked"
    INTERNAL_REGULARIZATION = "internal_regularization"


class DelayReason(str, Enum):
    """Motivos de atraso"""
    ESQUECIMENTO = "esquecimento"
    PROCESSO_ADMINISTRATIVO = "processo_administrativo"
    FALTA_DOCUMENTO = "falta_documento"
    DISPUTA = "disputa"
    FALTA_LIQUIDEZ = "falta_liquidez"
    CLIENTE_DIFICIL = "cliente_dificil"
    ACORDO_EM_CURSO = "acordo_em_curso"
    ERRO_INTERNO = "erro_interno"
    SALDO_RESIDUAL = "saldo_residual"
    OUTRO = "outro"


class PromiseStatus(str, Enum):
    """Estados de promessa de pagamento"""
    OPEN = "open"
    FULFILLED = "fulfilled"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BlockRequestStatus(str, Enum):
    """Estados de pedido de bloqueio"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DataHealthStatus(str, Enum):
    """Estado de saúde dos dados"""
    OK = "ok"
    WARNING = "warning"
    BLOCKING = "blocking"


# ============== REQUEST/RESPONSE MODELS ==============

# --- Finance Client ---
class CustomerSegment(str, Enum):
    """Segmento comercial do cliente (usado para régua de cobrança e filtros)."""
    PARTICULAR = "PARTICULAR"
    EMPRESA = "EMPRESA"
    FROTA = "FROTA"
    SEGURADORA = "SEGURADORA"
    LEASING = "LEASING"
    CONTA_CORRENTE = "CONTA_CORRENTE"
    OUTRO = "OUTRO"
    UNKNOWN = "UNKNOWN"


class FinanceClientBase(BaseModel):
    """Base para cliente financeiro"""
    genes_code: str
    genes_account: Optional[str] = None
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    locality: Optional[str] = None
    region: Optional[str] = None
    # Segmento comercial (backfilled do módulo Customer via linked_customer_id)
    customer_segment: CustomerSegment = CustomerSegment.UNKNOWN
    # Contactos financeiros dedicados (sobrepõem-se aos genéricos para envios do Finance)
    finance_email: Optional[str] = None
    finance_phone: Optional[str] = None
    finance_mobile: Optional[str] = None
    finance_contact_name: Optional[str] = None
    # Auditoria da última edição manual de contactos financeiros
    finance_contacts_updated_at: Optional[str] = None
    finance_contacts_updated_by: Optional[str] = None


class FinanceClientCreate(FinanceClientBase):
    """Criar cliente financeiro (via importação)"""
    pass


class FinanceClientResponse(FinanceClientBase):
    """Resposta de cliente financeiro"""
    id: str
    linked_customer_id: Optional[str] = None
    
    # Dados financeiros atuais
    total_balance: float = 0.0
    overdue_balance_accounting: float = 0.0
    overdue_balance_collectable: float = 0.0
    residual_balance: float = 0.0
    oldest_overdue_days: int = 0
    collection_index: float = 0.0
    
    # Enriquecimento InfoClientes
    credit_limit: Optional[float] = None
    risk_value: Optional[float] = None
    insured_risk_value: Optional[float] = None
    risk_percentage: Optional[float] = None
    annual_revenue: Optional[float] = None
    payment_terms: Optional[str] = None
    portfolio: Optional[float] = None  # Carteira
    pending_delivery: Optional[float] = None  # Albaranado
    
    # Estado operacional
    financial_status: FinancialStatus = FinancialStatus.OK
    traffic_light: TrafficLight = TrafficLight.GREEN
    is_residual_only: bool = False
    is_blocked: bool = False
    block_reason: Optional[str] = None
    
    # Controlo
    last_import_id: Optional[str] = None
    last_action_at: Optional[str] = None
    next_action_date: Optional[str] = None
    created_at: str
    updated_at: str
    
    # Evolução crédito trimestral (join com finance_credit_evolution)
    credit_evolution: Optional[Dict[str, float]] = None
    credit_trend_percentage: Optional[float] = None
    credit_trend_absolute: Optional[float] = None


class FinanceClientListResponse(BaseModel):
    """Lista de clientes financeiros"""
    clients: List[FinanceClientResponse]
    total: int
    page: int
    page_size: int


# --- Finance Document ---
class FinanceDocumentResponse(BaseModel):
    """Documento financeiro"""
    id: str
    client_id: str
    document_type: str  # FT, NC, etc.
    document_number: str
    description: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    amount_original: Optional[float] = None
    amount_open: float
    amount_overdue: float = 0.0
    days_overdue: int = 0
    classification: DocumentClassification
    effective_classification: Optional[DocumentClassification] = None
    manually_marked_collectable: bool = False
    manual_action: Optional[str] = None
    manual_action_reason: Optional[str] = None
    manual_action_by: Optional[str] = None
    manual_action_at: Optional[str] = None
    last_import_id: str
    created_at: str
    updated_at: str


# --- Finance Import ---
class ImportTotals(BaseModel):
    """Totais agregados de importação"""
    clients: int = 0
    documents: int = 0
    total_balance: float = 0.0
    total_overdue: float = 0.0
    total_collectable: float = 0.0
    total_residual: float = 0.0


class FinanceImportResponse(BaseModel):
    """Resposta de importação"""
    id: str
    type: ImportType
    source_method: ImportSourceMethod
    filename: str
    file_hash: str
    as_of_date: Optional[str] = None
    uploaded_by: str
    uploaded_by_name: Optional[str] = None
    uploaded_at: str
    status: ImportStatus
    totals: ImportTotals
    warnings: List[str] = []
    errors: List[str] = []
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


class FinanceImportListResponse(BaseModel):
    """Lista de importações (paginada)"""
    imports: List[FinanceImportResponse]
    total: int
    limit: int = 50
    offset: int = 0
    has_more: bool = False


# --- Finance Action ---
class FinanceActionCreate(BaseModel):
    """Criar ação/contacto"""
    action_type: ActionType
    notes: Optional[str] = None
    delay_reason: Optional[DelayReason] = None
    next_action_date: Optional[str] = None


class FinanceActionResponse(BaseModel):
    """Resposta de ação"""
    id: str
    client_id: str
    action_type: ActionType
    user_id: str
    user_name: str
    notes: Optional[str] = None
    delay_reason: Optional[DelayReason] = None
    next_action_date: Optional[str] = None
    created_at: str


# --- Finance Promise ---
class FinancePromiseCreate(BaseModel):
    """Criar promessa de pagamento"""
    amount: float
    promise_date: str  # YYYY-MM-DD
    notes: Optional[str] = None
    linked_document_ids: List[str] = []


class FinancePromiseUpdate(BaseModel):
    """Atualizar promessa"""
    status: Optional[PromiseStatus] = None
    notes: Optional[str] = None


class FinancePromiseResponse(BaseModel):
    """Resposta de promessa"""
    id: str
    client_id: str
    client_name: Optional[str] = None
    genes_code: Optional[str] = None
    amount: float
    promise_date: str
    status: PromiseStatus
    notes: Optional[str] = None
    linked_document_ids: List[str] = []
    created_by: str
    created_by_name: str
    created_at: str
    verified_at: Optional[str] = None
    verified_import_id: Optional[str] = None
    verification_note: Optional[str] = None


# --- Block Request ---
class BlockRequestCreate(BaseModel):
    """Sugerir bloqueio"""
    reason: str


class BlockRequestReview(BaseModel):
    """Aprovar/Rejeitar bloqueio"""
    approved: bool
    review_notes: Optional[str] = None


class BlockRequestResponse(BaseModel):
    """Resposta de pedido de bloqueio"""
    id: str
    client_id: str
    client_name: str
    suggested_by: str
    suggested_by_name: str
    suggested_at: str
    reason: str
    status: BlockRequestStatus
    reviewed_by: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: Optional[str] = None


# --- Data Health ---
class DataHealthResponse(BaseModel):
    """Estado de saúde dos dados"""
    source_type: ImportType
    required_frequency: str  # daily, weekly
    last_import_id: Optional[str] = None
    last_import_at: Optional[str] = None
    last_as_of_date: Optional[str] = None
    status: DataHealthStatus
    is_blocking_operations: bool
    message: Optional[str] = None


class DataHealthListResponse(BaseModel):
    """Lista de estados de saúde"""
    items: List[DataHealthResponse]
    any_blocking: bool


# --- Dashboard ---
class AgingBucket(BaseModel):
    """Bucket de aging"""
    range_label: str  # "0-30", "31-60", "61-90", "+90"
    client_count: int
    total_amount: float


class TopDebtor(BaseModel):
    """Top devedor"""
    client_id: str
    client_name: str
    genes_code: str
    overdue_amount: float
    oldest_days: int
    traffic_light: TrafficLight


class DashboardResponse(BaseModel):
    """Dashboard financeiro"""
    # Totais
    total_balance: float
    total_overdue_accounting: float
    total_overdue_collectable: float
    total_residual: float
    
    # Contagens
    clients_with_overdue: int
    clients_blocked: int
    promises_active: int
    promises_failed: int
    
    # Aging
    aging_buckets: List[AgingBucket]
    
    # Top devedores
    top_debtors: List[TopDebtor]
    
    # Última atualização
    last_import_at: Optional[str] = None
    data_is_current: bool
    
    # Valor recuperado (comparação diária de documentos em aberto)
    recovered_today: float = 0.0
    recovered_week: float = 0.0
    recovered_month: float = 0.0


# --- Collections Today ---
class CollectionItem(BaseModel):
    """Item de cobrança do dia"""
    client_id: str
    client_name: str
    genes_code: str
    total_balance: float
    overdue_collectable: float
    residual_balance: float
    oldest_overdue_days: int
    financial_status: FinancialStatus
    traffic_light: TrafficLight
    last_action_at: Optional[str] = None
    next_action_date: Optional[str] = None
    has_active_promise: bool
    has_failed_promise: bool
    priority_score: float  # Para ordenação


class CollectionsTodayResponse(BaseModel):
    """Cobranças do dia"""
    items: List[CollectionItem]
    total_items: int
    total_value: float
    is_blocked: bool  # Se dados desatualizados
    block_message: Optional[str] = None


# --- Regularizations ---
class RegularizationItem(BaseModel):
    """Item de regularização (por documento)"""
    # Documento
    document_id: str
    document_type: str
    document_number: str
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    amount_open: float
    days_overdue: int
    classification: DocumentClassification
    manual_action: Optional[str] = None

    # Cliente
    client_id: str
    client_name: str
    genes_code: str

    # Agregado do cliente
    client_residual_balance: float = 0.0
    client_residual_document_count: int = 0

    # Sugestão
    suggestion_code: str  # "ignore" | "review" | "request_regularization" | "validate_old_invoice"
    suggestion_label: str


class RegularizationsResponse(BaseModel):
    """Lista de regularizações (por documento)"""
    items: List[RegularizationItem]
    total_residual: float
    total_documents: int
    total_clients: int


class DocumentActionCreate(BaseModel):
    """Acção manual sobre um documento (residual/micro-old/disputa/resolvido)"""
    action: DocumentActionType
    reason: Optional[str] = None

# --- Configurações do módulo ---
class FinanceSettingsUpdate(BaseModel):
    """Atualização das configurações do módulo Finance"""
    residual_document_threshold: Optional[float] = Field(None, ge=0, le=1000)
    residual_client_threshold: Optional[float] = Field(None, ge=0, le=10000)
    residual_percentage_threshold: Optional[float] = Field(None, ge=0, le=1)
    residual_max_documents: Optional[int] = Field(None, ge=1, le=1000)
    micro_old_days_threshold: Optional[int] = Field(None, ge=30, le=3650)
    show_credit_warning_on_tickets: Optional[bool] = None


class FinanceClientContactsUpdate(BaseModel):
    """Atualização de contactos financeiros + segmento do cliente."""
    customer_segment: Optional[CustomerSegment] = None
    finance_email: Optional[str] = Field(None, max_length=200)
    finance_phone: Optional[str] = Field(None, max_length=40)
    finance_mobile: Optional[str] = Field(None, max_length=40)
    finance_contact_name: Optional[str] = Field(None, max_length=200)
    reason: Optional[str] = Field(None, max_length=500)


# --- Email templates (BD-backed) ---
class EmailTemplateBase(BaseModel):
    """Template de email para comunicação manual do Finance."""
    key: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    label: str = Field(..., min_length=1, max_length=120)
    bucket_hint: Optional[str] = Field(
        None,
        description="Bucket sugerido da régua (d0_15/d16_30/d31_60/d61_90/d90p/d120p/promise/dispute/generic)",
    )
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=8000)
    whatsapp_body: Optional[str] = Field(None, max_length=4000)
    is_active: bool = True


class EmailTemplateCreate(EmailTemplateBase):
    pass


class EmailTemplateUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=120)
    bucket_hint: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    whatsapp_body: Optional[str] = None
    is_active: Optional[bool] = None


class EmailTemplateResponse(EmailTemplateBase):
    id: str
    created_by: Optional[str] = None
    created_at: str
    updated_at: str


class EmailTemplateListResponse(BaseModel):
    templates: List[EmailTemplateResponse]
    total: int
