"""
Finance Import Service
Serviço de importação e processamento de ficheiros financeiros
"""
import logging
import uuid
import hashlib
from datetime import datetime, timezone, date, timedelta
from typing import Dict, Any, Optional, List, Tuple

from db import db
from ..models import (
    ImportType, ImportStatus, ImportSourceMethod,
    FinancialStatus, TrafficLight, DocumentClassification,
)
from ..parsers import (
    parse_overdue_balances,
    parse_open_documents,
    parse_client_info,
    parse_credit_evolution,
)

logger = logging.getLogger(__name__)

# Configurações default do módulo (podem ser alteradas em finance_settings)
DEFAULT_SETTINGS = {
    'residual_document_threshold': 1.00,      # até 1€ por documento
    'residual_client_threshold': 5.00,        # até 5€ acumulado por cliente
    'residual_percentage_threshold': 0.005,   # até 0.5% do valor original (deprecated)
    'residual_max_documents': 10,             # máximo de documentos residuais por cliente
    'micro_old_days_threshold': 365,          # dias vencidos p/ considerar micro-saldo antigo
    'show_credit_warning_on_tickets': True,   # aviso genérico nos tickets
}


async def get_finance_settings() -> Dict[str, Any]:
    """Carrega configurações do módulo (BD com fallback para defaults)."""
    doc = await db.finance_settings.find_one({"id": "global"}, {"_id": 0}) or {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k in DEFAULT_SETTINGS and v is not None}}

# Limites de diferença para aprovação automática
DIFF_THRESHOLDS = {
    'auto_accept': 0.10,      # até 10% - aceita automaticamente
    'accept_warning': 0.30,   # até 30% - aceita com aviso
    # acima de 30% - precisa aprovação
}


def calculate_traffic_light(
    oldest_overdue_days: int,
    overdue_collectable: float,
    total_balance: float,
    has_failed_promise: bool = False,
    is_blocked: bool = False,
    financial_status: str = None
) -> TrafficLight:
    """
    Calcula o semáforo financeiro do cliente.
    """
    # Crítico
    if is_blocked:
        return TrafficLight.CRITICAL
    if financial_status == FinancialStatus.BLOQUEIO_SUGERIDO.value:
        return TrafficLight.CRITICAL
    if oldest_overdue_days > 90:
        return TrafficLight.CRITICAL
    if has_failed_promise:
        return TrafficLight.CRITICAL
    
    # Vermelho
    if oldest_overdue_days > 60:
        return TrafficLight.RED
    if overdue_collectable > 5000 and oldest_overdue_days > 30:
        return TrafficLight.RED
    
    # Laranja
    if oldest_overdue_days > 30:
        return TrafficLight.ORANGE
    if total_balance > 0:
        collection_index = (overdue_collectable / total_balance) * 100 if total_balance > 0 else 0
        if collection_index > 30:
            return TrafficLight.ORANGE
    
    # Amarelo
    if oldest_overdue_days > 0:
        return TrafficLight.YELLOW
    if overdue_collectable > 0:
        return TrafficLight.YELLOW
    
    # Verde
    return TrafficLight.GREEN


def calculate_financial_status(
    overdue_collectable: float,
    residual_balance: float,
    is_residual_only: bool,
    is_blocked: bool,
    has_active_promise: bool = False,
    has_failed_promise: bool = False,
    in_dispute: bool = False,
    block_suggested: bool = False
) -> FinancialStatus:
    """
    Calcula o estado financeiro do cliente.
    """
    if is_blocked:
        return FinancialStatus.BLOQUEADO
    if block_suggested:
        return FinancialStatus.BLOQUEIO_SUGERIDO
    if in_dispute:
        return FinancialStatus.EM_DISPUTA
    if has_failed_promise:
        return FinancialStatus.PROMESSA_FALHADA
    if has_active_promise:
        return FinancialStatus.PROMESSA_ATIVA
    if is_residual_only:
        return FinancialStatus.REGULARIZACAO_TECNICA
    if overdue_collectable > 0:
        return FinancialStatus.EM_COBRANCA
    return FinancialStatus.OK


def classify_document(
    amount_open: float,
    amount_original: Optional[float],
    is_credit_note: bool,
    days_overdue: int = 0,
    in_dispute: bool = False,
    in_payment_plan: bool = False,
    config: Optional[Dict[str, Any]] = None
) -> DocumentClassification:
    """
    Classifica um documento (cobrável, residual, micro-old, crédito, etc.)

    Regras (por ordem de precedência):
      1) Nota de crédito / valor negativo -> CREDIT
      2) Em disputa -> DISPUTE
      3) Em plano de pagamento -> PAYMENT_PLAN
      4) amount_open <= 0 -> COLLECTABLE (nada em aberto)
      5) amount_open <= residual_document_threshold (default 1€) -> RESIDUAL
         (sempre, independentemente da % do valor original — evita micro-saldos
         de €0.80 sobre faturas grandes ficarem como cobráveis)
      6) amount_open <= residual_client_threshold (default 5€) E
         days_overdue > 365 -> MICRO_OLD
         (micro-saldo antigo — provável desactualização contabilística)
      7) Caso contrário -> COLLECTABLE
    """
    cfg = config or DEFAULT_SETTINGS

    if is_credit_note or (amount_open is not None and amount_open < 0):
        return DocumentClassification.CREDIT

    if in_dispute:
        return DocumentClassification.DISPUTE

    if in_payment_plan:
        return DocumentClassification.PAYMENT_PLAN

    if amount_open is None or amount_open <= 0:
        return DocumentClassification.COLLECTABLE

    residual_doc_threshold = cfg.get('residual_document_threshold', 1.00)
    micro_old_threshold = cfg.get('residual_client_threshold', 5.00)
    micro_old_days = cfg.get('micro_old_days_threshold', 365)

    # Regra 5 — residual absoluto (independente de %)
    if amount_open <= residual_doc_threshold:
        return DocumentClassification.RESIDUAL

    # Regra 6 — micro-saldo antigo
    if amount_open <= micro_old_threshold and days_overdue > micro_old_days:
        return DocumentClassification.MICRO_OLD

    return DocumentClassification.COLLECTABLE


async def process_overdue_balances_import(
    import_id: str,
    file_content: bytes,
    uploaded_by: str,
    as_of_date: Optional[str] = None,
    force_approved: bool = False
) -> Dict[str, Any]:
    """
    Processa importação de saldos vencidos.
    Este é o ficheiro principal diário.
    """
    result = {
        'success': False,
        'import_id': import_id,
        'status': ImportStatus.VALIDATING.value,
        'totals': {},
        'warnings': [],
        'errors': []
    }
    
    try:
        # Parse do ficheiro
        parsed = parse_overdue_balances(file_content)
        
        if parsed['errors']:
            result['errors'].extend(parsed['errors'])
            result['status'] = ImportStatus.REJECTED.value
            await db.finance_imports.update_one(
                {"id": import_id},
                {"$set": {"status": result['status'], "errors": result['errors']}}
            )
            return result
        
        result['warnings'].extend(parsed['warnings'])
        
        now = datetime.now(timezone.utc).isoformat()
        today = date.today().isoformat()
        
        # Verificar diferença com última importação
        last_import = await db.finance_imports.find_one(
            {"type": ImportType.OVERDUE_BALANCES.value, "status": ImportStatus.IMPORTED.value},
            sort=[("uploaded_at", -1)]
        )
        
        needs_approval = False
        if not force_approved and last_import and last_import.get('totals', {}).get('total_overdue', 0) > 0:
            last_total = last_import['totals']['total_overdue']
            current_total = parsed['totals']['total_overdue']
            diff_pct = abs(current_total - last_total) / last_total if last_total > 0 else 0
            
            if diff_pct > DIFF_THRESHOLDS['accept_warning']:
                needs_approval = True
                result['warnings'].append(f"Diferença de {diff_pct*100:.1f}% face à última importação. Requer aprovação.")
            elif diff_pct > DIFF_THRESHOLDS['auto_accept']:
                result['warnings'].append(f"Diferença de {diff_pct*100:.1f}% face à última importação.")
        
        # Diferença anormal: NÃO aplicar dados — aguardar aprovação de FINANCE_REVIEWER/OWNER
        if needs_approval:
            result['status'] = ImportStatus.PENDING_APPROVAL.value
            result['totals'] = {
                "clients": parsed['totals']['client_count'],
                "documents": parsed['totals']['document_count'],
                "total_balance": parsed['totals']['total_balance'],
                "total_overdue": parsed['totals']['total_overdue'],
            }
            result['message'] = "Importação requer aprovação antes de os dados serem aplicados."
            await db.finance_imports.update_one(
                {"id": import_id},
                {"$set": {
                    "status": result['status'],
                    "totals": result['totals'],
                    "warnings": result['warnings'],
                }}
            )
            logger.info(f"Import {import_id} pending approval ({result['warnings']})")
            return result
        
        # Processar clientes e documentos
        cfg = await get_finance_settings()
        clients_created = 0
        clients_updated = 0
        documents_processed = 0
        
        for client_data in parsed['clients']:
            genes_code = client_data['genes_code']
            
            # Buscar cliente existente
            existing_client = await db.finance_clients.find_one({"genes_code": genes_code})
            
            # Processar documentos do cliente
            total_residual = 0.0
            residual_doc_count = 0
            overdue_collectable = 0.0
            oldest_overdue_days = 0
            
            for doc in client_data.get('documents', []):
                amount_open = doc.get('amount_overdue', 0)
                amount_original = doc.get('amount_due')
                is_credit = doc.get('document_type') == 'NC' or amount_open < 0
                days_overdue = doc.get('days_overdue', 0)

                classification = classify_document(
                    amount_open=amount_open,
                    amount_original=amount_original,
                    is_credit_note=is_credit,
                    days_overdue=days_overdue,
                    config=cfg,
                )

                # Preservar override manual em documento existente
                doc_id = f"{genes_code}_{doc['document_number']}"
                existing_doc = await db.finance_documents.find_one({"id": doc_id}, {
                    "_id": 0,
                    "manually_marked_collectable": 1,
                    "manual_action": 1,
                    "manual_action_reason": 1,
                    "manual_action_by": 1,
                    "manual_action_at": 1,
                }) or {}
                manually_marked_collectable = bool(existing_doc.get("manually_marked_collectable", False))
                manual_action = existing_doc.get("manual_action")

                # Classificação efectiva (o que decide se entra em cobrança)
                effective = classification
                if manually_marked_collectable:
                    effective = DocumentClassification.COLLECTABLE
                elif manual_action == "mark_dispute":
                    effective = DocumentClassification.DISPUTE
                elif manual_action == "mark_resolved_operationally":
                    effective = DocumentClassification.RESOLVED_OPERATIONALLY
                elif manual_action == "regularize_internally":
                    # continua a contar como residual/micro-old, apenas com flag
                    pass

                # Agregação
                if effective == DocumentClassification.COLLECTABLE:
                    if amount_open > 0:
                        overdue_collectable += amount_open
                        if days_overdue > oldest_overdue_days:
                            oldest_overdue_days = days_overdue
                elif effective in (
                    DocumentClassification.RESIDUAL,
                    DocumentClassification.MICRO_OLD,
                ):
                    total_residual += amount_open
                    residual_doc_count += 1
                # DISPUTE / RESOLVED_OPERATIONALLY / CREDIT / PAYMENT_PLAN: não somam a nenhum bucket operacional

                doc_record = {
                    "id": doc_id,
                    "client_id": existing_client['id'] if existing_client else None,
                    "genes_code": genes_code,
                    "document_type": doc.get('document_type', 'FT'),
                    "document_number": doc['document_number'],
                    "invoice_date": doc.get('invoice_date'),
                    "due_date": doc.get('due_date'),
                    "amount_original": amount_original,
                    "amount_open": amount_open,
                    "amount_overdue": amount_open,
                    "days_overdue": days_overdue,
                    "classification": classification.value,
                    "effective_classification": effective.value,
                    "manually_marked_collectable": manually_marked_collectable,
                    "manual_action": manual_action,
                    "manual_action_reason": existing_doc.get("manual_action_reason"),
                    "manual_action_by": existing_doc.get("manual_action_by"),
                    "manual_action_at": existing_doc.get("manual_action_at"),
                    "last_import_id": import_id,
                    "updated_at": now
                }

                await db.finance_documents.update_one(
                    {"id": doc_id},
                    {"$set": doc_record, "$setOnInsert": {"created_at": now}},
                    upsert=True
                )
                documents_processed += 1
            
            # Verificar residual acumulado
            is_residual_only = (overdue_collectable <= 0 and total_residual > 0)
            if total_residual > cfg['residual_client_threshold'] or residual_doc_count > cfg['residual_max_documents']:
                # Residual acumulado - precisa revisão
                result['warnings'].append(f"Cliente {genes_code} com residual acumulado: {total_residual:.2f}€ em {residual_doc_count} docs")
            
            # Calcular índice de cobrança
            total_balance = client_data.get('total_balance', 0)
            collection_index = (overdue_collectable / total_balance * 100) if total_balance > 0 else 0
            
            # Manter estado atual se existir (bloqueio, disputa, etc.)
            current_status = existing_client.get('financial_status') if existing_client else None
            is_blocked = existing_client.get('is_blocked', False) if existing_client else False
            block_suggested = current_status == FinancialStatus.BLOQUEIO_SUGERIDO.value if current_status else False
            in_dispute = current_status == FinancialStatus.EM_DISPUTA.value if current_status else False
            
            # Verificar promessas
            has_active_promise = await db.finance_promises.count_documents({
                "client_id": existing_client['id'] if existing_client else None,
                "status": "open"
            }) > 0 if existing_client else False
            
            has_failed_promise = await db.finance_promises.count_documents({
                "client_id": existing_client['id'] if existing_client else None,
                "status": "failed"
            }) > 0 if existing_client else False
            
            # Calcular estado e semáforo
            financial_status = calculate_financial_status(
                overdue_collectable=overdue_collectable,
                residual_balance=total_residual,
                is_residual_only=is_residual_only,
                is_blocked=is_blocked,
                has_active_promise=has_active_promise,
                has_failed_promise=has_failed_promise,
                in_dispute=in_dispute,
                block_suggested=block_suggested
            )
            
            traffic_light = calculate_traffic_light(
                oldest_overdue_days=oldest_overdue_days,
                overdue_collectable=overdue_collectable,
                total_balance=total_balance,
                has_failed_promise=has_failed_promise,
                is_blocked=is_blocked,
                financial_status=financial_status.value
            )
            
            # Criar/atualizar cliente
            client_id = existing_client['id'] if existing_client else str(uuid.uuid4())
            
            client_record = {
                "id": client_id,
                "genes_code": genes_code,
                "name": client_data['name'],
                "email": client_data.get('email'),
                "phone": client_data.get('phone'),
                "mobile": client_data.get('mobile'),
                "locality": client_data.get('locality'),
                "region": client_data.get('region'),
                "total_balance": total_balance,
                "overdue_balance_accounting": client_data.get('total_overdue', 0),
                "overdue_balance_collectable": overdue_collectable,
                "residual_balance": total_residual,
                "oldest_overdue_days": oldest_overdue_days,
                "collection_index": round(collection_index, 2),
                "financial_status": financial_status.value,
                "traffic_light": traffic_light.value,
                "is_residual_only": is_residual_only,
                "is_blocked": is_blocked,
                "last_import_id": import_id,
                "updated_at": now
            }
            
            # Preservar campos existentes
            if existing_client:
                for field in ['linked_customer_id', 'credit_limit', 'risk_value', 'insured_risk_value', 
                              'risk_percentage', 'annual_revenue', 'payment_terms', 'portfolio',
                              'pending_delivery', 'genes_account', 'block_reason', 
                              'last_action_at', 'next_action_date']:
                    if existing_client.get(field):
                        client_record[field] = existing_client[field]
            
            await db.finance_clients.update_one(
                {"genes_code": genes_code},
                {"$set": client_record, "$setOnInsert": {"created_at": now}},
                upsert=True
            )
            
            # Atualizar client_id nos documentos
            await db.finance_documents.update_many(
                {"genes_code": genes_code, "client_id": None},
                {"$set": {"client_id": client_id}}
            )
            
            if existing_client:
                clients_updated += 1
            else:
                clients_created += 1
            
            # Guardar métrica diária
            daily_metric = {
                "client_id": client_id,
                "import_id": import_id,
                "date": as_of_date or today,
                "total_balance": total_balance,
                "overdue_balance_accounting": client_data.get('total_overdue', 0),
                "overdue_balance_collectable": overdue_collectable,
                "residual_balance": total_residual,
                "oldest_overdue_days": oldest_overdue_days,
                "collection_index": round(collection_index, 2),
                "financial_status": financial_status.value,
                "traffic_light": traffic_light.value,
            }
            
            await db.finance_client_daily_metrics.update_one(
                {"client_id": client_id, "date": daily_metric["date"]},
                {"$set": daily_metric},
                upsert=True
            )
        
        # Remover documentos que não vieram nesta importação (foram pagos)
        # Opcional: marcar como pagos em vez de apagar
        
        # Verificar promessas vencidas contra a nova importação
        promises_verified = await verify_promises_after_import(import_id, as_of_date or today)
        if promises_verified:
            result['promises_verified'] = promises_verified
        
        # Atualizar totais da importação
        totals = {
            "clients": parsed['totals']['client_count'],
            "documents": documents_processed,
            "total_balance": parsed['totals']['total_balance'],
            "total_overdue": parsed['totals']['total_overdue'],
            "total_collectable": sum(c.get('overdue_balance_collectable', 0) for c in parsed['clients']),
            "total_residual": sum(c.get('residual_balance', 0) for c in parsed['clients']),
            "clients_created": clients_created,
            "clients_updated": clients_updated,
        }
        
        result['totals'] = totals
        
        # Determinar estado final
        if result['warnings']:
            result['status'] = ImportStatus.ACCEPTED_WITH_WARNINGS.value
        else:
            result['status'] = ImportStatus.IMPORTED.value
        
        result['success'] = result['status'] in [
            ImportStatus.IMPORTED.value,
            ImportStatus.ACCEPTED_WITH_WARNINGS.value
        ]
        
        # Atualizar importação
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {
                "status": result['status'],
                "totals": totals,
                "warnings": result['warnings'],
                "errors": result['errors'],
                "as_of_date": as_of_date or today,
                "processed_at": now
            }}
        )
        
        # Atualizar data_health
        await db.finance_data_health.update_one(
            {"source_type": ImportType.OVERDUE_BALANCES.value},
            {"$set": {
                "source_type": ImportType.OVERDUE_BALANCES.value,
                "required_frequency": "daily",
                "last_import_id": import_id,
                "last_import_at": now,
                "last_as_of_date": as_of_date or today,
                "status": "ok" if result['success'] else "warning",
                "is_blocking_operations": not result['success']
            }},
            upsert=True
        )
        
        logger.info(f"Processed overdue balances import {import_id}: {clients_created} created, {clients_updated} updated, {documents_processed} documents")
        
    except Exception as e:
        logger.error(f"Error processing overdue balances import: {e}")
        result['errors'].append(f"Erro ao processar importação: {str(e)}")
        result['status'] = ImportStatus.FAILED.value
        
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {"status": result['status'], "errors": result['errors']}}
        )
    
    return result


async def process_client_info_import(
    import_id: str,
    file_content: bytes,
    uploaded_by: str
) -> Dict[str, Any]:
    """
    Processa importação de InfoClientes (enriquecimento semanal).
    """
    result = {
        'success': False,
        'import_id': import_id,
        'status': ImportStatus.VALIDATING.value,
        'totals': {},
        'warnings': [],
        'errors': []
    }
    
    try:
        # Parse do ficheiro
        parsed = parse_client_info(file_content)
        
        if parsed['errors']:
            result['errors'].extend(parsed['errors'])
            result['status'] = ImportStatus.REJECTED.value
            await db.finance_imports.update_one(
                {"id": import_id},
                {"$set": {"status": result['status'], "errors": result['errors']}}
            )
            return result
        
        result['warnings'].extend(parsed['warnings'])
        
        now = datetime.now(timezone.utc).isoformat()
        today = date.today().isoformat()
        
        clients_updated = 0
        clients_not_found = 0
        
        for client_data in parsed['clients']:
            genes_code = client_data['genes_code']
            
            # Buscar cliente existente
            existing = await db.finance_clients.find_one({"genes_code": genes_code})
            
            if not existing:
                clients_not_found += 1
                continue
            
            # Atualizar dados de enriquecimento
            update_data = {
                "genes_account": client_data.get('account'),
                "credit_limit": client_data.get('credit_limit'),  # Pode não existir
                "risk_value": client_data.get('risk_value'),
                "insured_risk_value": client_data.get('insured_risk_value'),
                "risk_percentage": client_data.get('risk_percentage'),
                "annual_revenue": client_data.get('annual_revenue'),
                "portfolio": client_data.get('portfolio'),
                "pending_delivery": client_data.get('pending_delivery'),
                "updated_at": now
            }
            
            # Remover None values
            update_data = {k: v for k, v in update_data.items() if v is not None}
            
            await db.finance_clients.update_one(
                {"genes_code": genes_code},
                {"$set": update_data}
            )
            clients_updated += 1
        
        if clients_not_found > 0:
            result['warnings'].append(f"{clients_not_found} clientes não encontrados (ainda não importados via saldos vencidos)")
        
        result['totals'] = {
            "clients": parsed['totals']['client_count'],
            "clients_updated": clients_updated,
            "clients_not_found": clients_not_found,
            "total_balance": parsed['totals']['total_balance'],
            "total_annual_revenue": parsed['totals']['total_annual_revenue'],
        }
        
        result['status'] = ImportStatus.IMPORTED.value
        result['success'] = True
        
        # Atualizar importação
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {
                "status": result['status'],
                "totals": result['totals'],
                "warnings": result['warnings'],
                "as_of_date": today,
                "processed_at": now
            }}
        )
        
        # Atualizar data_health
        await db.finance_data_health.update_one(
            {"source_type": ImportType.CLIENT_INFO.value},
            {"$set": {
                "source_type": ImportType.CLIENT_INFO.value,
                "required_frequency": "weekly",
                "last_import_id": import_id,
                "last_import_at": now,
                "last_as_of_date": today,
                "status": "ok",
                "is_blocking_operations": False
            }},
            upsert=True
        )
        
        logger.info(f"Processed client info import {import_id}: {clients_updated} updated")
        
    except Exception as e:
        logger.error(f"Error processing client info import: {e}")
        result['errors'].append(f"Erro ao processar importação: {str(e)}")
        result['status'] = ImportStatus.FAILED.value
        
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {"status": result['status'], "errors": result['errors']}}
        )
    
    return result


async def process_credit_evolution_import(
    import_id: str,
    file_content: bytes,
    uploaded_by: str
) -> Dict[str, Any]:
    """
    Processa importação de Evolução de Crédito Trimestral.
    Guarda a série trimestral por cliente em finance_credit_evolution
    e enriquece finance_clients com a tendência.
    """
    result = {
        'success': False,
        'import_id': import_id,
        'status': ImportStatus.VALIDATING.value,
        'totals': {},
        'warnings': [],
        'errors': []
    }
    
    try:
        parsed = parse_credit_evolution(file_content)
        
        if parsed['errors']:
            result['errors'].extend(parsed['errors'])
            result['status'] = ImportStatus.REJECTED.value
            await db.finance_imports.update_one(
                {"id": import_id},
                {"$set": {"status": result['status'], "errors": result['errors']}}
            )
            return result
        
        result['warnings'].extend(parsed['warnings'])
        
        now = datetime.now(timezone.utc).isoformat()
        today = date.today().isoformat()
        
        clients_saved = 0
        clients_enriched = 0
        
        for client_data in parsed['clients']:
            genes_code = client_data['genes_code']
            
            await db.finance_credit_evolution.update_one(
                {"genes_code": genes_code},
                {"$set": {
                    "genes_code": genes_code,
                    "account": client_data.get('account'),
                    "name": client_data.get('name'),
                    "evolution": client_data.get('evolution', {}),
                    "trend_percentage": client_data.get('trend_percentage'),
                    "trend_absolute": client_data.get('trend_absolute'),
                    "source_import_id": import_id,
                    "updated_at": now
                }},
                upsert=True
            )
            clients_saved += 1
            
            update_res = await db.finance_clients.update_one(
                {"genes_code": genes_code},
                {"$set": {
                    "credit_trend_percentage": client_data.get('trend_percentage'),
                    "credit_trend_absolute": client_data.get('trend_absolute'),
                    "updated_at": now
                }}
            )
            if update_res.matched_count:
                clients_enriched += 1
        
        not_found = clients_saved - clients_enriched
        if not_found > 0:
            result['warnings'].append(f"{not_found} clientes não encontrados (ainda não importados via saldos vencidos)")
        
        result['totals'] = {
            "clients": parsed['totals']['client_count'],
            "clients_updated": clients_enriched,
            "periods": len(parsed.get('periods', [])),
        }
        
        result['status'] = ImportStatus.IMPORTED.value
        result['success'] = True
        result['periods'] = parsed.get('periods', [])
        
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {
                "status": result['status'],
                "totals": result['totals'],
                "warnings": result['warnings'],
                "as_of_date": today,
                "processed_at": now
            }}
        )
        
        await db.finance_data_health.update_one(
            {"source_type": ImportType.CREDIT_EVOLUTION.value},
            {"$set": {
                "source_type": ImportType.CREDIT_EVOLUTION.value,
                "required_frequency": "quarterly",
                "last_import_id": import_id,
                "last_import_at": now,
                "last_as_of_date": today,
                "status": "ok",
                "is_blocking_operations": False
            }},
            upsert=True
        )
        
        logger.info(f"Processed credit evolution import {import_id}: {clients_saved} saved, {clients_enriched} enriched")
        
    except Exception as e:
        logger.error(f"Error processing credit evolution import: {e}")
        result['errors'].append(f"Erro ao processar importação: {str(e)}")
        result['status'] = ImportStatus.FAILED.value
        
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {"status": result['status'], "errors": result['errors']}}
        )
    
    return result


async def verify_promises_after_import(import_id: str, as_of: str) -> int:
    """
    Verifica promessas de pagamento vencidas contra a importação acabada de aplicar.
    Redução >= valor prometido -> Cumprida; redução parcial -> Parcialmente Cumprida; sem redução -> Falhada.
    """
    verified = 0
    now = datetime.now(timezone.utc).isoformat()
    
    promises = await db.finance_promises.find(
        {"status": "open", "promise_date": {"$lt": as_of}}, {"_id": 0}
    ).to_list(1000)
    
    for promise in promises:
        client = await db.finance_clients.find_one({"id": promise["client_id"]}, {"_id": 0})
        if not client:
            continue
        
        current_overdue = client.get("overdue_balance_accounting", 0) or 0
        amount = promise.get("amount", 0) or 0
        baseline = promise.get("baseline_overdue")
        
        if baseline is None:
            # Fallback: métrica diária mais próxima da data de criação da promessa
            created_date = (promise.get("created_at") or "")[:10]
            metric = await db.finance_client_daily_metrics.find_one(
                {"client_id": promise["client_id"], "date": {"$lte": created_date}},
                {"_id": 0}, sort=[("date", -1)]
            )
            baseline = metric.get("overdue_balance_accounting") if metric else None
        
        if baseline is None:
            new_status = "fulfilled" if current_overdue <= 0.01 else "failed"
            note = f"Sem baseline registado — verificado pelo saldo vencido atual ({current_overdue:.2f}€)"
        else:
            reduction = baseline - current_overdue
            if current_overdue <= 0.01 or reduction >= amount - 0.01:
                new_status = "fulfilled"
            elif reduction > 0.01:
                new_status = "partial"
            else:
                new_status = "failed"
            note = f"Redução de {max(reduction, 0):.2f}€ face ao baseline de {baseline:.2f}€ (prometido: {amount:.2f}€)"
        
        await db.finance_promises.update_one(
            {"id": promise["id"]},
            {"$set": {
                "status": new_status,
                "verified_at": now,
                "verified_import_id": import_id,
                "verification_note": note
            }}
        )
        
        status_labels = {"fulfilled": "Cumprida", "partial": "Parcialmente Cumprida", "failed": "Falhada"}
        await db.finance_actions.insert_one({
            "id": str(uuid.uuid4()),
            "client_id": promise["client_id"],
            "action_type": "promise_updated",
            "user_id": "system",
            "user_name": "Sistema (verificação automática)",
            "notes": f"Promessa de {amount:.2f}€ ({promise.get('promise_date')}) marcada como {status_labels[new_status]}. {note}",
            "created_at": now
        })
        
        # Atualizar estado do cliente se a promessa falhou
        if new_status == "failed" and not client.get("is_blocked") and client.get("financial_status") not in [
            FinancialStatus.BLOQUEIO_SUGERIDO.value, FinancialStatus.EM_DISPUTA.value
        ]:
            tl = calculate_traffic_light(
                oldest_overdue_days=client.get("oldest_overdue_days", 0),
                overdue_collectable=client.get("overdue_balance_collectable", 0),
                total_balance=client.get("total_balance", 0),
                has_failed_promise=True,
                is_blocked=False,
                financial_status=FinancialStatus.PROMESSA_FALHADA.value
            )
            await db.finance_clients.update_one(
                {"id": client["id"]},
                {"$set": {
                    "financial_status": FinancialStatus.PROMESSA_FALHADA.value,
                    "traffic_light": tl.value,
                    "updated_at": now
                }}
            )
        
        verified += 1
        logger.info(f"Promise {promise['id']} auto-verified: {new_status}")
    
    return verified


async def process_open_documents_import(
    import_id: str,
    file_content: bytes,
    uploaded_by: str,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Processa importação do Mapa de Documentos em Aberto.
    Compara com o estado anterior para detetar pagamentos prováveis e parciais.
    """
    result = {
        'success': False,
        'import_id': import_id,
        'status': ImportStatus.VALIDATING.value,
        'totals': {},
        'warnings': [],
        'errors': []
    }
    
    try:
        parsed = parse_open_documents(file_content)
        
        if parsed['errors']:
            result['errors'].extend(parsed['errors'])
            result['status'] = ImportStatus.REJECTED.value
            await db.finance_imports.update_one(
                {"id": import_id},
                {"$set": {"status": result['status'], "errors": result['errors']}}
            )
            return result
        
        result['warnings'].extend(parsed['warnings'])
        
        now = datetime.now(timezone.utc).isoformat()
        today = date.today().isoformat()
        as_of = as_of_date or today
        
        # Estado anterior (para comparação diária)
        old_docs = {}
        async for d in db.finance_open_documents.find({}, {"_id": 0}):
            old_docs[d["doc_key"]] = d
        
        new_keys = set()
        docs_to_insert = []
        recovery_events = []
        
        for doc in parsed['documents']:
            doc_key = f"{doc['genes_code']}_{doc['document_number']}"
            new_keys.add(doc_key)
            docs_to_insert.append({
                **doc,
                "doc_key": doc_key,
                "import_id": import_id,
                "as_of_date": as_of,
                "updated_at": now
            })
            
            # Pagamento parcial: documento presente mas com valor em aberto menor
            old = old_docs.get(doc_key)
            if old and not doc.get('is_credit_note'):
                diff = (old.get('amount', 0) or 0) - (doc.get('amount', 0) or 0)
                if diff > 0.009:
                    recovery_events.append({
                        "id": str(uuid.uuid4()),
                        "date": as_of,
                        "genes_code": doc['genes_code'],
                        "client_name": doc.get('client_name'),
                        "document_number": doc['document_number'],
                        "document_type": doc.get('document_type'),
                        "event_type": "partial_payment",
                        "amount": round(diff, 2),
                        "import_id": import_id,
                        "created_at": now
                    })
        
        # Pagamentos prováveis: documentos que desapareceram
        if old_docs:
            for doc_key, old in old_docs.items():
                if doc_key not in new_keys and not old.get('is_credit_note') and (old.get('amount', 0) or 0) > 0:
                    recovery_events.append({
                        "id": str(uuid.uuid4()),
                        "date": as_of,
                        "genes_code": old['genes_code'],
                        "client_name": old.get('client_name'),
                        "document_number": old['document_number'],
                        "document_type": old.get('document_type'),
                        "event_type": "probable_payment",
                        "amount": round(old.get('amount', 0), 2),
                        "import_id": import_id,
                        "created_at": now
                    })
        
        # ============ STAGED REPLACE ATÓMICO ============
        # Nunca apagamos os documentos atuais antes de garantir que o novo lote está
        # completamente inserido e validado. Se algo falhar, os dados antigos ficam
        # intocados e a importação é marcada como FAILED.
        staging_collection_name = f"finance_open_documents_staging_{import_id[:8]}"
        staging = db[staging_collection_name]

        try:
            # 1) Escrever tudo em staging (nunca toca em finance_open_documents)
            if docs_to_insert:
                await staging.insert_many([dict(d) for d in docs_to_insert])

            # 2) Validar contagem em staging (deve bater com o parse)
            staged_count = await staging.count_documents({})
            if staged_count != len(docs_to_insert):
                raise RuntimeError(
                    f"Staging count mismatch: inseridos {staged_count} de {len(docs_to_insert)}"
                )

            # 3) Swap atómico — apenas AGORA apagamos os antigos e escrevemos os novos
            #    O processo entre estas duas linhas é sub-segundo; se cair a meio, a
            #    próxima importação vai comparar contra vazio e criar recovery events
            #    incorrectos, mas os dados históricos em finance_imports e as
            #    finance_client_daily_metrics permanecem íntegros.
            await db.finance_open_documents.delete_many({})
            if docs_to_insert:
                await db.finance_open_documents.insert_many(
                    [dict(d) for d in docs_to_insert]
                )

            # 4) Verificação final
            final_count = await db.finance_open_documents.count_documents({})
            if final_count != len(docs_to_insert):
                raise RuntimeError(
                    f"Post-swap count mismatch: {final_count} vs {len(docs_to_insert)}"
                )
        finally:
            # 5) Limpeza da staging (sempre, mesmo em erro)
            try:
                await staging.drop()
            except Exception as drop_err:
                logger.warning(f"Failed to drop staging collection {staging_collection_name}: {drop_err}")

        if recovery_events:
            await db.finance_recovery_events.insert_many([dict(e) for e in recovery_events])
        
        recovered_total = round(sum(e['amount'] for e in recovery_events), 2)
        paid_count = sum(1 for e in recovery_events if e['event_type'] == 'probable_payment')
        partial_count = sum(1 for e in recovery_events if e['event_type'] == 'partial_payment')
        
        if not old_docs:
            result['warnings'].append("Primeira importação de documentos em aberto — comparação diária ativa a partir da próxima.")
        elif recovery_events:
            result['message'] = f"Detetados {paid_count} pagamentos prováveis e {partial_count} pagamentos parciais ({recovered_total:.2f}€ recuperados)"
        
        result['totals'] = {
            "clients": parsed['totals']['client_count'],
            "documents": parsed['totals']['document_count'],
            "total_balance": parsed['totals']['total_balance'],
            "total_overdue": parsed['totals']['total_overdue'],
            "credit_notes": parsed['totals']['credit_notes_count'],
            "credit_notes_amount": round(parsed['totals']['credit_notes_amount'], 2),
            "recovered_amount": recovered_total,
            "probable_payments": paid_count,
            "partial_payments": partial_count,
        }
        
        result['status'] = ImportStatus.ACCEPTED_WITH_WARNINGS.value if result['warnings'] else ImportStatus.IMPORTED.value
        result['success'] = True
        
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {
                "status": result['status'],
                "totals": result['totals'],
                "warnings": result['warnings'],
                "as_of_date": as_of,
                "processed_at": now
            }}
        )
        
        await db.finance_data_health.update_one(
            {"source_type": ImportType.OPEN_DOCUMENTS.value},
            {"$set": {
                "source_type": ImportType.OPEN_DOCUMENTS.value,
                "required_frequency": "daily",
                "last_import_id": import_id,
                "last_import_at": now,
                "last_as_of_date": as_of,
                "status": "ok",
                "is_blocking_operations": False
            }},
            upsert=True
        )
        
        logger.info(f"Processed open documents import {import_id}: {len(docs_to_insert)} docs, {len(recovery_events)} recovery events")
        
    except Exception as e:
        logger.error(f"Error processing open documents import: {e}")
        result['errors'].append(f"Erro ao processar importação: {str(e)}")
        result['status'] = ImportStatus.FAILED.value
        
        await db.finance_imports.update_one(
            {"id": import_id},
            {"$set": {"status": result['status'], "errors": result['errors']}}
        )
    
    return result


# ============== RECOMPUTAÇÃO GLOBAL ==============

async def recompute_documents_and_clients(
    triggered_by: str = "system",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Reprocessa a classificação de TODOS os documentos existentes na BD (sem re-importar)
    e recalcula os agregados de cada cliente (`overdue_balance_collectable`,
    `residual_balance`, `is_residual_only`, `oldest_overdue_days`, `financial_status`,
    `traffic_light`).

    Respeita overrides manuais (`manually_marked_collectable`, `manual_action`).

    Devolve um sumário. Se `dry_run=True`, não escreve na BD.
    """
    cfg = await get_finance_settings()
    now = datetime.now(timezone.utc).isoformat()

    docs_reclassified = 0
    docs_total = 0
    clients_updated = 0
    changes_by_class: Dict[str, int] = {}

    # 1) Reclassificar documentos e agrupar por cliente
    per_client_aggregates: Dict[str, Dict[str, Any]] = {}

    async for doc in db.finance_documents.find({}, {"_id": 0}):
        docs_total += 1
        amount_open = float(doc.get("amount_open", 0) or 0)
        amount_original = doc.get("amount_original")
        days_overdue = int(doc.get("days_overdue", 0) or 0)
        is_credit = doc.get("document_type") == "NC" or amount_open < 0
        prev_class = doc.get("classification")
        manually_marked_collectable = bool(doc.get("manually_marked_collectable", False))
        manual_action = doc.get("manual_action")

        new_class = classify_document(
            amount_open=amount_open,
            amount_original=amount_original,
            is_credit_note=is_credit,
            days_overdue=days_overdue,
            config=cfg,
        )

        effective = new_class
        if manually_marked_collectable:
            effective = DocumentClassification.COLLECTABLE
        elif manual_action == "mark_dispute":
            effective = DocumentClassification.DISPUTE
        elif manual_action == "mark_resolved_operationally":
            effective = DocumentClassification.RESOLVED_OPERATIONALLY

        if new_class.value != prev_class:
            docs_reclassified += 1
            key = f"{prev_class}->{new_class.value}"
            changes_by_class[key] = changes_by_class.get(key, 0) + 1

        if not dry_run:
            await db.finance_documents.update_one(
                {"id": doc["id"]},
                {"$set": {
                    "classification": new_class.value,
                    "effective_classification": effective.value,
                    "updated_at": now,
                }}
            )

        client_id = doc.get("client_id")
        if not client_id:
            continue

        agg = per_client_aggregates.setdefault(client_id, {
            "overdue_collectable": 0.0,
            "residual_balance": 0.0,
            "residual_doc_count": 0,
            "oldest_overdue_days": 0,
            "in_dispute": False,
        })

        if effective == DocumentClassification.COLLECTABLE:
            if amount_open > 0:
                agg["overdue_collectable"] += amount_open
                if days_overdue > agg["oldest_overdue_days"]:
                    agg["oldest_overdue_days"] = days_overdue
        elif effective in (
            DocumentClassification.RESIDUAL,
            DocumentClassification.MICRO_OLD,
        ):
            agg["residual_balance"] += amount_open
            agg["residual_doc_count"] += 1
        elif effective == DocumentClassification.DISPUTE:
            agg["in_dispute"] = True

    # 2) Actualizar agregados nos clientes
    if not dry_run:
        for client_id, agg in per_client_aggregates.items():
            client = await db.finance_clients.find_one({"id": client_id}, {"_id": 0})
            if not client:
                continue

            overdue_collectable = round(agg["overdue_collectable"], 2)
            residual_balance = round(agg["residual_balance"], 2)
            is_residual_only = overdue_collectable <= 0 and residual_balance > 0

            is_blocked = bool(client.get("is_blocked", False))
            current_status = client.get("financial_status")
            block_suggested = current_status == FinancialStatus.BLOQUEIO_SUGERIDO.value

            has_active_promise = await db.finance_promises.count_documents({
                "client_id": client_id, "status": "open"
            }) > 0
            has_failed_promise = await db.finance_promises.count_documents({
                "client_id": client_id, "status": "failed"
            }) > 0

            financial_status = calculate_financial_status(
                overdue_collectable=overdue_collectable,
                residual_balance=residual_balance,
                is_residual_only=is_residual_only,
                is_blocked=is_blocked,
                has_active_promise=has_active_promise,
                has_failed_promise=has_failed_promise,
                in_dispute=agg["in_dispute"] or current_status == FinancialStatus.EM_DISPUTA.value,
                block_suggested=block_suggested,
            )

            total_balance = float(client.get("total_balance", 0) or 0)
            traffic_light = calculate_traffic_light(
                oldest_overdue_days=agg["oldest_overdue_days"],
                overdue_collectable=overdue_collectable,
                total_balance=total_balance,
                has_failed_promise=has_failed_promise,
                is_blocked=is_blocked,
                financial_status=financial_status.value,
            )

            await db.finance_clients.update_one(
                {"id": client_id},
                {"$set": {
                    "overdue_balance_collectable": overdue_collectable,
                    "residual_balance": residual_balance,
                    "oldest_overdue_days": agg["oldest_overdue_days"],
                    "is_residual_only": is_residual_only,
                    "financial_status": financial_status.value,
                    "traffic_light": traffic_light.value,
                    "updated_at": now,
                }}
            )
            clients_updated += 1

    summary = {
        "triggered_by": triggered_by,
        "dry_run": dry_run,
        "documents_total": docs_total,
        "documents_reclassified": docs_reclassified,
        "clients_updated": clients_updated,
        "changes_by_class": changes_by_class,
        "executed_at": now,
    }
    logger.info(f"Finance recompute: {summary}")

    if not dry_run:
        await db.finance_recompute_log.insert_one({
            "id": str(uuid.uuid4()),
            **summary,
        })
    return summary
