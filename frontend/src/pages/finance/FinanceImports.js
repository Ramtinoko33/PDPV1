import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
import axios from 'axios';
import {
  Upload,
  FileSpreadsheet,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  RefreshCw,
  Download
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const formatDateTime = (dateStr) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('pt-PT');
};

const StatusBadge = ({ status }) => {
  const styles = {
    imported: 'bg-green-100 text-green-800',
    accepted: 'bg-green-100 text-green-800',
    accepted_with_warnings: 'bg-yellow-100 text-yellow-800',
    received: 'bg-blue-100 text-blue-800',
    validating: 'bg-blue-100 text-blue-800',
    pending_approval: 'bg-orange-100 text-orange-800',
    rejected: 'bg-red-100 text-red-800',
    failed: 'bg-red-100 text-red-800',
    duplicate: 'bg-slate-100 text-slate-800',
    outdated: 'bg-slate-100 text-slate-800'
  };
  
  const labels = {
    imported: 'Importado',
    accepted: 'Aceite',
    accepted_with_warnings: 'Aceite (Avisos)',
    received: 'Recebido',
    validating: 'A validar',
    pending_approval: 'Aguarda Aprovação',
    rejected: 'Rejeitado',
    failed: 'Falhou',
    duplicate: 'Duplicado',
    outdated: 'Desatualizado'
  };
  
  return (
    <Badge className={styles[status] || 'bg-slate-100'}>
      {labels[status] || status}
    </Badge>
  );
};

const FinanceImports = () => {
  const { user, getAuthHeaders } = useAuth();
  const [imports, setImports] = useState([]);
  const [dataHealth, setDataHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selectedType, setSelectedType] = useState('overdue_balances');
  const [importsMeta, setImportsMeta] = useState({ total: 0, offset: 0, has_more: false });
  const [loadingMore, setLoadingMore] = useState(false);
  const fileInputRef = useRef(null);

  const PAGE_SIZE = 50;

  const fetchData = async () => {
    setLoading(true);
    try {
      const [importsRes, healthRes] = await Promise.all([
        axios.get(`${API_URL}/api/finance/imports?limit=${PAGE_SIZE}&offset=0`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/finance/data-health`, { headers: getAuthHeaders() })
      ]);
      setImports(importsRes.data.imports);
      setImportsMeta({
        total: importsRes.data.total,
        offset: importsRes.data.imports.length,
        has_more: importsRes.data.has_more,
      });
      setDataHealth(healthRes.data);
    } catch (err) {
      console.error('Erro ao carregar importações:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadMoreImports = async () => {
    setLoadingMore(true);
    try {
      const res = await axios.get(
        `${API_URL}/api/finance/imports?limit=${PAGE_SIZE}&offset=${importsMeta.offset}`,
        { headers: getAuthHeaders() }
      );
      setImports((prev) => [...prev, ...res.data.imports]);
      setImportsMeta({
        total: res.data.total,
        offset: importsMeta.offset + res.data.imports.length,
        has_more: res.data.has_more,
      });
    } catch (err) {
      console.error('Erro ao carregar mais:', err);
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    // Validate file type
    if (!file.name.match(/\.(xlsx|xls)$/i)) {
      alert('Por favor selecione um ficheiro Excel (.xlsx ou .xls)');
      return;
    }
    
    setUploading(true);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await axios.post(
        `${API_URL}/api/finance/imports/${selectedType}`,
        formData,
        {
          headers: {
            ...getAuthHeaders(),
            'Content-Type': 'multipart/form-data'
          }
        }
      );
      
      if (response.data.success) {
        alert('Ficheiro importado com sucesso!');
      } else if (response.data.errors?.length > 0) {
        alert(`Erros: ${response.data.errors.join(', ')}`);
      }
      
      fetchData();
    } catch (err) {
      console.error('Erro ao fazer upload:', err);
      alert(err.response?.data?.detail || 'Erro ao importar ficheiro');
    } finally {
      setUploading(false);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleApprove = async (importId) => {
    try {
      await axios.post(
        `${API_URL}/api/finance/imports/${importId}/approve`,
        {},
        { headers: getAuthHeaders() }
      );
      fetchData();
    } catch (err) {
      console.error('Erro ao aprovar:', err);
      alert('Erro ao aprovar importação');
    }
  };

  const typeLabels = {
    overdue_balances: 'Saldos Vencidos',
    open_documents: 'Documentos Aberto',
    client_info: 'Info Clientes',
    credit_evolution: 'Evolução Crédito'
  };

  const canApprove = user?.finance_role === 'OWNER' || user?.finance_role === 'FINANCE_REVIEWER';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Importações</h1>
          <p className="text-slate-500 text-sm">Gerir ficheiros do GENES/ERP</p>
        </div>
        <Button variant="outline" onClick={fetchData}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Data Health Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {dataHealth?.items?.map((item) => {
          const statusColors = {
            ok: 'border-green-200 bg-green-50',
            warning: 'border-yellow-200 bg-yellow-50',
            blocking: 'border-red-200 bg-red-50'
          };
          const statusIcons = {
            ok: <CheckCircle className="h-5 w-5 text-green-600" />,
            warning: <AlertTriangle className="h-5 w-5 text-yellow-600" />,
            blocking: <XCircle className="h-5 w-5 text-red-600" />
          };
          return (
            <Card key={item.source_type} className={`border-2 ${statusColors[item.status]}`}>
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  {statusIcons[item.status]}
                  <div>
                    <p className="font-medium">{typeLabels[item.source_type]}</p>
                    <p className="text-sm text-slate-600">
                      {item.last_import_at 
                        ? `Última: ${formatDateTime(item.last_import_at)}`
                        : 'Nenhuma importação'
                      }
                    </p>
                    {item.message && (
                      <p className="text-xs text-slate-500 mt-1">{item.message}</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Upload Section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Nova Importação
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 space-y-2">
              <label className="text-sm font-medium">Tipo de Ficheiro</label>
              <Select value={selectedType} onValueChange={setSelectedType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="overdue_balances">
                    <div className="flex items-center gap-2">
                      <FileSpreadsheet className="h-4 w-4" />
                      Saldos Vencidos (Diário) — "saldosvencidos.xlsx"
                    </div>
                  </SelectItem>
                  <SelectItem value="open_documents">
                    <div className="flex items-center gap-2">
                      <FileSpreadsheet className="h-4 w-4" />
                      Documentos em Aberto (Diário) — "Exemplo de mapa.xlsx"
                    </div>
                  </SelectItem>
                  <SelectItem value="client_info">
                    <div className="flex items-center gap-2">
                      <FileSpreadsheet className="h-4 w-4" />
                      Info Clientes (Semanal) — "infocliente.xlsx"
                    </div>
                  </SelectItem>
                  <SelectItem value="credit_evolution">
                    <div className="flex items-center gap-2">
                      <FileSpreadsheet className="h-4 w-4" />
                      Evolução Crédito (Trimestral) — "evoluçaocredito3em3meses.xlsx"
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="flex items-end">
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls"
                onChange={handleFileSelect}
                className="hidden"
                id="file-upload"
              />
              <Button
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="w-full md:w-auto"
              >
                {uploading ? (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    A importar...
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4 mr-2" />
                    Selecionar Ficheiro
                  </>
                )}
              </Button>
            </div>
          </div>
          
          <div className="mt-4 p-3 bg-slate-50 rounded-lg">
            <p className="text-sm text-slate-600">
              <strong>Formatos aceites:</strong> .xlsx, .xls
            </p>
            <p className="text-sm text-slate-500 mt-1">
              {selectedType === 'overdue_balances' && 
                'Ficheiro "saldosvencidos.xlsx" — mapa de saldos vencidos exportado do GENES (agrupado por cliente, com documentos). Importar diariamente antes de iniciar as cobranças.'}
              {selectedType === 'client_info' && 
                'Ficheiro "infocliente.xlsx" — InfoClientes para enriquecimento de dados (risco, faturação anual, forma de pagamento). Importar semanalmente.'}
              {selectedType === 'open_documents' &&
                'Ficheiro "Exemplo de mapa.xlsx" — mapa plano de documentos em aberto (FT e NC) para comparação diária. Parser em desenvolvimento (Fase 2): o ficheiro fica guardado.'}
              {selectedType === 'credit_evolution' &&
                'Ficheiro "evoluçaocredito3em3meses.xlsx" — evolução trimestral do crédito por cliente (colunas MM-YYYY). Importar a cada trimestre para análise de tendência.'}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Import History */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Histórico de Importações</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Data</th>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Tipo</th>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Ficheiro</th>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Utilizador</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Origem</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Clientes</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Documentos</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Estado</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {imports.map((imp) => (
                  <tr key={imp.id} className="hover:bg-slate-50">
                    <td className="p-3 text-sm">{formatDateTime(imp.uploaded_at)}</td>
                    <td className="p-3">
                      <Badge variant="outline">{typeLabels[imp.type] || imp.type}</Badge>
                    </td>
                    <td className="p-3 text-sm text-slate-600 max-w-[200px] truncate">
                      {imp.filename}
                    </td>
                    <td className="p-3 text-sm text-slate-600">{imp.uploaded_by_name || '-'}</td>
                    <td className="p-3 text-center">
                      <Badge variant="outline" className="text-xs">
                        {imp.source_method === 'rpa_folder' ? 'RPA' : 'Manual'}
                      </Badge>
                    </td>
                    <td className="p-3 text-center text-sm">
                      {imp.totals?.clients ?? '-'}
                    </td>
                    <td className="p-3 text-center text-sm">
                      {imp.totals?.documents ?? '-'}
                    </td>
                    <td className="p-3 text-center">
                      <StatusBadge status={imp.status} />
                    </td>
                    <td className="p-3 text-center">
                      {imp.status === 'pending_approval' && canApprove && (
                        <Button 
                          size="sm" 
                          onClick={() => handleApprove(imp.id)}
                        >
                          Aprovar
                        </Button>
                      )}
                      {imp.warnings?.length > 0 && (
                        <span className="text-xs text-yellow-600" title={imp.warnings.join(', ')}>
                          {imp.warnings.length} aviso(s)
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
                {imports.length === 0 && !loading && (
                  <tr>
                    <td colSpan={9} className="p-8 text-center text-slate-500">
                      Nenhuma importação encontrada
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {importsMeta.has_more && (
            <div className="p-4 border-t flex items-center justify-center gap-3">
              <span className="text-sm text-slate-500">
                A mostrar {imports.length} de {importsMeta.total}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={loadMoreImports}
                disabled={loadingMore}
                data-testid="imports-load-more-btn"
              >
                {loadingMore ? 'A carregar…' : 'Ver mais'}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default FinanceImports;
