import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import axios from 'axios';
import {
  Phone,
  MessageSquare,
  Mail,
  FileText,
  AlertTriangle,
  RefreshCw,
  Search,
  ArrowRight,
  Clock,
  Euro
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

const CollectionsToday = () => {
  const { getAuthHeaders } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_URL}/api/finance/collections/today`, {
        headers: getAuthHeaders()
      });
      setData(response.data);
    } catch (err) {
      console.error('Erro ao carregar cobranças:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const filteredItems = data?.items?.filter(item => 
    item.client_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.genes_code.includes(searchTerm)
  ) || [];

  if (loading) {
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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Cobranças de Hoje</h1>
          <p className="text-slate-500 text-sm">
            {data?.total_items || 0} clientes · {formatCurrency(data?.total_value)} em cobrança
          </p>
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Pesquisar..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9 w-64"
            />
          </div>
          <Button variant="outline" size="icon" onClick={fetchData}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Collections List */}
      <div className="space-y-3">
        {filteredItems.map((item) => (
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
                    <div className="flex items-center gap-4 mt-2 text-sm text-slate-600">
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

        {filteredItems.length === 0 && (
          <Card>
            <CardContent className="p-8 text-center">
              <p className="text-slate-500">
                {searchTerm ? 'Nenhum cliente encontrado' : 'Nenhuma cobrança pendente para hoje'}
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default CollectionsToday;
