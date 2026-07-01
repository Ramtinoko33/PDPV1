import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import axios from 'axios';
import { Coins, RefreshCw, ArrowRight, Users } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const formatCurrency = (value) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(value || 0);

const SUGGESTION_LABELS = {
  ignore: { label: 'Ignorar operacionalmente', style: 'bg-slate-100 text-slate-700' },
  review: { label: 'Rever internamente', style: 'bg-yellow-100 text-yellow-800' },
  request_regularization: { label: 'Pedir regularização à contabilidade', style: 'bg-orange-100 text-orange-800' },
};

const Regularizations = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/finance/regularizations`, { headers: getAuthHeaders() });
      setData(res.data);
    } catch (err) {
      console.error('Erro ao carregar regularizações:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6" data-testid="regularizations-page">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Regularizações</h1>
          <p className="text-slate-500 text-sm">
            Saldos residuais e diferenças técnicas — contam na dívida contabilística mas não vão para cobrança
          </p>
        </div>
        <Button variant="outline" onClick={fetchData} data-testid="regularizations-refresh-btn">
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Total Residual</p>
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
              <p className="text-sm text-slate-500">Clientes com Residuais</p>
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

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Clientes com Saldos Residuais</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Cliente</th>
                  <th className="text-left p-3 text-sm font-medium text-slate-600">Código</th>
                  <th className="text-right p-3 text-sm font-medium text-slate-600">Total Residual</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Nº Docs Residuais</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600">Sugestão</th>
                  <th className="text-center p-3 text-sm font-medium text-slate-600"></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(data?.items || []).map((item) => {
                  const sug = SUGGESTION_LABELS[item.suggestion] || SUGGESTION_LABELS.review;
                  return (
                    <tr key={item.client_id} className="hover:bg-slate-50" data-testid={`regularization-row-${item.genes_code}`}>
                      <td className="p-3 text-sm font-medium">{item.client_name}</td>
                      <td className="p-3 text-sm text-slate-500">#{item.genes_code}</td>
                      <td className="p-3 text-sm text-right font-semibold text-amber-700">
                        {formatCurrency(item.residual_balance)}
                      </td>
                      <td className="p-3 text-sm text-center">{item.residual_document_count}</td>
                      <td className="p-3 text-center">
                        <Badge className={sug.style}>{sug.label}</Badge>
                      </td>
                      <td className="p-3 text-center">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => navigate(`/finance/clients/${item.client_id}`)}
                          data-testid={`regularization-open-client-${item.genes_code}`}
                        >
                          Abrir Ficha
                          <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
                {(data?.items || []).length === 0 && !loading && (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-slate-500">
                      Sem saldos residuais registados
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

export default Regularizations;
