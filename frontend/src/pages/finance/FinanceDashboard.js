import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import axios from 'axios';
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Users,
  FileText,
  Clock,
  Euro,
  ArrowRight,
  RefreshCw,
  Upload
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Semáforo visual
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

const formatCurrency = (value) => {
  return new Intl.NumberFormat('pt-PT', {
    style: 'currency',
    currency: 'EUR'
  }).format(value || 0);
};

const FinanceDashboard = () => {
  const { getAuthHeaders } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [dataHealth, setDataHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [dashRes, healthRes] = await Promise.all([
        axios.get(`${API_URL}/api/finance/dashboard`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/finance/data-health`, { headers: getAuthHeaders() })
      ]);
      setDashboard(dashRes.data);
      setDataHealth(healthRes.data);
      setError(null);
    } catch (err) {
      setError('Erro ao carregar dados financeiros');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-orange-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">CRM Finance</h1>
          <p className="text-slate-500 text-sm">Dashboard financeiro</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Atualizar
          </Button>
          <Link to="/finance/imports">
            <Button size="sm">
              <Upload className="h-4 w-4 mr-2" />
              Importar Dados
            </Button>
          </Link>
        </div>
      </div>

      {/* Data Health Alert */}
      {dataHealth?.any_blocking && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-800">Dados Desatualizados</p>
            <p className="text-sm text-red-600">
              Para evitar cobranças incorretas, carregue o ficheiro de saldos vencidos atualizado.
            </p>
            <Link to="/finance/imports" className="text-sm text-red-700 underline hover:no-underline">
              Ir para Importações →
            </Link>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-500">Total Vencido Cobrável</p>
                <p className="text-2xl font-bold text-slate-900">
                  {formatCurrency(dashboard?.total_overdue_collectable)}
                </p>
              </div>
              <div className="h-12 w-12 rounded-full bg-red-100 flex items-center justify-center">
                <Euro className="h-6 w-6 text-red-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-500">Clientes com Dívida</p>
                <p className="text-2xl font-bold text-slate-900">
                  {dashboard?.clients_with_overdue || 0}
                </p>
              </div>
              <div className="h-12 w-12 rounded-full bg-orange-100 flex items-center justify-center">
                <Users className="h-6 w-6 text-orange-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-500">Promessas Ativas</p>
                <p className="text-2xl font-bold text-slate-900">
                  {dashboard?.promises_active || 0}
                </p>
                {dashboard?.promises_failed > 0 && (
                  <p className="text-xs text-red-600">
                    {dashboard.promises_failed} falhadas
                  </p>
                )}
              </div>
              <div className="h-12 w-12 rounded-full bg-blue-100 flex items-center justify-center">
                <FileText className="h-6 w-6 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-500">Clientes Bloqueados</p>
                <p className="text-2xl font-bold text-slate-900">
                  {dashboard?.clients_blocked || 0}
                </p>
              </div>
              <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center">
                <AlertTriangle className="h-6 w-6 text-slate-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Aging Buckets */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Aging de Vencidos
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {dashboard?.aging_buckets?.map((bucket) => {
                const percentage = dashboard.total_overdue_collectable > 0 
                  ? (bucket.total_amount / dashboard.total_overdue_collectable) * 100 
                  : 0;
                const colors = {
                  '0-30': 'bg-yellow-500',
                  '31-60': 'bg-orange-500',
                  '61-90': 'bg-red-500',
                  '+90': 'bg-red-700'
                };
                return (
                  <div key={bucket.range_label} className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium">{bucket.range_label} dias</span>
                      <span className="text-slate-600">
                        {bucket.client_count} clientes · {formatCurrency(bucket.total_amount)}
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div 
                        className={`h-full ${colors[bucket.range_label] || 'bg-slate-400'} transition-all`}
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Top Debtors */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <TrendingDown className="h-5 w-5" />
              Top 10 Maiores Devedores
            </CardTitle>
            <Link to="/finance/clients?has_overdue=true">
              <Button variant="ghost" size="sm">
                Ver todos <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {dashboard?.top_debtors?.slice(0, 10).map((debtor, idx) => (
                <Link 
                  key={debtor.client_id}
                  to={`/finance/clients/${debtor.client_id}`}
                  className="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  <span className="text-sm font-medium text-slate-400 w-6">
                    {idx + 1}.
                  </span>
                  <TrafficLightBadge light={debtor.traffic_light} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate">{debtor.client_name}</p>
                    <p className="text-xs text-slate-500">{debtor.oldest_days} dias vencido</p>
                  </div>
                  <span className="font-semibold text-sm text-red-600">
                    {formatCurrency(debtor.overdue_amount)}
                  </span>
                </Link>
              ))}
              {(!dashboard?.top_debtors || dashboard.top_debtors.length === 0) && (
                <p className="text-center text-slate-500 py-4">Sem devedores</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Data Health Status */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Estado dos Dados</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {dataHealth?.items?.map((item) => {
              const statusColors = {
                ok: 'bg-green-100 text-green-800 border-green-200',
                warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
                blocking: 'bg-red-100 text-red-800 border-red-200'
              };
              const labels = {
                overdue_balances: 'Saldos Vencidos',
                open_documents: 'Documentos Aberto',
                client_info: 'Info Clientes'
              };
              return (
                <div 
                  key={item.source_type}
                  className={`p-4 rounded-lg border ${statusColors[item.status] || 'bg-slate-50'}`}
                >
                  <p className="font-medium">{labels[item.source_type] || item.source_type}</p>
                  <p className="text-sm mt-1">
                    {item.last_import_at 
                      ? `Última: ${new Date(item.last_import_at).toLocaleDateString('pt-PT')}`
                      : 'Nenhuma importação'
                    }
                  </p>
                  {item.message && (
                    <p className="text-xs mt-1">{item.message}</p>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default FinanceDashboard;
