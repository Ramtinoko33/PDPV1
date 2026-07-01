"""
Parser para ficheiro de Saldos Vencidos (saldosvencidos.xlsx)
Ficheiro principal diário de trabalho para cobrança.

Estrutura: Agrupado por cliente com cabeçalhos repetidos
- Linha de cliente: Nome, Cód, Localidade, Email, etc.
- Linhas de documentos: Nº doc, datas, valores vencidos
"""
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, date
from io import BytesIO
import openpyxl

logger = logging.getLogger(__name__)

# Colunas esperadas no cabeçalho de cliente
CLIENT_HEADER_MARKERS = ['Cliente', 'Cód. Cliente', 'Importe Total Vencido', 'Saldo Cliente']

# Colunas esperadas no cabeçalho de documentos
DOC_HEADER_MARKERS = ['Documento', 'Data da fatura', 'Data Vencimento', 'Dias Vencidos']


def parse_date(value: Any) -> Optional[str]:
    """Converte valor para data ISO string"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        # Tentar parse de string datetime
        try:
            # Formato: "2026-04-21 16:12:32.35700"
            dt = datetime.fromisoformat(value.split('.')[0].replace(' ', 'T'))
            return dt.date().isoformat()
        except:
            pass
        # Tentar parse simples
        try:
            return datetime.strptime(value[:10], '%Y-%m-%d').date().isoformat()
        except:
            pass
    return None


def parse_float(value: Any) -> float:
    """Converte valor para float"""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remover espaços e substituir vírgula por ponto
        cleaned = value.strip().replace(',', '.').replace(' ', '')
        try:
            return float(cleaned)
        except:
            return 0.0
    return 0.0


def parse_int(value: Any) -> int:
    """Converte valor para int"""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except:
            return 0
    return 0


def is_client_header_row(row: List[Any]) -> bool:
    """Verifica se é uma linha de cabeçalho de cliente"""
    if not row or len(row) < 3:
        return False
    row_str = [str(c).strip() if c else '' for c in row[:5]]
    return all(marker in row_str for marker in ['Cliente', 'Cód. Cliente'])


def is_doc_header_row(row: List[Any]) -> bool:
    """Verifica se é uma linha de cabeçalho de documentos"""
    if not row or len(row) < 3:
        return False
    row_str = [str(c).strip() if c else '' for c in row[:10]]
    return 'Documento' in row_str and 'Data Vencimento' in row_str


def is_client_data_row(row: List[Any]) -> bool:
    """Verifica se é uma linha de dados de cliente (não vazia na coluna 0)"""
    if not row or len(row) < 3:
        return False
    first_col = row[0]
    if first_col is None or str(first_col).strip() == '':
        return False
    # Não é cabeçalho
    if str(first_col).strip().lower() == 'cliente':
        return False
    return True


def is_doc_data_row(row: List[Any]) -> bool:
    """Verifica se é uma linha de dados de documento (vazia na coluna 0, com dados na coluna 1)"""
    if not row or len(row) < 3:
        return False
    first_col = row[0]
    second_col = row[1] if len(row) > 1 else None
    
    # Coluna 0 vazia, coluna 1 com número de documento
    if (first_col is None or str(first_col).strip() == '') and second_col:
        doc_str = str(second_col).strip()
        # Não é cabeçalho
        if doc_str.lower() == 'documento':
            return False
        # Tem formato de documento (ex: 026/3119)
        if '/' in doc_str or doc_str.replace(' ', '').isalnum():
            return True
    return False


def parse_overdue_balances(file_content: bytes) -> Dict[str, Any]:
    """
    Parse do ficheiro de saldos vencidos.
    
    Returns:
        Dict com:
        - clients: Lista de clientes com seus documentos
        - totals: Totais agregados
        - warnings: Avisos
        - errors: Erros
    """
    result = {
        'clients': [],
        'totals': {
            'client_count': 0,
            'document_count': 0,
            'total_overdue': 0.0,
            'total_balance': 0.0,
        },
        'warnings': [],
        'errors': []
    }
    
    try:
        wb = openpyxl.load_workbook(BytesIO(file_content), data_only=True)
        sheet = wb.active
        
        current_client = None
        current_client_docs = []
        
        for row_num, row in enumerate(sheet.iter_rows(values_only=True), 1):
            row_list = list(row) if row else []
            
            # Skip linhas completamente vazias
            if not any(c for c in row_list if c is not None and str(c).strip()):
                continue
            
            # Detectar tipo de linha
            if is_client_header_row(row_list):
                # Guardar cliente anterior se existir
                if current_client:
                    current_client['documents'] = current_client_docs
                    result['clients'].append(current_client)
                    result['totals']['document_count'] += len(current_client_docs)
                current_client = None
                current_client_docs = []
                continue
            
            if is_doc_header_row(row_list):
                continue
            
            if is_client_data_row(row_list):
                # Guardar cliente anterior
                if current_client:
                    current_client['documents'] = current_client_docs
                    result['clients'].append(current_client)
                    result['totals']['document_count'] += len(current_client_docs)
                
                # Novo cliente
                # Colunas: Cliente, Cód. Cliente, Localidade, Região, Email, Telefone1, Telefone2, Importe Total Vencido, Saldo Cliente
                total_overdue = parse_float(row_list[7] if len(row_list) > 7 else 0)
                total_balance = parse_float(row_list[8] if len(row_list) > 8 else 0)
                
                current_client = {
                    'name': str(row_list[0]).strip() if row_list[0] else '',
                    'genes_code': str(row_list[1]).strip() if len(row_list) > 1 and row_list[1] else '',
                    'locality': str(row_list[2]).strip() if len(row_list) > 2 and row_list[2] else None,
                    'region': str(row_list[3]).strip() if len(row_list) > 3 and row_list[3] else None,
                    'email': str(row_list[4]).strip() if len(row_list) > 4 and row_list[4] and row_list[4] != '0' else None,
                    'phone': str(row_list[5]).strip() if len(row_list) > 5 and row_list[5] and row_list[5] != '0' else None,
                    'mobile': str(row_list[6]).strip() if len(row_list) > 6 and row_list[6] and row_list[6] != '0' else None,
                    'total_overdue': total_overdue,
                    'total_balance': total_balance,
                }
                current_client_docs = []
                
                result['totals']['client_count'] += 1
                result['totals']['total_overdue'] += total_overdue
                result['totals']['total_balance'] += total_balance
                continue
            
            if is_doc_data_row(row_list) and current_client:
                # Linha de documento
                # Colunas (offset 1): Documento, Data da fatura, Data Vencimento, CódSede, Sede, Dias Vencidos, Importe Vencimiento, Vencido Factura
                doc = {
                    'document_number': str(row_list[1]).strip() if len(row_list) > 1 and row_list[1] else '',
                    'invoice_date': parse_date(row_list[2]) if len(row_list) > 2 else None,
                    'due_date': parse_date(row_list[3]) if len(row_list) > 3 else None,
                    'branch_code': str(row_list[4]).strip() if len(row_list) > 4 and row_list[4] else None,
                    'branch_name': str(row_list[5]).strip() if len(row_list) > 5 and row_list[5] else None,
                    'days_overdue': parse_int(row_list[6]) if len(row_list) > 6 else 0,
                    'amount_due': parse_float(row_list[7]) if len(row_list) > 7 else 0.0,
                    'amount_overdue': parse_float(row_list[8]) if len(row_list) > 8 else 0.0,
                }
                
                # Inferir tipo de documento do número
                doc_num = doc['document_number'].upper()
                if 'NC' in doc_num or doc['amount_due'] < 0:
                    doc['document_type'] = 'NC'
                elif 'FT' in doc_num or 'FAT' in doc_num:
                    doc['document_type'] = 'FT'
                else:
                    doc['document_type'] = 'FT'  # Default
                
                current_client_docs.append(doc)
        
        # Guardar último cliente
        if current_client:
            current_client['documents'] = current_client_docs
            result['clients'].append(current_client)
            result['totals']['document_count'] += len(current_client_docs)
        
        wb.close()
        
        logger.info(f"Parsed overdue balances: {result['totals']['client_count']} clients, {result['totals']['document_count']} documents")
        
    except Exception as e:
        logger.error(f"Error parsing overdue balances: {e}")
        result['errors'].append(f"Erro ao processar ficheiro: {str(e)}")
    
    return result
