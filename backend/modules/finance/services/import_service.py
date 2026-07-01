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

# Configurações de saldos residuais
RESIDUAL_CONFIG = {
    'document_threshold': 1.00,      # até 1€ por documento
    'client_threshold': 5.00,        # até 5€ acumulado por cliente
    'percentage_threshold': 0.005,   # até 0.5% do valor original
    'max_documents': 10,             # máximo de documentos residuais por cliente
}

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
    in_dispute: bool = False,
    in_payment_plan: bool = False
) -> DocumentClassification:
    """
    Classifica um documento (cobrável, residual, crédito, etc.)
    """
    if is_credit_note or amount_open < 0:
        return DocumentClassification.CREDIT
    
    if in_dispute:
        return DocumentClassification.DISPUTE
    
    if in_payment_plan:
        return DocumentClassification.PAYMENT_PLAN
    
    # Verificar se é residual
    if amount_open > 0 and amount_open <= RESIDUAL_CONFIG['document_threshold']:
        # Verificar percentagem se temos valor original
        if amount_original and amount_original > 0:
            percentage = amount_open / amount_original
            if percentage <= RESIDUAL_CONFIG['percentage_threshold']:
                return DocumentClassification.RESIDUAL
        else:
            # Sem valor original, usar apenas threshold absoluto
            return DocumentClassification.RESIDUAL
    
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
                    is_credit_note=is_credit
                )
                
                if classification == DocumentClassification.RESIDUAL:
                    total_residual += amount_open
                    residual_doc_count += 1
                elif classification == DocumentClassification.COLLECTABLE:
                    overdue_collectable += amount_open
                    if days_overdue > oldest_overdue_days:
                        oldest_overdue_days = days_overdue
                
                # Criar/atualizar documento
                doc_id = f"{genes_code}_{doc['document_number']}"
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
            if total_residual > RESIDUAL_CONFIG['client_threshold'] or residual_doc_count > RESIDUAL_CONFIG['max_documents']:
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
