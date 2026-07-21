import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import {
  Select, SelectTrigger, SelectContent, SelectItem, SelectValue
} from '../../components/ui/select';
import axios from 'axios';
import {
  AlertTriangle,
  RefreshCw,
  Search,
  ArrowRight,
  Clock,
  Euro,
  Filter,
  X
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
    <span className={`inline-block w-3 h-3 rounded-full ${colors[light] || 'bg-gray-400'}`} 
          title={light} />
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
    OK: 'bg-green-100 text-green-800'
  };
  
  const labels = {
    EM_COBRANCA: 'Em Cobrança',
    PROMESSA_ATIVA: 'Promessa Ativa',
    PROMESSA_FALHADA: 'Promessa Falhada',
    EM_DISPUTA: 'Em Disputa',
    BLOQUEIO_SUGERIDO: 'Bloqueio Sugerido',
    BLOQUEADO: 'Bloqueado',
    OK: 'OK'
  };
  
  return (
    <Badge className={styles[status] || 'bg-slate-100 text-slate-800'}>
      {labels[status] || status}
    </Badge>
  );
};

const formatCurrency = (value) => {
  return new Intl.NumberFormat('pt-PT', {
    style: 'currency',
    currency: 'EUR'
  }).format(value || 0);
};

const DEFAULT_FILTERS = {
  search: '',
  min_overdue: '',
  max_overdue: '',
  min_days: '',
  max_days: '',
  only_low_values: false,
  only_old_docs: false,
  financial_status: '',
  sort_by: 'priority',
};

const CollectionsToday = () => {
  const { getAuthHeaders } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [showFilters, setShowFilters] = useState(false);

  const buildParams = useCallback(() => {
    const p = new URLSearchParams();
    if (filters.search) p.set('search', filters.search);
    if (filters.min_overdue !== '') p.set('min_overdue', filters.min_overdue);
    if (filters.max_overdue !== '') p.set('max_overdue', filters.max_overdue);
    if (filters.min_days !== '') p.set('min_days', filters.min_days);
    if (filters.max_days !== '') p.set('max_days', filters.max_days);
    if (filters.only_low_values) p.set('only_low_values', 'true');
    if (filters.only_old_docs) p.set('only_old_docs', 'true');
    if (filters.financial_status) p.set('financial_status', filters.financial_status);
    p.set('sort_by', filters.sort_by);
    return p.toString();
  }, [filters]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_URL}/api/finance/collections/today?${buildParams()}`, {
        headers: getAuthHeaders()
      });
      setData(response.data);
    } catch (err) {
      console.error('Erro ao carregar cobranças:', err);
    } finally {
      setLoading(false);
    }
  }, [buildParams, getAuthHeaders]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const items = data?.items || [];

  const activeFilterCount = useMemo(() => {
    let c = 0;
    ['only_low_values', 'only_old_docs'].forEach((k) => { if (filters[k]) c++; });
    ['min_overdue', 'max_overdue', 'min_days', 'max_days', 'financial_status'].forEach((k) => {
      if (filters[k] !== '' && filters[k] !== null && filters[k] !== undefined) c++;
    });
    if (filters.sort_by !== 'priority') c++;
    return c;
  }, [filters]);

  const resetFilters = () => setFilters(DEFAULT_FILTERS);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-orange-600" />
      </div>
    );
  }

  // Blocked state
  if (data?.is_blocked) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Cobranças de Hoje</h1>
          <p className="text-slate-500 text-sm">Lista prioritária de contactos</p>
        </div>
        
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <AlertTriangle className="h-12 w-12 text-red-600 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-red-800 mb-2">Cobranças Bloqueadas</h2>
          <p className="text-red-600 mb-4">{data.block_message}</p>
          <Link to="/finance/imports">
            <Button>
              Importar Dados Atualizados
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="collections-today-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Cobranças de Hoje</h1>
          <p className="text-slate-500 text-sm">
            {data?.total_items || 0} clientes · {formatCurrency(data?.total_value)} em cobrança
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Pesquisar..."
              value={filters.search}
              onChange={(e) => setFilters({ ...filters, search: e.target.value })}
              className="pl-9 w-64"
              data-testid="collections-search-input"
            />
          </div>
          <Select value={filters.sort_by} onValueChange={(v) => setFilters({ ...filters, sort_by: v })}>
            <SelectTrigger className="w-56" data-testid="collections-sort-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="priority">Prioridade</SelectItem>
              <SelectItem value="overdue_desc">Vencido ↓</SelectItem>
              <SelectItem value="overdue_asc">Vencido ↑</SelectItem>
              <SelectItem value="total_desc">Saldo total ↓</SelectItem>
              <SelectItem value="total_asc">Saldo total ↑</SelectItem>
              <SelectItem value="days_desc">Dias vencidos ↓</SelectItem>
              <SelectItem value="days_asc">Dias vencidos ↑</SelectItem>
              <SelectItem value="doc_count">Nº documentos</SelectItem>
              <SelectItem value="last_action">Último contacto</SelectItem>
              <SelectItem value="financial_status">Estado financeiro</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant={showFilters || activeFilterCount > 0 ? 'default' : 'outline'}
            onClick={() => setShowFilters((v) => !v)}
            data-testid="collections-toggle-filters"
          >
            <Filter className="h-4 w-4 mr-1" /> Filtros
            {activeFilterCount > 0 && (
              <Badge className="ml-2 bg-white text-orange-700">{activeFilterCount}</Badge>
            )}
          </Button>
          <Button variant="outline" size="icon" onClick={fetchData} data-testid="collections-refresh-btn">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Filtros avançados */}
      {showFilters && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Filter className="h-4 w-4" /> Filtros avançados
              </span>
              <Button variant="ghost" size="sm" onClick={resetFilters} data-testid="collections-reset-filters">
                <X className="h-3.5 w-3.5 mr-1" /> Limpar
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="flex gap-2">
              <Input
                type="number"
                placeholder="Vencido mín. (€)"
                value={filters.min_overdue}
                onChange={(e) => setFilters({ ...filters, min_overdue: e.target.value })}
                data-testid="collections-min-overdue-input"
              />
              <Input
                type="number"
                placeholder="Vencido máx. (€)"
                value={filters.max_overdue}
                onChange={(e) => setFilters({ ...filters, max_overdue: e.target.value })}
                data-testid="collections-max-overdue-input"
              />
            </div>
            <div className="flex gap-2">
              <Input
                type="number"
                placeholder="Dias mín."
                value={filters.min_days}
                onChange={(e) => setFilters({ ...filters, min_days: e.target.value })}
                data-testid="collections-min-days-input"
              />
              <Input
                type="number"
                placeholder="Dias máx."
                value={filters.max_days}
                onChange={(e) => setFilters({ ...filters, max_days: e.target.value })}
                data-testid="collections-max-days-input"
              />
            </div>
            <Select
              value={filters.financial_status || 'ANY'}
              onValueChange={(v) => setFilters({ ...filters, financial_status: v === 'ANY' ? '' : v })}
            >
              <SelectTrigger data-testid="collections-financial-status-select">
                <SelectValue placeholder="Estado financeiro" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ANY">Todos os estados</SelectItem>
                <SelectItem value="EM_COBRANCA">Em Cobrança</SelectItem>
                <SelectItem value="PROMESSA_ATIVA">Promessa Ativa</SelectItem>
                <SelectItem value="PROMESSA_FALHADA">Promessa Falhada</SelectItem>
                <SelectItem value="EM_DISPUTA">Em Disputa</SelectItem>
                <SelectItem value="BLOQUEIO_SUGERIDO">Bloqueio Sugerido</SelectItem>
                <SelectItem value="BLOQUEADO">Bloqueado</SelectItem>
              </SelectContent>
            </Select>
            <div className="col-span-full flex flex-wrap gap-2 pt-2 border-t">
              <Button
                size="sm"
                variant={filters.only_low_values ? 'default' : 'outline'}
                onClick={() => setFilters({ ...filters, only_low_values: !filters.only_low_values })}
                data-testid="collections-toggle-low-values"
              >
                Só valores baixos ({'≤'}5€)
              </Button>
              <Button
                size="sm"
                variant={filters.only_old_docs ? 'default' : 'outline'}
                onClick={() => setFilters({ ...filters, only_old_docs: !filters.only_old_docs })}
                data-testid="collections-toggle-old-docs"
              >
                Só documentos antigos (&gt;365 dias)
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Collections List */}
      <div className="space-y-3">
        {items.map((item) => (
          <Card key={item.client_id} className="hover:shadow-md transition-shadow">
            <CardContent className="p-4">
              <div className="flex items-start gap-4">
                {/* Traffic Light & Info */}
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <div className="mt-1">
                    <TrafficLightBadge light={item.traffic_light} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link 
                        to={`/finance/clients/${item.client_id}`}
                        className="font-semibold text-slate-900 hover:text-orange-600 truncate"
                        data-testid={`collections-open-client-${item.genes_code}`}
                      >
                        {item.client_name}
                      </Link>
                      <span className="text-sm text-slate-500">#{item.genes_code}</span>
                      <StatusBadge status={item.financial_status} />
                      {item.has_failed_promise && (
                        <Badge variant="destructive" className="text-xs">
                          Promessa Falhada
                        </Badge>
                      )}
                      {item.has_active_promise && (
                        <Badge className="bg-blue-100 text-blue-800 text-xs">
                          Promessa Ativa
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-2 text-sm text-slate-600 flex-wrap">
                      <span className="flex items-center gap-1">
                        <Euro className="h-4 w-4" />
                        <span className="font-semibold text-red-600">
                          {formatCurrency(item.overdue_collectable)}
                        </span>
                        <span className="text-slate-400">vencido</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-4 w-4" />
                        {item.oldest_overdue_days} dias
                      </span>
                      {item.total_balance > 0 && (
                        <span className="text-slate-400">
                          Saldo total: {formatCurrency(item.total_balance)}
                        </span>
                      )}
                      {item.last_action_at && (
                        <span className="text-slate-400">
                          Último contacto: {new Date(item.last_action_at).toLocaleDateString('pt-PT')}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2">
                  <Link to={`/finance/clients/${item.client_id}`}>
                    <Button size="sm">
                      Abrir Ficha
                      <ArrowRight className="h-4 w-4 ml-1" />
                    </Button>
                  </Link>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}

        {items.length === 0 && !loading && (
          <Card>
            <CardContent className="p-8 text-center">
              <p className="text-slate-500">
                {activeFilterCount > 0 ? 'Nenhum cliente corresponde aos filtros' : 'Nenhuma cobrança pendente para hoje'}
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default CollectionsToday;
