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

const FinanceClients = () => {
  const { getAuthHeaders } = useAuth();
  const [clients, setClients] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [searchTerm, setSearchTerm] = useState('');
  const [filters, setFilters] = useState({
    status: 'all',
    traffic_light: 'all',
    has_overdue: 'all',
    is_blocked: ''
  });
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

  const clearFilters = () => {
    setFilters({
      status: 'all',
      traffic_light: 'all',
      has_overdue: 'all',
      is_blocked: ''
    });
    setSearchTerm('');
    setPage(1);
  };

  const hasActiveFilters = Object.values(filters).some(v => v && v !== 'all') || searchTerm;

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
          <CardContent className="p-4">
            <div className="flex flex-wrap gap-4 items-end">
              <div className="space-y-1">
                <label className="text-sm font-medium">Estado</label>
                <Select 
                  value={filters.status} 
                  onValueChange={(v) => { setFilters({...filters, status: v}); setPage(1); }}
                >
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="EM_COBRANCA">Em Cobrança</SelectItem>
                    <SelectItem value="PROMESSA_ATIVA">Promessa Ativa</SelectItem>
                    <SelectItem value="PROMESSA_FALHADA">Promessa Falhada</SelectItem>
                    <SelectItem value="EM_DISPUTA">Em Disputa</SelectItem>
                    <SelectItem value="BLOQUEADO">Bloqueado</SelectItem>
                    <SelectItem value="OK">OK</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-1">
                <label className="text-sm font-medium">Semáforo</label>
                <Select 
                  value={filters.traffic_light} 
                  onValueChange={(v) => { setFilters({...filters, traffic_light: v}); setPage(1); }}
                >
                  <SelectTrigger className="w-32">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
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

              <div className="space-y-1">
                <label className="text-sm font-medium">Vencido</label>
                <Select 
                  value={filters.has_overdue} 
                  onValueChange={(v) => { setFilters({...filters, has_overdue: v}); setPage(1); }}
                >
                  <SelectTrigger className="w-32">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="true">Com vencido</SelectItem>
                    <SelectItem value="false">Sem vencido</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {hasActiveFilters && (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  <X className="h-4 w-4 mr-1" />
                  Limpar
                </Button>
              )}
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
