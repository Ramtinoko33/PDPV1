import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '../../components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
import axios from 'axios';
import { AlertTriangle, CheckCircle, XCircle, RefreshCw, ShieldCheck } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TYPE_LABEL = {
  overdue_balances: 'Saldos Vencidos',
  open_documents: 'Documentos Aberto',
  client_info: 'Info Clientes',
  credit_evolution: 'Evolução Crédito',
};

const formatCurrency = (v) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(v || 0);

const formatDateTime = (s) => (s ? new Date(s).toLocaleString('pt-PT') : '-');

const FinanceAnomalies = () => {
  const { user, getAuthHeaders } = useAuth();
  const canValidate = ['OWNER', 'FINANCE_REVIEWER'].includes(user?.finance_role);

  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('active');
  const [severityFilter, setSeverityFilter] = useState('all');

  const [validateDialog, setValidateDialog] = useState({
    open: false,
    anomaly: null,
    comment: '',
    submitting: false,
    error: null,
  });

  const fetchAnomalies = useCallback(async () => {
    setLoading(true);
    try {
      const params = { status: statusFilter };
      if (severityFilter !== 'all') params.severity = severityFilter;
      const res = await axios.get(`${API_URL}/api/finance/anomalies`, {
        headers: getAuthHeaders(),
        params,
      });
      setAnomalies(res.data.anomalies || []);
    } catch (err) {
      console.error('Erro a carregar anomalias:', err);
      setAnomalies([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, severityFilter, getAuthHeaders]);

  useEffect(() => { fetchAnomalies(); }, [fetchAnomalies]);

  const openValidate = (anomaly) => {
    setValidateDialog({ open: true, anomaly, comment: '', submitting: false, error: null });
  };

  const submitValidate = async () => {
    const { anomaly, comment } = validateDialog;
    if (!anomaly) return;
    if (!comment.trim()) {
      setValidateDialog((s) => ({ ...s, error: 'Comentário obrigatório' }));
      return;
    }
    setValidateDialog((s) => ({ ...s, submitting: true, error: null }));
    try {
      await axios.post(
        `${API_URL}/api/finance/anomalies/${anomaly.id}/validate`,
        { comment: comment.trim() },
        { headers: getAuthHeaders() }
      );
      setValidateDialog({ open: false, anomaly: null, comment: '', submitting: false, error: null });
      fetchAnomalies();
    } catch (err) {
      setValidateDialog((s) => ({
        ...s,
        submitting: false,
        error: err?.response?.data?.detail || 'Erro ao validar',
      }));
    }
  };

  const closeValidate = () => {
    if (validateDialog.submitting) return;
    setValidateDialog({ open: false, anomaly: null, comment: '', submitting: false, error: null });
  };

  return (
    <div className="p-6 space-y-6" data-testid="finance-anomalies-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <AlertTriangle className="h-7 w-7 text-amber-500" />
            Anomalias entre Importações
          </h1>
          <p className="text-slate-500 mt-1">
            Diferenças anormais entre importações Finance consecutivas do mesmo tipo.
            {' '}Alerta apenas — não bloqueia nenhum dado.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={fetchAnomalies}
          disabled={loading}
          data-testid="anomalies-refresh-btn"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Actualizar
        </Button>
      </div>

      {/* Filtros */}
      <Card>
        <CardContent className="p-4 flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-600">Estado:</span>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-40" data-testid="anomalies-status-filter">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Activas</SelectItem>
                <SelectItem value="validated">Validadas</SelectItem>
                <SelectItem value="all">Todas</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-600">Severidade:</span>
            <Select value={severityFilter} onValueChange={setSeverityFilter}>
              <SelectTrigger className="w-40" data-testid="anomalies-severity-filter">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                <SelectItem value="critical">Crítica</SelectItem>
                <SelectItem value="warning">Warning</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="ml-auto text-sm text-slate-500" data-testid="anomalies-count-summary">
            {anomalies.length} {anomalies.length === 1 ? 'anomalia' : 'anomalias'}
          </div>
        </CardContent>
      </Card>

      {/* Lista de anomalias */}
      {loading && (
        <div className="text-center py-10 text-slate-500">A carregar…</div>
      )}
      {!loading && anomalies.length === 0 && (
        <Card>
          <CardContent className="p-10 text-center">
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
            <div className="text-lg font-medium">Sem anomalias {statusFilter === 'active' ? 'activas' : ''}</div>
            <div className="text-sm text-slate-500 mt-1">
              As últimas importações estão em linha com as anteriores.
            </div>
          </CardContent>
        </Card>
      )}

      {!loading && anomalies.map((a) => (
        <Card
          key={a.id}
          className={
            a.status === 'validated'
              ? 'border-slate-200 opacity-75'
              : a.severity === 'critical'
                ? 'border-red-300 border-2'
                : 'border-amber-300 border-2'
          }
          data-testid={`anomaly-card-${a.id}`}
        >
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg">
                  {a.severity === 'critical'
                    ? <XCircle className="h-5 w-5 text-red-600" />
                    : <AlertTriangle className="h-5 w-5 text-amber-500" />
                  }
                  {TYPE_LABEL[a.import_type] || a.import_type}
                  <Badge
                    variant={a.severity === 'critical' ? 'destructive' : 'default'}
                    className={a.severity === 'critical' ? '' : 'bg-amber-500'}
                    data-testid={`anomaly-severity-${a.id}`}
                  >
                    {a.severity === 'critical' ? 'CRÍTICO' : 'WARNING'}
                  </Badge>
                  {a.status === 'validated' && (
                    <Badge variant="outline" className="border-green-500 text-green-700">
                      <ShieldCheck className="h-3 w-3 mr-1" />Validada
                    </Badge>
                  )}
                </CardTitle>
                <div className="text-sm text-slate-600 mt-1">
                  {a.triggers.join(' • ')}
                </div>
              </div>
              {a.status === 'active' && canValidate && (
                <Button
                  size="sm"
                  onClick={() => openValidate(a)}
                  data-testid={`anomaly-validate-btn-${a.id}`}
                >
                  <ShieldCheck className="h-4 w-4 mr-1" />
                  Validar
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Anterior */}
              <div className="p-3 bg-slate-50 rounded border">
                <div className="text-xs uppercase text-slate-500 mb-2">Anterior</div>
                <div className="text-xs text-slate-600 mb-1 truncate" title={a.previous.filename}>
                  {a.previous.filename}
                </div>
                <div className="text-xs text-slate-500 mb-2">{formatDateTime(a.previous.uploaded_at)}</div>
                <div className="text-sm">Vencido: <strong>{formatCurrency(a.previous.total_overdue)}</strong></div>
                <div className="text-sm">Clientes: <strong>{a.previous.clients}</strong></div>
                <div className="text-sm">Docs: <strong>{a.previous.documents}</strong></div>
              </div>
              {/* Actual */}
              <div className="p-3 bg-blue-50 rounded border border-blue-200">
                <div className="text-xs uppercase text-blue-700 mb-2">Actual</div>
                <div className="text-xs text-slate-700 mb-1 truncate" title={a.current.filename}>
                  {a.current.filename}
                </div>
                <div className="text-xs text-slate-500 mb-2">{formatDateTime(a.current.uploaded_at)}</div>
                <div className="text-sm">Vencido: <strong data-testid={`anomaly-current-total-${a.id}`}>{formatCurrency(a.current.total_overdue)}</strong></div>
                <div className="text-sm">Clientes: <strong data-testid={`anomaly-current-clients-${a.id}`}>{a.current.clients}</strong></div>
                <div className="text-sm">Docs: <strong data-testid={`anomaly-current-docs-${a.id}`}>{a.current.documents}</strong></div>
              </div>
              {/* Delta */}
              <div className={`p-3 rounded border ${a.severity === 'critical' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
                <div className={`text-xs uppercase mb-2 ${a.severity === 'critical' ? 'text-red-700' : 'text-amber-700'}`}>Δ Diferença</div>
                <div className="text-sm">
                  Vencido: <strong data-testid={`anomaly-delta-total-${a.id}`}>
                    {a.delta.total_overdue_abs > 0 ? '+' : ''}{formatCurrency(a.delta.total_overdue_abs)}
                  </strong> ({a.delta.total_overdue_pct}%)
                </div>
                <div className="text-sm">
                  Clientes: <strong>{a.delta.clients_abs > 0 ? '+' : ''}{a.delta.clients_abs}</strong> ({a.delta.clients_pct}%)
                </div>
                <div className="text-sm">
                  Docs: <strong>{a.delta.documents_abs > 0 ? '+' : ''}{a.delta.documents_abs}</strong> ({a.delta.documents_pct}%)
                </div>
              </div>
            </div>

            {a.validation && (
              <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded text-sm">
                <div className="font-medium text-green-800 mb-1">
                  <ShieldCheck className="inline h-4 w-4 mr-1" />
                  Validada por {a.validation.validated_by_name} — {formatDateTime(a.validation.validated_at)}
                </div>
                <div className="text-green-900" data-testid={`anomaly-validation-comment-${a.id}`}>
                  “{a.validation.comment}”
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      {/* Dialog de validação */}
      <Dialog open={validateDialog.open} onOpenChange={(o) => { if (!o) closeValidate(); }}>
        <DialogContent data-testid="anomaly-validate-dialog">
          <DialogHeader>
            <DialogTitle>Validar anomalia</DialogTitle>
            <DialogDescription>
              Confirma que a diferença detectada é legítima. A validação fica registada com o seu nome e o comentário.
            </DialogDescription>
          </DialogHeader>
          {validateDialog.anomaly && (
            <div className="p-3 bg-slate-50 border rounded text-sm mb-3">
              <div><strong>{TYPE_LABEL[validateDialog.anomaly.import_type]}</strong> — {validateDialog.anomaly.severity.toUpperCase()}</div>
              <div className="text-slate-600 mt-1">{validateDialog.anomaly.triggers.join(' • ')}</div>
            </div>
          )}
          <label className="text-sm font-medium">Comentário (obrigatório)</label>
          <Textarea
            value={validateDialog.comment}
            onChange={(e) => setValidateDialog((s) => ({ ...s, comment: e.target.value, error: null }))}
            placeholder="Ex: Confirmado com contabilidade — recuperação de saldos antigos após reconciliação"
            rows={4}
            data-testid="anomaly-validate-comment-input"
          />
          {validateDialog.error && (
            <div className="text-sm text-red-600" data-testid="anomaly-validate-error">
              {validateDialog.error}
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={closeValidate}
              disabled={validateDialog.submitting}
              data-testid="anomaly-validate-cancel-btn"
            >
              Cancelar
            </Button>
            <Button
              onClick={submitValidate}
              disabled={validateDialog.submitting || !validateDialog.comment.trim()}
              data-testid="anomaly-validate-submit-btn"
            >
              {validateDialog.submitting ? 'A gravar…' : 'Confirmar validação'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FinanceAnomalies;
