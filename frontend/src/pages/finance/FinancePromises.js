import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../components/ui/select';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '../../components/ui/dropdown-menu';
import axios from 'axios';
import { toast } from 'sonner';
import { RefreshCw, MoreVertical, CalendarClock } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const formatCurrency = (value) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(value || 0);

const formatDate = (dateStr) => (dateStr ? new Date(dateStr).toLocaleDateString('pt-PT') : '-');

const STATUS_META = {
  open: { label: 'Aberta', style: 'bg-blue-100 text-blue-800' },
  fulfilled: { label: 'Cumprida', style: 'bg-green-100 text-green-800' },
  partial: { label: 'Parcialmente Cumprida', style: 'bg-teal-100 text-teal-800' },
  failed: { label: 'Falhada', style: 'bg-red-100 text-red-800' },
  cancelled: { label: 'Cancelada', style: 'bg-slate-100 text-slate-700' },
};

const FinancePromises = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [promises, setPromises] = useState([]);
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter !== 'all' ? `?status=${statusFilter}` : '';
      const res = await axios.get(`${API_URL}/api/finance/promises${params}`, { headers: getAuthHeaders() });
      setPromises(res.data.promises || []);
    } catch (err) {
      console.error('Erro ao carregar promessas:', err);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const updateStatus = async (promiseId, newStatus) => {
    try {
      await axios.patch(
        `${API_URL}/api/finance/promises/${promiseId}`,
        { status: newStatus },
        { headers: getAuthHeaders() }
      );
      toast.success(`Promessa marcada como "${STATUS_META[newStatus].label}"`);
      fetchData();
    } catch (err) {
      console.error('Erro ao atualizar promessa:', err);
      toast.error(err.response?.data?.detail || 'Erro ao atualizar promessa');
    }
  };

  const isOverdue = (p) => p.status === 'open' && p.promise_date < new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-6" data-testid="promises-page">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Promessas de Pagamento</h1>
          <p className="text-slate-500 text-sm">Acompanhamento de todas as promessas registadas</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[200px]" data-testid="promises-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              <SelectItem value="open">Abertas</SelectItem>
              <SelectItem value="fulfilled">Cumpridas</SelectItem>
              <SelectItem value="partial">Parcialmente Cumpridas</SelectItem>
              <SelectItem value="failed">Falhadas</SelectItem>
              <SelectItem value="cancelled">Canceladas</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={fetchData} data-testid="promises-refresh-btn">
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <CalendarClock className="h-5 w-5" />
            {promises.length} promessa(s)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Cliente</th>
                  <th className="text-right p-3 text-sm font-medium text-slate-600">Valor</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Data Prometida</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Estado</th>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Criada por</th>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Notas</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600"></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {promises.map((p) => {
                  const meta = STATUS_META[p.status] || STATUS_META.open;
                  return (
                    <tr key={p.id} className="hover:bg-slate-50" data-testid={`promise-row-${p.id}`}>
                      <td className="p-3 text-sm">
                        <button
                          className="font-medium text-slate-900 hover:text-orange-600 hover:underline text-left"
                          onClick={() => navigate(`/finance/clients/${p.client_id}`)}
                          data-testid={`promise-client-link-${p.id}`}
                        >
                          {p.client_name || p.client_id}
                        </button>
                        {p.genes_code && <span className="text-slate-400 ml-1.5">#{p.genes_code}</span>}
                      </td>
                      <td className="p-3 text-sm text-right font-semibold">{formatCurrency(p.amount)}</td>
                      <td className={`p-3 text-sm text-center ${isOverdue(p) ? 'text-red-600 font-semibold' : ''}`}>
                        {formatDate(p.promise_date)}
                        {isOverdue(p) && <span className="block text-xs">vencida</span>}
                      </td>
                      <td className="p-3 text-center">
                        <Badge className={meta.style}>{meta.label}</Badge>
                      </td>
                      <td className="p-3 text-sm text-slate-600">{p.created_by_name || '-'}</td>
                      <td className="p-3 text-sm text-slate-500 max-w-[220px] truncate" title={p.notes || ''}>
                        {p.notes || '-'}
                      </td>
                      <td className="p-3 text-center">
                        {p.status === 'open' && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button size="sm" variant="ghost" data-testid={`promise-actions-btn-${p.id}`}>
                                <MoreVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => updateStatus(p.id, 'fulfilled')} data-testid={`promise-fulfill-${p.id}`}>
                                Marcar Cumprida
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => updateStatus(p.id, 'partial')}>
                                Marcar Parcialmente Cumprida
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => updateStatus(p.id, 'failed')} className="text-red-600" data-testid={`promise-fail-${p.id}`}>
                                Marcar Falhada
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => updateStatus(p.id, 'cancelled')}>
                                Cancelar
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {promises.length === 0 && !loading && (
                  <tr>
                    <td colSpan={7} className="p-8 text-center text-slate-500">
                      Nenhuma promessa encontrada
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default FinancePromises;
