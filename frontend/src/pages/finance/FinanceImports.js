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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '../../components/ui/dialog';
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

const formatCurrency = (v) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(v || 0);

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
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    // 1) Detecção heurística de tipo — avisa antes do upload se o
    //    tipo seleccionado no dropdown não corresponde ao conteúdo do
    //    ficheiro (previne o cenário 1492/0 do bug de Feb 2026).
    try {
      const detectForm = new FormData();
      detectForm.append('file', file);
      const detectRes = await axios.post(
        `${API_URL}/api/finance/imports/detect-type`,
        detectForm,
        { headers: { ...getAuthHeaders(), 'Content-Type': 'multipart/form-data' } }
      );
      const detected = detectRes.data?.detected;
      const confidence = detectRes.data?.confidence;
      if (
        detected
        && detected !== selectedType
        && (confidence === 'high' || confidence === 'medium')
      ) {
        const labels = {
          overdue_balances: 'Saldos Vencidos',
          open_documents: 'Documentos Aberto',
          client_info: 'Info Clientes',
          credit_evolution: 'Evolução Crédito',
        };
        const ok = window.confirm(
          `⚠️ O ficheiro parece ser do tipo "${labels[detected] || detected}" `
          + `(confiança ${confidence}), mas seleccionou "${labels[selectedType] || selectedType}" no dropdown.\n\n`
          + `Deseja mesmo assim continuar com "${labels[selectedType] || selectedType}"?\n\n`
          + `Recomendado: cancelar e escolher "${labels[detected] || detected}" no dropdown.`
        );
        if (!ok) {
          if (fileInputRef.current) fileInputRef.current.value = '';
          return;
        }
      }
    } catch (err) {
      // Se a detecção falhar não bloqueia o upload — apenas regista.
      console.warn('Detecção de tipo falhou (continuando com upload):', err);
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

  const [approveDialog, setApproveDialog] = useState({
    open: false,
    importId: null,
    filename: null,
    loading: false,
    preview: null,
    error: null,
    submitting: false,
    confirmText: '',
  });

  const openApproveDialog = async (imp) => {
    setApproveDialog({
      open: true,
      importId: imp.id,
      filename: imp.filename,
      loading: true,
      preview: null,
      error: null,
      submitting: false,
      confirmText: '',
    });
    try {
      const res = await axios.get(
        `${API_URL}/api/finance/imports/${imp.id}/preview`,
        { headers: getAuthHeaders() }
      );
      setApproveDialog((s) => ({ ...s, loading: false, preview: res.data }));
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Erro ao carregar prévia da importação';
      setApproveDialog((s) => ({ ...s, loading: false, error: detail }));
    }
  };

  const confirmApprove = async () => {
    const { importId, preview, confirmText } = approveDialog;
    if (!importId) return;
    if (preview?.is_critical && confirmText.trim().toUpperCase() !== 'APROVAR') {
      alert('Escreva APROVAR para confirmar esta importação crítica.');
      return;
    }
    setApproveDialog((s) => ({ ...s, submitting: true }));
    try {
      await axios.post(
        `${API_URL}/api/finance/imports/${importId}/approve`,
        {},
        { headers: getAuthHeaders() }
      );
      setApproveDialog({
        open: false, importId: null, filename: null, loading: false,
        preview: null, error: null, submitting: false, confirmText: '',
      });
      fetchData();
    } catch (err) {
      console.error('Erro ao aprovar:', err);
      const detail = err?.response?.data?.detail;
      setApproveDialog((s) => ({
        ...s,
        submitting: false,
        error: detail || 'Erro ao aprovar importação',
      }));
      // Refresca lista em background para mostrar novo estado (ex: rejected pelo guard)
      fetchData();
    }
  };

  const closeApproveDialog = () => {
    if (approveDialog.submitting) return;
    setApproveDialog({
      open: false, importId: null, filename: null, loading: false,
      preview: null, error: null, submitting: false, confirmText: '',
    });
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
                          onClick={() => openApproveDialog(imp)}
                          data-testid={`approve-import-btn-${imp.id}`}
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

      {/* Modal de Pré-Aprovação — mostra impacto antes de aplicar dados */}
      <Dialog
        open={approveDialog.open}
        onOpenChange={(open) => { if (!open) closeApproveDialog(); }}
      >
        <DialogContent
          className="max-w-2xl"
          data-testid="approve-import-dialog"
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className={`h-5 w-5 ${approveDialog.preview?.is_critical ? 'text-red-600' : 'text-amber-600'}`} />
              Confirmar aprovação de importação
            </DialogTitle>
            <DialogDescription>
              Ficheiro: <strong>{approveDialog.filename}</strong>
            </DialogDescription>
          </DialogHeader>

          {approveDialog.loading && (
            <div className="p-6 text-center text-sm text-slate-500" data-testid="approve-dialog-loading">
              A calcular impacto…
            </div>
          )}

          {!approveDialog.loading && approveDialog.error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded text-sm text-red-800" data-testid="approve-dialog-error">
              {approveDialog.error}
            </div>
          )}

          {!approveDialog.loading && approveDialog.preview && (
            <div className="space-y-4">
              {/* Guard warnings — bloqueio crítico */}
              {approveDialog.preview.guard_warnings?.length > 0 && (
                <div className="p-3 bg-red-50 border-2 border-red-300 rounded" data-testid="approve-dialog-guard-warnings">
                  <div className="flex items-start gap-2">
                    <XCircle className="h-5 w-5 text-red-600 mt-0.5" />
                    <div className="flex-1">
                      <div className="font-semibold text-red-800">
                        Safety guard activo — aprovação será rejeitada
                      </div>
                      <ul className="text-sm text-red-700 mt-1 space-y-1 list-disc list-inside">
                        {approveDialog.preview.guard_warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {!approveDialog.preview.supported && (
                <div className="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-800">
                  {approveDialog.preview.message || 'Prévia detalhada não disponível para este tipo de importação.'}
                </div>
              )}

              {approveDialog.preview.supported && approveDialog.preview.new && (
                <>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="p-3 bg-slate-50 border rounded">
                      <div className="text-xs text-slate-500 uppercase mb-1">Actual</div>
                      <div className="text-sm">Clientes: <strong data-testid="preview-current-clients">{approveDialog.preview.current.clients}</strong></div>
                      <div className="text-sm">Docs: <strong data-testid="preview-current-docs">{approveDialog.preview.current.documents}</strong></div>
                      <div className="text-sm">Vencido: <strong data-testid="preview-current-total">{formatCurrency(approveDialog.preview.current.total_overdue)}</strong></div>
                    </div>
                    <div className="p-3 bg-blue-50 border border-blue-200 rounded">
                      <div className="text-xs text-blue-700 uppercase mb-1">Novo</div>
                      <div className="text-sm">Clientes: <strong data-testid="preview-new-clients">{approveDialog.preview.new.clients}</strong></div>
                      <div className="text-sm">Docs: <strong data-testid="preview-new-docs">{approveDialog.preview.new.documents}</strong></div>
                      <div className="text-sm">Vencido: <strong data-testid="preview-new-total">{formatCurrency(approveDialog.preview.new.total_overdue)}</strong></div>
                    </div>
                    <div className={`p-3 border rounded ${approveDialog.preview.is_critical ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
                      <div className={`text-xs uppercase mb-1 ${approveDialog.preview.is_critical ? 'text-red-700' : 'text-amber-700'}`}>Δ Diferença</div>
                      <div className="text-sm">+{approveDialog.preview.delta.clients_added} novos cli</div>
                      <div className="text-sm">−{approveDialog.preview.delta.clients_removed} cli fora</div>
                      <div className="text-sm">
                        Vencido: <strong data-testid="preview-diff-pct">{approveDialog.preview.delta.total_overdue_diff_pct}%</strong>
                      </div>
                    </div>
                  </div>

                  {approveDialog.preview.is_critical && approveDialog.preview.guard_warnings.length === 0 && (
                    <div className="p-3 bg-amber-50 border border-amber-200 rounded text-sm text-amber-800">
                      <strong>Diferença anormal.</strong> Reveja com atenção antes de aprovar.
                    </div>
                  )}
                </>
              )}

              {approveDialog.preview.is_critical && approveDialog.preview.guard_warnings.length === 0 && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    Alteração crítica — escreva <code className="px-1 bg-slate-100 rounded">APROVAR</code> para confirmar:
                  </label>
                  <Input
                    value={approveDialog.confirmText}
                    onChange={(e) => setApproveDialog((s) => ({ ...s, confirmText: e.target.value }))}
                    placeholder="APROVAR"
                    data-testid="approve-dialog-confirm-input"
                  />
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={closeApproveDialog}
              disabled={approveDialog.submitting}
              data-testid="approve-dialog-cancel-btn"
            >
              Cancelar
            </Button>
            <Button
              onClick={confirmApprove}
              disabled={
                approveDialog.loading
                || approveDialog.submitting
                || (approveDialog.preview?.guard_warnings?.length > 0)
                || (
                  approveDialog.preview?.is_critical
                  && (approveDialog.preview?.guard_warnings?.length || 0) === 0
                  && approveDialog.confirmText.trim().toUpperCase() !== 'APROVAR'
                )
              }
              data-testid="approve-dialog-confirm-btn"
              className={approveDialog.preview?.is_critical ? 'bg-red-600 hover:bg-red-700' : ''}
            >
              {approveDialog.submitting ? 'A aprovar…' : 'Confirmar aprovação'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FinanceImports;
