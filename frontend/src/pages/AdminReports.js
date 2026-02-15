import { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { 
  BarChart3, 
  TrendingUp,
  Users,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Euro,
  Filter,
  Download,
  RefreshCw
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const AdminReports = () => {
  const { getAuthHeaders } = useAuth();
  
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [filters, setFilters] = useState({
    start_date: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    status: '',
    type: '',
    assigned_to: ''
  });
  
  const [users, setUsers] = useState([]);
  const [ticketTypes, setTicketTypes] = useState([]);

  useEffect(() => {
    fetchUsers();
    fetchTicketTypes();
    generateReport();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/users`, { headers: getAuthHeaders() });
      setUsers(response.data);
    } catch (error) {
      console.error('Error fetching users:', error);
    }
  };

  const fetchTicketTypes = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/admin/ticket-types`, { headers: getAuthHeaders() });
      setTicketTypes(response.data);
    } catch (error) {
      console.error('Error fetching ticket types:', error);
    }
  };

  const generateReport = async () => {
    setLoading(true);
    try {
      const filterParams = {
        ...filters,
        status: filters.status || null,
        type: filters.type || null,
        assigned_to: filters.assigned_to || null
      };
      
      const response = await axios.post(
        `${API_URL}/api/admin/reports`,
        filterParams,
        { headers: getAuthHeaders() }
      );
      setReport(response.data);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao gerar relatório');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('pt-PT', { 
      style: 'currency', 
      currency: 'EUR' 
    }).format(value);
  };

  const getStatusColor = (status) => {
    const colors = {
      'ABERTO': 'bg-emerald-100 text-emerald-700',
      'EM_TRATAMENTO': 'bg-blue-100 text-blue-700',
      'AGUARDA_CLIENTE': 'bg-amber-100 text-amber-700',
      'FECHADO': 'bg-zinc-100 text-zinc-700'
    };
    return colors[status] || 'bg-zinc-100 text-zinc-700';
  };

  const getStatusLabel = (status) => {
    const labels = {
      'ABERTO': 'Aberto',
      'EM_TRATAMENTO': 'Em Tratamento',
      'AGUARDA_CLIENTE': 'Aguarda Cliente',
      'FECHADO': 'Fechado'
    };
    return labels[status] || status;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">
            Relatórios
          </h1>
          <p className="text-zinc-500 mt-1">
            Análise de desempenho e métricas de tickets
          </p>
        </div>
        <Button 
          onClick={generateReport} 
          disabled={loading}
          className="bg-orange-600 hover:bg-orange-700"
          data-testid="refresh-report-btn"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Filtros
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="space-y-2">
              <Label>Data Início</Label>
              <Input
                type="date"
                value={filters.start_date}
                onChange={(e) => setFilters({ ...filters, start_date: e.target.value })}
                data-testid="filter-start-date"
              />
            </div>
            <div className="space-y-2">
              <Label>Data Fim</Label>
              <Input
                type="date"
                value={filters.end_date}
                onChange={(e) => setFilters({ ...filters, end_date: e.target.value })}
                data-testid="filter-end-date"
              />
            </div>
            <div className="space-y-2">
              <Label>Estado</Label>
              <Select value={filters.status} onValueChange={(v) => setFilters({ ...filters, status: v === 'all' ? '' : v })}>
                <SelectTrigger data-testid="filter-status">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="ABERTO">Aberto</SelectItem>
                  <SelectItem value="EM_TRATAMENTO">Em Tratamento</SelectItem>
                  <SelectItem value="AGUARDA_CLIENTE">Aguarda Cliente</SelectItem>
                  <SelectItem value="FECHADO">Fechado</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Tipo</Label>
              <Select value={filters.type} onValueChange={(v) => setFilters({ ...filters, type: v === 'all' ? '' : v })}>
                <SelectTrigger data-testid="filter-type">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {ticketTypes.map((t) => (
                    <SelectItem key={t.code} value={t.code}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Atribuído a</Label>
              <Select value={filters.assigned_to} onValueChange={(v) => setFilters({ ...filters, assigned_to: v === 'all' ? '' : v })}>
                <SelectTrigger data-testid="filter-assigned">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {users.filter(u => u.role !== 'ADMIN').map((u) => (
                    <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex justify-end mt-4">
            <Button onClick={generateReport} disabled={loading} data-testid="apply-filters-btn">
              Aplicar Filtros
            </Button>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="w-12 h-12 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : report ? (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-500">Total de Tickets</p>
                    <p className="text-3xl font-bold text-slate-900">{report.metrics.total_tickets}</p>
                  </div>
                  <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                    <BarChart3 className="h-6 w-6 text-blue-600" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-500">Taxa de Cumprimento SLA</p>
                    <p className="text-3xl font-bold text-slate-900">{report.metrics.sla_compliance_rate}%</p>
                  </div>
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                    report.metrics.sla_compliance_rate >= 80 ? 'bg-emerald-100' : 
                    report.metrics.sla_compliance_rate >= 50 ? 'bg-amber-100' : 'bg-red-100'
                  }`}>
                    <Clock className={`h-6 w-6 ${
                      report.metrics.sla_compliance_rate >= 80 ? 'text-emerald-600' : 
                      report.metrics.sla_compliance_rate >= 50 ? 'text-amber-600' : 'text-red-600'
                    }`} />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-500">Tickets em Atraso</p>
                    <p className="text-3xl font-bold text-red-600">{report.metrics.tickets_overdue}</p>
                  </div>
                  <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
                    <AlertTriangle className="h-6 w-6 text-red-600" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-500">Valor Total Orçamentos</p>
                    <p className="text-2xl font-bold text-emerald-600">{formatCurrency(report.metrics.total_quote_value)}</p>
                  </div>
                  <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center">
                    <Euro className="h-6 w-6 text-emerald-600" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Quote Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center">
                    <TrendingUp className="h-5 w-5 text-amber-600" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-slate-900">{report.metrics.quotes_sent}</p>
                    <p className="text-sm text-zinc-500">Orçamentos Enviados</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-emerald-100 rounded-full flex items-center justify-center">
                    <CheckCircle className="h-5 w-5 text-emerald-600" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-emerald-600">{report.metrics.quotes_accepted}</p>
                    <p className="text-sm text-zinc-500">Orçamentos Aceites</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
                    <XCircle className="h-5 w-5 text-red-600" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-red-600">{report.metrics.quotes_rejected}</p>
                    <p className="text-sm text-zinc-500">Orçamentos Recusados</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Status and Type Distribution */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Distribuição por Estado</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {Object.entries(report.metrics.tickets_by_status).map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge className={getStatusColor(status)}>
                          {getStatusLabel(status)}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-32 h-2 bg-zinc-100 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-orange-500 rounded-full"
                            style={{ width: `${(count / report.metrics.total_tickets) * 100}%` }}
                          />
                        </div>
                        <span className="text-sm font-medium w-12 text-right">{count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Distribuição por Tipo</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {Object.entries(report.metrics.tickets_by_type).map(([type, count]) => {
                    const typeInfo = ticketTypes.find(t => t.code === type);
                    return (
                      <div key={type} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div 
                            className="w-3 h-3 rounded-full"
                            style={{ backgroundColor: typeInfo?.color || '#6b7280' }}
                          />
                          <span className="text-sm">{typeInfo?.label || type}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-32 h-2 bg-zinc-100 rounded-full overflow-hidden">
                            <div 
                              className="h-full rounded-full"
                              style={{ 
                                width: `${(count / report.metrics.total_tickets) * 100}%`,
                                backgroundColor: typeInfo?.color || '#6b7280'
                              }}
                            />
                          </div>
                          <span className="text-sm font-medium w-12 text-right">{count}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Agent Performance */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Users className="h-5 w-5" />
                Desempenho por Agente
              </CardTitle>
            </CardHeader>
            <CardContent>
              {report.agent_performance.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-3 px-4 font-semibold text-zinc-600">Agente</th>
                        <th className="text-center py-3 px-4 font-semibold text-zinc-600">Tickets Atribuídos</th>
                        <th className="text-center py-3 px-4 font-semibold text-zinc-600">Tickets Fechados</th>
                        <th className="text-center py-3 px-4 font-semibold text-zinc-600">Taxa SLA</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.agent_performance.map((agent) => (
                        <tr key={agent.user_id} className="border-b hover:bg-zinc-50">
                          <td className="py-3 px-4 font-medium">{agent.user_name}</td>
                          <td className="text-center py-3 px-4">{agent.tickets_assigned}</td>
                          <td className="text-center py-3 px-4">{agent.tickets_closed}</td>
                          <td className="text-center py-3 px-4">
                            <Badge className={
                              agent.sla_compliance_rate >= 80 ? 'bg-emerald-100 text-emerald-700' :
                              agent.sla_compliance_rate >= 50 ? 'bg-amber-100 text-amber-700' :
                              'bg-red-100 text-red-700'
                            }>
                              {agent.sla_compliance_rate}%
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-center text-zinc-500 py-8">Nenhum dado de agentes disponível</p>
              )}
            </CardContent>
          </Card>

          {/* Daily Chart */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Tickets por Dia (Últimos 30 dias)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-48 flex items-end gap-1">
                {report.daily_ticket_counts.slice(-30).map((day, index) => {
                  const maxCount = Math.max(...report.daily_ticket_counts.map(d => d.count), 1);
                  const height = (day.count / maxCount) * 100;
                  return (
                    <div 
                      key={day.date}
                      className="flex-1 bg-orange-500 rounded-t hover:bg-orange-600 transition-colors group relative"
                      style={{ height: `${Math.max(height, 2)}%` }}
                      title={`${day.date}: ${day.count} tickets`}
                    >
                      <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap">
                        {day.count}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-between mt-2 text-xs text-zinc-500">
                <span>{report.daily_ticket_counts[0]?.date}</span>
                <span>{report.daily_ticket_counts[report.daily_ticket_counts.length - 1]?.date}</span>
              </div>
            </CardContent>
          </Card>
        </>
      ) : (
        <div className="text-center py-12 text-zinc-500">
          Clique em "Atualizar" para gerar o relatório
        </div>
      )}
    </div>
  );
};

export default AdminReports;
