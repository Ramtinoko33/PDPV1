import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import {
  Select, SelectTrigger, SelectContent, SelectItem, SelectValue
} from '../../components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { toast } from 'sonner';
import axios from 'axios';
import {
  Coins, RefreshCw, ArrowRight, Users, Filter, FileText,
  CheckCircle2, AlertTriangle, XCircle, Wrench, RotateCcw
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const formatCurrency = (value) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(value || 0);

const CLASSIFICATION_LABELS = {
  residual: { label: 'Residual', style: 'bg-amber-100 text-amber-800' },
  micro_old: { label: 'Micro-saldo antigo', style: 'bg-orange-100 text-orange-800' },
  residual_accumulated: { label: 'Residual acumulado', style: 'bg-red-100 text-red-800' },
};

const SUGGESTION_STYLES = {
  validate_old_invoice: 'bg-orange-50 text-orange-800 border border-orange-200',
  request_regularization: 'bg-blue-50 text-blue-800 border border-blue-200',
  review: 'bg-yellow-50 text-yellow-800 border border-yellow-200',
  ignore: 'bg-slate-50 text-slate-700 border border-slate-200',
};

const ACTION_OPTIONS = [
  { key: 'mark_collectable', label: 'Manter em cobrança', icon: CheckCircle2, variant: 'default', tone: 'text-emerald-600' },
  { key: 'mark_dispute', label: 'Marcar como disputa', icon: AlertTriangle, variant: 'outline', tone: 'text-purple-600' },
  { key: 'mark_resolved_operationally', label: 'Resolver operacionalmente', icon: XCircle, variant: 'outline', tone: 'text-slate-600' },
  { key: 'regularize_internally', label: 'Regularizar internamente', icon: Wrench, variant: 'outline', tone: 'text-blue-600' },
  { key: 'reset', label: 'Limpar override', icon: RotateCcw, variant: 'ghost', tone: 'text-slate-500' },
];

const Regularizations = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    search: '',
    only_micro_old: false,
    only_residual: false,
    only_low_values: false,
    min_amount: '',
    max_amount: '',
    min_days: '',
    max_days: '',
    sort_by: 'days_overdue',
    sort_dir: 'desc',
  });
  const [actionDialog, setActionDialog] = useState({ open: false, item: null, action: null, reason: '' });

  const buildParams = useCallback(() => {
    const p = new URLSearchParams();
    if (filters.search) p.set('search', filters.search);
    if (filters.only_micro_old) p.set('only_micro_old', 'true');
    if (filters.only_residual) p.set('only_residual', 'true');
    if (filters.only_low_values) p.set('only_low_values', 'true');
    if (filters.min_amount !== '') p.set('min_amount', filters.min_amount);
    if (filters.max_amount !== '') p.set('max_amount', filters.max_amount);
    if (filters.min_days !== '') p.set('min_days', filters.min_days);
    if (filters.max_days !== '') p.set('max_days', filters.max_days);
    p.set('sort_by', filters.sort_by);
    p.set('sort_dir', filters.sort_dir);
    return p.toString();
  }, [filters]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/finance/regularizations?${buildParams()}`, {
        headers: getAuthHeaders(),
      });
      setData(res.data);
    } catch (err) {
      console.error('Erro ao carregar regularizações:', err);
      toast.error('Erro ao carregar regularizações');
    } finally {
      setLoading(false);
    }
  }, [buildParams, getAuthHeaders]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const openAction = (item, actionKey) => {
    setActionDialog({ open: true, item, action: actionKey, reason: '' });
  };

  const confirmAction = async () => {
    const { item, action, reason } = actionDialog;
    if (!item || !action) return;
    try {
      await axios.post(
        `${API_URL}/api/finance/documents/${item.document_id}/action`,
        { action, reason: reason || null },
        { headers: getAuthHeaders() }
      );
      toast.success('Acção aplicada e agregados recalculados');
      setActionDialog({ open: false, item: null, action: null, reason: '' });
      fetchData();
    } catch (err) {
      console.error('Erro:', err);
      toast.error(err?.response?.data?.detail || 'Erro ao aplicar acção');
    }
  };

  const resetFilters = () => {
    setFilters({
      search: '',
      only_micro_old: false,
      only_residual: false,
      only_low_values: false,
      min_amount: '',
      max_amount: '',
      min_days: '',
      max_days: '',
      sort_by: 'days_overdue',
      sort_dir: 'desc',
    });
  };

  const items = data?.items || [];
  const activeFilterCount = useMemo(() => {
    let c = 0;
    ['only_micro_old', 'only_residual', 'only_low_values'].forEach((k) => { if (filters[k]) c++; });
    ['search', 'min_amount', 'max_amount', 'min_days', 'max_days'].forEach((k) => { if (filters[k] !== '') c++; });
    return c;
  }, [filters]);

  return (
    <div className="space-y-6" data-testid="regularizations-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Regularizações</h1>
          <p className="text-slate-500 text-sm">
            Documentos residuais, micro-saldos antigos e regularizações técnicas — contam na dívida contabilística mas ficam fora da cobrança operacional
          </p>
        </div>
        <Button variant="outline" onClick={fetchData} data-testid="regularizations-refresh-btn">
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Total Residual/Micro-Old</p>
              <p className="text-2xl font-bold text-slate-900" data-testid="regularizations-total-residual">
                {formatCurrency(data?.total_residual)}
              </p>
            </div>
            <div className="h-10 w-10 rounded-full bg-amber-100 flex items-center justify-center">
              <Coins className="h-5 w-5 text-amber-600" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Documentos</p>
              <p className="text-2xl font-bold text-slate-900" data-testid="regularizations-total-documents">
                {data?.total_documents ?? 0}
              </p>
            </div>
            <div className="h-10 w-10 rounded-full bg-orange-100 flex items-center justify-center">
              <FileText className="h-5 w-5 text-orange-600" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Clientes</p>
              <p className="text-2xl font-bold text-slate-900" data-testid="regularizations-total-clients">
                {data?.total_clients ?? 0}
              </p>
            </div>
            <div className="h-10 w-10 rounded-full bg-slate-100 flex items-center justify-center">
              <Users className="h-5 w-5 text-slate-600" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filtros */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Filter className="h-4 w-4" /> Filtros e Ordenação
            {activeFilterCount > 0 && (
              <Badge className="bg-orange-100 text-orange-800" data-testid="regularizations-active-filters-count">
                {activeFilterCount} activo{activeFilterCount > 1 ? 's' : ''}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <Input
            placeholder="Pesquisar cliente/código/nº doc"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            data-testid="regularizations-search-input"
          />
          <div className="flex gap-2">
            <Input
              type="number"
              placeholder="Valor mín. (€)"
              value={filters.min_amount}
              onChange={(e) => setFilters({ ...filters, min_amount: e.target.value })}
              data-testid="regularizations-min-amount-input"
            />
            <Input
              type="number"
              placeholder="Valor máx. (€)"
              value={filters.max_amount}
              onChange={(e) => setFilters({ ...filters, max_amount: e.target.value })}
              data-testid="regularizations-max-amount-input"
            />
          </div>
          <div className="flex gap-2">
            <Input
              type="number"
              placeholder="Dias mín."
              value={filters.min_days}
              onChange={(e) => setFilters({ ...filters, min_days: e.target.value })}
              data-testid="regularizations-min-days-input"
            />
            <Input
              type="number"
              placeholder="Dias máx."
              value={filters.max_days}
              onChange={(e) => setFilters({ ...filters, max_days: e.target.value })}
              data-testid="regularizations-max-days-input"
            />
          </div>
          <div className="flex gap-2">
            <Select
              value={filters.sort_by}
              onValueChange={(v) => setFilters({ ...filters, sort_by: v })}
            >
              <SelectTrigger data-testid="regularizations-sort-by">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="days_overdue">Dias vencidos</SelectItem>
                <SelectItem value="amount_open">Valor em aberto</SelectItem>
                <SelectItem value="client_residual_balance">Residual do cliente</SelectItem>
                <SelectItem value="client_name">Nome do cliente</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={filters.sort_dir}
              onValueChange={(v) => setFilters({ ...filters, sort_dir: v })}
            >
              <SelectTrigger className="w-24" data-testid="regularizations-sort-dir">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="desc">↓ Desc</SelectItem>
                <SelectItem value="asc">↑ Asc</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {/* Toggles */}
          <div className="col-span-full flex flex-wrap gap-2 items-center pt-2 border-t">
            <Button
              variant={filters.only_micro_old ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilters({ ...filters, only_micro_old: !filters.only_micro_old, only_residual: false })}
              data-testid="regularizations-toggle-micro-old"
            >
              Só micro-saldos antigos
            </Button>
            <Button
              variant={filters.only_residual ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilters({ ...filters, only_residual: !filters.only_residual, only_micro_old: false })}
              data-testid="regularizations-toggle-residual"
            >
              Só residuais ({'≤'}1€)
            </Button>
            <Button
              variant={filters.only_low_values ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilters({ ...filters, only_low_values: !filters.only_low_values })}
              data-testid="regularizations-toggle-low-values"
            >
              Só valores baixos ({'≤'}1€)
            </Button>
            <div className="ml-auto">
              <Button variant="ghost" size="sm" onClick={resetFilters} data-testid="regularizations-reset-filters">
                Limpar filtros
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabela */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            Documentos ({items.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b sticky top-0">
                <tr>
                  <th className="text-left p-3 font-medium text-slate-600">Cliente</th>
                  <th className="text-left p-3 font-medium text-slate-600">Cód.</th>
                  <th className="text-left p-3 font-medium text-slate-600">Documento</th>
                  <th className="text-right p-3 font-medium text-slate-600">Valor</th>
                  <th className="text-center p-3 font-medium text-slate-600">Dias</th>
                  <th className="text-right p-3 font-medium text-slate-600">Residual Cliente</th>
                  <th className="text-center p-3 font-medium text-slate-600">Nº Docs</th>
                  <th className="text-center p-3 font-medium text-slate-600">Classificação</th>
                  <th className="text-left p-3 font-medium text-slate-600">Sugestão</th>
                  <th className="text-center p-3 font-medium text-slate-600">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {items.map((item) => {
                  const cls = CLASSIFICATION_LABELS[item.classification] || CLASSIFICATION_LABELS.residual;
                  const sugStyle = SUGGESTION_STYLES[item.suggestion_code] || SUGGESTION_STYLES.review;
                  return (
                    <tr key={item.document_id} className="hover:bg-slate-50" data-testid={`regularization-row-${item.document_number}`}>
                      <td className="p-3 font-medium">
                        <button
                          onClick={() => navigate(`/finance/clients/${item.client_id}`)}
                          className="text-left hover:text-orange-600"
                          data-testid={`regularization-open-client-${item.genes_code}`}
                        >
                          {item.client_name}
                        </button>
                      </td>
                      <td className="p-3 text-slate-500">#{item.genes_code}</td>
                      <td className="p-3">
                        <span className="text-slate-700">{item.document_type} {item.document_number}</span>
                        {item.due_date && (
                          <div className="text-xs text-slate-400">Venc: {item.due_date}</div>
                        )}
                      </td>
                      <td className="p-3 text-right font-semibold text-amber-700">
                        {formatCurrency(item.amount_open)}
                      </td>
                      <td className="p-3 text-center text-slate-700">{item.days_overdue}</td>
                      <td className="p-3 text-right text-slate-600">
                        {formatCurrency(item.client_residual_balance)}
                      </td>
                      <td className="p-3 text-center text-slate-600">{item.client_residual_document_count}</td>
                      <td className="p-3 text-center">
                        <Badge className={cls.style}>{cls.label}</Badge>
                        {item.manual_action && (
                          <div className="text-xs text-slate-400 mt-1">override: {item.manual_action}</div>
                        )}
                      </td>
                      <td className="p-3">
                        <span className={`inline-block px-2 py-1 rounded text-xs ${sugStyle}`}>
                          {item.suggestion_label}
                        </span>
                      </td>
                      <td className="p-3">
                        <div className="flex flex-wrap gap-1 justify-center">
                          {ACTION_OPTIONS.map((opt) => {
                            const Icon = opt.icon;
                            return (
                              <Button
                                key={opt.key}
                                size="sm"
                                variant={opt.variant}
                                onClick={() => openAction(item, opt.key)}
                                title={opt.label}
                                className={`h-7 w-7 p-0 ${opt.tone}`}
                                data-testid={`regularization-action-${opt.key}-${item.document_number}`}
                              >
                                <Icon className="h-3.5 w-3.5" />
                              </Button>
                            );
                          })}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => navigate(`/finance/clients/${item.client_id}`)}
                            className="h-7 w-7 p-0"
                            title="Abrir ficha"
                            data-testid={`regularization-open-detail-${item.document_number}`}
                          >
                            <ArrowRight className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {items.length === 0 && !loading && (
                  <tr>
                    <td colSpan={10} className="p-8 text-center text-slate-500">
                      Sem documentos correspondentes aos filtros
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Dialog acção */}
      <Dialog open={actionDialog.open} onOpenChange={(open) => !open && setActionDialog({ open: false, item: null, action: null, reason: '' })}>
        <DialogContent data-testid="regularization-action-dialog">
          <DialogHeader>
            <DialogTitle>
              {ACTION_OPTIONS.find((a) => a.key === actionDialog.action)?.label || 'Confirmar acção'}
            </DialogTitle>
          </DialogHeader>
          {actionDialog.item && (
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-slate-500">Cliente:</span>{' '}
                <span className="font-medium">{actionDialog.item.client_name}</span>
              </div>
              <div>
                <span className="text-slate-500">Documento:</span>{' '}
                <span className="font-medium">{actionDialog.item.document_type} {actionDialog.item.document_number}</span>
                {' · '}
                <span className="text-amber-700 font-semibold">{formatCurrency(actionDialog.item.amount_open)}</span>
                {' · '}
                <span className="text-slate-600">{actionDialog.item.days_overdue} dias</span>
              </div>
              <Textarea
                placeholder="Motivo / notas (opcional)"
                value={actionDialog.reason}
                onChange={(e) => setActionDialog({ ...actionDialog, reason: e.target.value })}
                rows={3}
                data-testid="regularization-action-reason-input"
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setActionDialog({ open: false, item: null, action: null, reason: '' })}>
              Cancelar
            </Button>
            <Button onClick={confirmAction} data-testid="regularization-action-confirm-btn">
              Confirmar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Regularizations;
