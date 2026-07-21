import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
import axios from 'axios';
import {
  Search,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Filter,
  X,
  ArrowUpDown
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TrafficLightBadge = ({ light }) => {
  const colors = {
    GREEN: 'bg-green-500',
    YELLOW: 'bg-yellow-500',
    ORANGE: 'bg-orange-500',
    RED: 'bg-red-500',
    CRITICAL: 'bg-red-700 animate-pulse'
  };
  
  return (
    <span className={`inline-block w-3 h-3 rounded-full ${colors[light] || 'bg-gray-400'}`} />
  );
};

const StatusBadge = ({ status }) => {
  const styles = {
    EM_COBRANCA: 'bg-orange-100 text-orange-800',
    PROMESSA_ATIVA: 'bg-blue-100 text-blue-800',
    PROMESSA_FALHADA: 'bg-red-100 text-red-800',
    EM_DISPUTA: 'bg-purple-100 text-purple-800',
    BLOQUEIO_SUGERIDO: 'bg-yellow-100 text-yellow-800',
    BLOQUEADO: 'bg-red-200 text-red-900',
    REGULARIZACAO_TECNICA: 'bg-slate-100 text-slate-800',
    OK: 'bg-green-100 text-green-800'
  };
  
  const labels = {
    EM_COBRANCA: 'Em Cobrança',
    PROMESSA_ATIVA: 'Promessa',
    PROMESSA_FALHADA: 'Falhada',
    EM_DISPUTA: 'Disputa',
    BLOQUEIO_SUGERIDO: 'Bloq. Sugerido',
    BLOQUEADO: 'Bloqueado',
    REGULARIZACAO_TECNICA: 'Regularização',
    OK: 'OK'
  };
  
  return (
    <Badge className={`text-xs ${styles[status] || 'bg-slate-100'}`}>
      {labels[status] || status}
    </Badge>
  );
};

const formatCurrency = (value) => {
  return new Intl.NumberFormat('pt-PT', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value || 0);
};

const DEFAULT_FILTERS = {
  status: 'all',
  traffic_light: 'all',
  has_overdue: 'all',
  is_blocked: '',
  customer_segment: 'all',
  aging_bucket: 'all',
  amount_preset: 'all',
  min_overdue: '',
  max_overdue: '',
  min_days: '',
  max_days: '',
  no_contact_days: '',
  never_contacted: false,
  missing_finance_email: false,
  has_active_promise: '',
  has_failed_promise: '',
  has_residual: '',
  sort_by: 'name',
};

const AMOUNT_PRESETS = [
  { key: 'all',      label: 'Todos',       min: '', max: '' },
  { key: 'lt10',     label: 'Até 10 €',    min: '', max: 10 },
  { key: '10_50',    label: '10-50 €',     min: 10, max: 50 },
  { key: '50_100',   label: '50-100 €',    min: 50, max: 100 },
  { key: '100_500',  label: '100-500 €',   min: 100, max: 500 },
  { key: 'gt500',    label: '+500 €',      min: 500, max: '' },
  { key: 'gt1000',   label: '+1.000 €',    min: 1000, max: '' },
];

const AGING_BUCKETS = [
  { key: 'all',   label: 'Todos' },
  { key: '0_30',  label: '0–30 dias' },
  { key: '31_60', label: '31–60 dias' },
  { key: '61_90', label: '61–90 dias' },
  { key: '90p',   label: '+90 dias' },
  { key: '120p',  label: '+120 dias' },
  { key: '180p',  label: '+180 dias' },
  { key: '365p',  label: '+365 dias' },
];

const SEGMENTS = ['PARTICULAR', 'EMPRESA', 'FROTA', 'SEGURADORA', 'LEASING', 'CONTA_CORRENTE', 'OUTRO', 'UNKNOWN'];

const FinanceClients = () => {
  const { getAuthHeaders } = useAuth();
  const [clients, setClients] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [searchTerm, setSearchTerm] = useState('');
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [showFilters, setShowFilters] = useState(false);

  const fetchClients = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString()
      });

      if (searchTerm) params.append('search', searchTerm);
      if (filters.status && filters.status !== 'all') params.append('status', filters.status);
      if (filters.traffic_light && filters.traffic_light !== 'all') params.append('traffic_light', filters.traffic_light);
      if (filters.has_overdue && filters.has_overdue !== 'all') params.append('has_overdue', filters.has_overdue);
      if (filters.is_blocked) params.append('is_blocked', filters.is_blocked);
      if (filters.customer_segment && filters.customer_segment !== 'all') params.append('customer_segment', filters.customer_segment);
      if (filters.aging_bucket && filters.aging_bucket !== 'all') params.append('aging_bucket', filters.aging_bucket);
      if (filters.min_overdue !== '') params.append('min_overdue', filters.min_overdue);
      if (filters.max_overdue !== '') params.append('max_overdue', filters.max_overdue);
      if (filters.min_days !== '') params.append('min_days', filters.min_days);
      if (filters.max_days !== '') params.append('max_days', filters.max_days);
      if (filters.no_contact_days !== '') params.append('no_contact_days', filters.no_contact_days);
      if (filters.never_contacted) params.append('never_contacted', 'true');
      if (filters.missing_finance_email) params.append('missing_finance_email', 'true');
      if (filters.has_active_promise !== '') params.append('has_active_promise', filters.has_active_promise);
      if (filters.has_failed_promise !== '') params.append('has_failed_promise', filters.has_failed_promise);
      if (filters.has_residual !== '') params.append('has_residual', filters.has_residual);
      if (filters.sort_by) params.append('sort_by', filters.sort_by);

      const response = await axios.get(`${API_URL}/api/finance/clients?${params}`, {
        headers: getAuthHeaders()
      });
      setClients(response.data.clients);
      setTotal(response.data.total);
    } catch (err) {
      console.error('Erro ao carregar clientes:', err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchTerm, filters, getAuthHeaders]);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      fetchClients();
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [fetchClients]);

  const totalPages = Math.ceil(total / pageSize);

  const applyAmountPreset = (key) => {
    const p = AMOUNT_PRESETS.find((x) => x.key === key) || AMOUNT_PRESETS[0];
    setFilters((f) => ({
      ...f,
      amount_preset: key,
      min_overdue: p.min === '' ? '' : String(p.min),
      max_overdue: p.max === '' ? '' : String(p.max),
    }));
    setPage(1);
  };

  const clearFilters = () => {
    setFilters(DEFAULT_FILTERS);
    setSearchTerm('');
    setPage(1);
  };

  const hasActiveFilters =
    searchTerm ||
    Object.entries(filters).some(([k, v]) => {
      if (k === 'sort_by') return v !== 'name';
      if (typeof v === 'boolean') return v;
      return v && v !== 'all';
    });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Clientes Financeiros</h1>
          <p className="text-slate-500 text-sm">{total} clientes encontrados</p>
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Nome ou código..."
              value={searchTerm}
              onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
              className="pl-9 w-64"
            />
          </div>
          <Button 
            variant={showFilters ? "default" : "outline"} 
            size="icon"
            onClick={() => setShowFilters(!showFilters)}
            data-testid="clients-toggle-filters"
          >
            <Filter className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" onClick={fetchClients}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <Card>
          <CardContent className="p-4 space-y-4">
            {/* Amount presets */}
            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-sm text-slate-500 mr-1">Valor:</span>
              {AMOUNT_PRESETS.map((p) => (
                <Button
                  key={p.key}
                  size="sm"
                  variant={filters.amount_preset === p.key ? 'default' : 'outline'}
                  onClick={() => applyAmountPreset(p.key)}
                  data-testid={`clients-preset-${p.key}`}
                >
                  {p.label}
                </Button>
              ))}
            </div>

            {/* Aging presets */}
            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-sm text-slate-500 mr-1">Dias:</span>
              {AGING_BUCKETS.map((b) => (
                <Button
                  key={b.key}
                  size="sm"
                  variant={filters.aging_bucket === b.key ? 'default' : 'outline'}
                  onClick={() => { setFilters({ ...filters, aging_bucket: b.key }); setPage(1); }}
                  data-testid={`clients-aging-${b.key}`}
                >
                  {b.label}
                </Button>
              ))}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {/* Estado */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500">Estado financeiro</label>
                <Select value={filters.status} onValueChange={(v) => { setFilters({...filters, status: v}); setPage(1); }}>
                  <SelectTrigger data-testid="clients-status-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="EM_COBRANCA">Em Cobrança</SelectItem>
                    <SelectItem value="PROMESSA_ATIVA">Promessa Ativa</SelectItem>
                    <SelectItem value="PROMESSA_FALHADA">Promessa Falhada</SelectItem>
                    <SelectItem value="EM_DISPUTA">Em Disputa</SelectItem>
                    <SelectItem value="BLOQUEIO_SUGERIDO">Bloqueio Sugerido</SelectItem>
                    <SelectItem value="BLOQUEADO">Bloqueado</SelectItem>
                    <SelectItem value="REGULARIZACAO_TECNICA">Regularização Técnica</SelectItem>
                    <SelectItem value="OK">OK</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Semáforo */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500">Semáforo</label>
                <Select value={filters.traffic_light} onValueChange={(v) => { setFilters({...filters, traffic_light: v}); setPage(1); }}>
                  <SelectTrigger data-testid="clients-traffic-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="CRITICAL">Crítico</SelectItem>
                    <SelectItem value="RED">Vermelho</SelectItem>
                    <SelectItem value="ORANGE">Laranja</SelectItem>
                    <SelectItem value="YELLOW">Amarelo</SelectItem>
                    <SelectItem value="GREEN">Verde</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Segmento */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500">Segmento</label>
                <Select value={filters.customer_segment} onValueChange={(v) => { setFilters({...filters, customer_segment: v}); setPage(1); }}>
                  <SelectTrigger data-testid="clients-segment-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    {SEGMENTS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              {/* Ordenação */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500">Ordenar por</label>
                <Select value={filters.sort_by} onValueChange={(v) => { setFilters({...filters, sort_by: v}); setPage(1); }}>
                  <SelectTrigger data-testid="clients-sort-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="name">Nome</SelectItem>
                    <SelectItem value="overdue_desc">Vencido ↓</SelectItem>
                    <SelectItem value="overdue_asc">Vencido ↑</SelectItem>
                    <SelectItem value="total_desc">Saldo total ↓</SelectItem>
                    <SelectItem value="total_asc">Saldo total ↑</SelectItem>
                    <SelectItem value="days_desc">Maior atraso ↓</SelectItem>
                    <SelectItem value="days_asc">Maior atraso ↑</SelectItem>
                    <SelectItem value="last_action">Último contacto</SelectItem>
                    <SelectItem value="doc_count">Nº documentos</SelectItem>
                    <SelectItem value="financial_status">Estado financeiro</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Vencido / Bloqueio */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500">Vencido</label>
                <Select value={filters.has_overdue} onValueChange={(v) => { setFilters({...filters, has_overdue: v}); setPage(1); }}>
                  <SelectTrigger data-testid="clients-overdue-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="true">Com vencido</SelectItem>
                    <SelectItem value="false">Sem vencido</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500">Bloqueio</label>
                <Select value={filters.is_blocked || 'all'} onValueChange={(v) => { setFilters({...filters, is_blocked: v === 'all' ? '' : v}); setPage(1); }}>
                  <SelectTrigger data-testid="clients-blocked-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="true">Bloqueados</SelectItem>
                    <SelectItem value="false">Não bloqueados</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Sem contacto */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500">Sem contacto há (dias)</label>
                <Input
                  type="number"
                  placeholder="Ex: 30"
                  value={filters.no_contact_days}
                  onChange={(e) => { setFilters({...filters, no_contact_days: e.target.value}); setPage(1); }}
                  data-testid="clients-no-contact-days-input"
                />
              </div>

              {/* min/max valor override */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-500">Vencido min - max (€)</label>
                <div className="flex gap-1">
                  <Input
                    type="number" placeholder="mín"
                    value={filters.min_overdue}
                    onChange={(e) => { setFilters({...filters, min_overdue: e.target.value, amount_preset: ''}); setPage(1); }}
                    data-testid="clients-min-overdue-input"
                  />
                  <Input
                    type="number" placeholder="máx"
                    value={filters.max_overdue}
                    onChange={(e) => { setFilters({...filters, max_overdue: e.target.value, amount_preset: ''}); setPage(1); }}
                    data-testid="clients-max-overdue-input"
                  />
                </div>
              </div>
            </div>

            {/* Toggles */}
            <div className="flex flex-wrap gap-2 items-center pt-2 border-t">
              <Button
                size="sm"
                variant={filters.never_contacted ? 'default' : 'outline'}
                onClick={() => { setFilters({...filters, never_contacted: !filters.never_contacted}); setPage(1); }}
                data-testid="clients-toggle-never-contacted"
              >
                Nunca contactado
              </Button>
              <Button
                size="sm"
                variant={filters.missing_finance_email ? 'default' : 'outline'}
                onClick={() => { setFilters({...filters, missing_finance_email: !filters.missing_finance_email}); setPage(1); }}
                data-testid="clients-toggle-missing-email"
              >
                Email financeiro em falta
              </Button>
              <Button
                size="sm"
                variant={filters.has_active_promise === 'true' ? 'default' : 'outline'}
                onClick={() => { setFilters({...filters, has_active_promise: filters.has_active_promise === 'true' ? '' : 'true'}); setPage(1); }}
                data-testid="clients-toggle-active-promise"
              >
                Promessa ativa
              </Button>
              <Button
                size="sm"
                variant={filters.has_failed_promise === 'true' ? 'default' : 'outline'}
                onClick={() => { setFilters({...filters, has_failed_promise: filters.has_failed_promise === 'true' ? '' : 'true'}); setPage(1); }}
                data-testid="clients-toggle-failed-promise"
              >
                Promessa falhada
              </Button>
              <Button
                size="sm"
                variant={filters.has_residual === 'true' ? 'default' : 'outline'}
                onClick={() => { setFilters({...filters, has_residual: filters.has_residual === 'true' ? '' : 'true'}); setPage(1); }}
                data-testid="clients-toggle-residual"
              >
                Com residuais
              </Button>
              <div className="ml-auto">
                {hasActiveFilters && (
                  <Button variant="ghost" size="sm" onClick={clearFilters} data-testid="clients-reset-filters">
                    <X className="h-4 w-4 mr-1" /> Limpar
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50 border-b">
              <tr>
                <th className="text-left p-3 font-medium text-slate-600 text-sm">Cliente</th>
                <th className="text-left p-3 font-medium text-slate-600 text-sm">Código</th>
                <th className="text-right p-3 font-medium text-slate-600 text-sm">Saldo</th>
                <th className="text-right p-3 font-medium text-slate-600 text-sm">Vencido</th>
                <th className="text-center p-3 font-medium text-slate-600 text-sm">Dias</th>
                <th className="text-center p-3 font-medium text-slate-600 text-sm">Estado</th>
                <th className="text-center p-3 font-medium text-slate-600 text-sm w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {clients.map((client) => (
                <tr key={client.id} className="hover:bg-slate-50">
                  <td className="p-3">
                    <Link 
                      to={`/finance/clients/${client.id}`}
                      className="flex items-center gap-2 hover:text-orange-600"
                    >
                      <TrafficLightBadge light={client.traffic_light} />
                      <span className="font-medium">{client.name}</span>
                    </Link>
                  </td>
                  <td className="p-3 text-slate-500 text-sm">{client.genes_code}</td>
                  <td className="p-3 text-right font-medium">
                    {formatCurrency(client.total_balance)}
                  </td>
                  <td className="p-3 text-right">
                    <span className={client.overdue_balance_collectable > 0 ? 'text-red-600 font-semibold' : 'text-slate-400'}>
                      {formatCurrency(client.overdue_balance_collectable)}
                    </span>
                  </td>
                  <td className="p-3 text-center text-sm">
                    {client.oldest_overdue_days > 0 ? (
                      <span className={client.oldest_overdue_days > 60 ? 'text-red-600 font-medium' : ''}>
                        {client.oldest_overdue_days}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="p-3 text-center">
                    <StatusBadge status={client.financial_status} />
                  </td>
                  <td className="p-3 text-center">
                    <Link to={`/finance/clients/${client.id}`}>
                      <Button variant="ghost" size="sm">
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </Link>
                  </td>
                </tr>
              ))}
              {clients.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-slate-500">
                    Nenhum cliente encontrado
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between p-4 border-t">
            <p className="text-sm text-slate-500">
              Página {page} de {totalPages}
            </p>
            <div className="flex gap-2">
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default FinanceClients;
