import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip } from 'recharts';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Textarea } from '../../components/ui/textarea';
import { Input } from '../../components/ui/input';

// Hoisted constants — avoid inline objects that force re-renders every frame
const HIST_CHART_MARGIN = { top: 8, right: 16, left: 8, bottom: 0 };
const HIST_TICK_STYLE = { fontSize: 11 };
const HIST_DOT_STYLE = { r: 3 };
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../../components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import QuickCommunicationPanel from './QuickCommunicationPanel';
import axios from 'axios';
import {
  ArrowLeft,
  Phone,
  MessageSquare,
  Mail,
  FileText,
  AlertTriangle,
  RefreshCw,
  Euro,
  Calendar,
  Clock,
  User,
  Building,
  Ban,
  CheckCircle,
  XCircle,
  Plus
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TrafficLightBadge = ({ light, large = false }) => {
  const colors = {
    GREEN: 'bg-green-500',
    YELLOW: 'bg-yellow-500',
    ORANGE: 'bg-orange-500',
    RED: 'bg-red-500',
    CRITICAL: 'bg-red-700 animate-pulse'
  };
  
  const size = large ? 'w-5 h-5' : 'w-3 h-3';
  
  return (
    <span className={`inline-block ${size} rounded-full ${colors[light] || 'bg-gray-400'}`} 
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
    REGULARIZACAO_TECNICA: 'bg-slate-100 text-slate-800',
    OK: 'bg-green-100 text-green-800'
  };
  
  const labels = {
    EM_COBRANCA: 'Em Cobrança',
    PROMESSA_ATIVA: 'Promessa Ativa',
    PROMESSA_FALHADA: 'Promessa Falhada',
    EM_DISPUTA: 'Em Disputa',
    BLOQUEIO_SUGERIDO: 'Bloqueio Sugerido',
    BLOQUEADO: 'Bloqueado',
    REGULARIZACAO_TECNICA: 'Regularização Técnica',
    OK: 'OK'
  };
  
  return (
    <Badge className={`${styles[status] || 'bg-slate-100'}`}>
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

const formatDate = (dateStr) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('pt-PT');
};

const formatDateTime = (dateStr) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('pt-PT');
};

const FinanceClientDetail = () => {
  const { clientId } = useParams();
  const { user, getAuthHeaders } = useAuth();
  const [client, setClient] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Modals
  const [showActionModal, setShowActionModal] = useState(false);
  const [showPromiseModal, setShowPromiseModal] = useState(false);
  const [showBlockModal, setShowBlockModal] = useState(false);
  
  // Form states
  const [actionType, setActionType] = useState('phone_call');
  const [actionNotes, setActionNotes] = useState('');
  const [delayReason, setDelayReason] = useState('');
  const [nextActionDate, setNextActionDate] = useState('');
  const [promiseAmount, setPromiseAmount] = useState('');
  const [promiseDate, setPromiseDate] = useState('');
  const [promiseNotes, setPromiseNotes] = useState('');
  const [blockReason, setBlockReason] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [clientRes, docsRes, historyRes] = await Promise.all([
        axios.get(`${API_URL}/api/finance/clients/${clientId}`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/finance/clients/${clientId}/documents`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/finance/clients/${clientId}/history`, { headers: getAuthHeaders() })
      ]);
      setClient(clientRes.data);
      setDocuments(docsRes.data.documents || []);
      setHistory(historyRes.data.actions || []);
    } catch (err) {
      console.error('Erro ao carregar cliente:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [clientId]);

  const handleSaveAction = async () => {
    setSaving(true);
    try {
      await axios.post(`${API_URL}/api/finance/clients/${clientId}/actions`, {
        action_type: actionType,
        notes: actionNotes,
        delay_reason: delayReason && delayReason !== 'none' ? delayReason : null,
        next_action_date: nextActionDate || null
      }, { headers: getAuthHeaders() });
      
      setShowActionModal(false);
      setActionNotes('');
      setDelayReason('');
      setNextActionDate('');
      fetchData();
    } catch (err) {
      console.error('Erro ao guardar ação:', err);
      alert('Erro ao guardar ação');
    } finally {
      setSaving(false);
    }
  };

  const handleSavePromise = async () => {
    setSaving(true);
    try {
      await axios.post(`${API_URL}/api/finance/clients/${clientId}/promises`, {
        amount: parseFloat(promiseAmount),
        promise_date: promiseDate,
        notes: promiseNotes || null
      }, { headers: getAuthHeaders() });
      
      setShowPromiseModal(false);
      setPromiseAmount('');
      setPromiseDate('');
      setPromiseNotes('');
      fetchData();
    } catch (err) {
      console.error('Erro ao criar promessa:', err);
      alert('Erro ao criar promessa');
    } finally {
      setSaving(false);
    }
  };

  const handleSuggestBlock = async () => {
    setSaving(true);
    try {
      await axios.post(`${API_URL}/api/finance/clients/${clientId}/suggest-block`, {
        reason: blockReason
      }, { headers: getAuthHeaders() });
      
      setShowBlockModal(false);
      setBlockReason('');
      fetchData();
    } catch (err) {
      console.error('Erro ao sugerir bloqueio:', err);
      alert('Erro ao sugerir bloqueio');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-orange-600" />
      </div>
    );
  }

  if (!client) {
    return (
      <div className="text-center py-8">
        <p className="text-slate-500">Cliente não encontrado</p>
        <Link to="/finance/clients">
          <Button variant="outline" className="mt-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Voltar
          </Button>
        </Link>
      </div>
    );
  }

  const actionTypeLabels = {
    phone_call: 'Telefonema',
    whatsapp: 'WhatsApp',
    email: 'Email',
    note: 'Nota',
    promise_created: 'Promessa Criada',
    promise_updated: 'Promessa Atualizada',
    dispute_marked: 'Disputa',
    payment_plan_marked: 'Plano de Pagamento',
    block_suggested: 'Bloqueio Sugerido',
    block_approved: 'Bloqueio Aprovado',
    block_rejected: 'Bloqueio Rejeitado',
    unblocked: 'Desbloqueado',
    internal_regularization: 'Regularização Interna',
  };

  const actionTypeStyles = {
    phone_call:            { bg: 'bg-slate-100',   dot: 'bg-slate-400',   icon: Phone,         iconColor: 'text-slate-600' },
    whatsapp:              { bg: 'bg-emerald-50',  dot: 'bg-emerald-500', icon: MessageSquare, iconColor: 'text-emerald-600' },
    email:                 { bg: 'bg-blue-50',     dot: 'bg-blue-500',    icon: Mail,          iconColor: 'text-blue-600' },
    note:                  { bg: 'bg-yellow-50',   dot: 'bg-yellow-500',  icon: FileText,      iconColor: 'text-yellow-700' },
    promise_created:       { bg: 'bg-indigo-50',   dot: 'bg-indigo-500',  icon: CheckCircle,   iconColor: 'text-indigo-600' },
    promise_updated:       { bg: 'bg-indigo-50',   dot: 'bg-indigo-500',  icon: CheckCircle,   iconColor: 'text-indigo-600' },
    dispute_marked:        { bg: 'bg-purple-50',   dot: 'bg-purple-500',  icon: AlertTriangle, iconColor: 'text-purple-600' },
    payment_plan_marked:   { bg: 'bg-teal-50',     dot: 'bg-teal-500',    icon: Calendar,      iconColor: 'text-teal-600' },
    block_suggested:       { bg: 'bg-amber-50',    dot: 'bg-amber-500',   icon: AlertTriangle, iconColor: 'text-amber-600' },
    block_approved:        { bg: 'bg-red-50',      dot: 'bg-red-600',     icon: Ban,           iconColor: 'text-red-600' },
    block_rejected:        { bg: 'bg-slate-50',    dot: 'bg-slate-500',   icon: XCircle,       iconColor: 'text-slate-500' },
    unblocked:             { bg: 'bg-green-50',    dot: 'bg-green-600',   icon: CheckCircle,   iconColor: 'text-green-600' },
    internal_regularization: { bg: 'bg-orange-50', dot: 'bg-orange-500',  icon: FileText,      iconColor: 'text-orange-600' },
  };

  const groupHistoryByDay = (items) => {
    const groups = {};
    for (const it of items) {
      const day = (it.created_at || '').slice(0, 10);
      if (!groups[day]) groups[day] = [];
      groups[day].push(it);
    }
    return Object.entries(groups).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  };

  const formatDayLabel = (isoDay) => {
    if (!isoDay) return '—';
    try {
      const d = new Date(isoDay);
      const today = new Date();
      const yest = new Date(); yest.setDate(today.getDate() - 1);
      if (d.toDateString() === today.toDateString()) return 'Hoje';
      if (d.toDateString() === yest.toDateString()) return 'Ontem';
      return d.toLocaleDateString('pt-PT', { day: '2-digit', month: 'long', year: 'numeric' });
    } catch { return isoDay; }
  };

  const delayReasonLabels = {
    esquecimento: 'Esquecimento',
    processo_administrativo: 'Processo Administrativo',
    falta_documento: 'Falta de Documento',
    disputa: 'Disputa',
    falta_liquidez: 'Falta de Liquidez',
    cliente_dificil: 'Cliente Difícil',
    acordo_em_curso: 'Acordo em Curso',
    erro_interno: 'Erro Interno',
    saldo_residual: 'Saldo Residual',
    outro: 'Outro'
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Link to="/finance/clients">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <TrafficLightBadge light={client.traffic_light} large />
              <h1 className="text-2xl font-bold text-slate-900">{client.name}</h1>
              <StatusBadge status={client.financial_status} />
              {client.is_blocked && (
                <Badge variant="destructive">
                  <Ban className="h-3 w-3 mr-1" />
                  Bloqueado
                </Badge>
              )}
            </div>
            <p className="text-slate-500 mt-1">
              Código: {client.genes_code} · Conta: {client.genes_account || '-'}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowActionModal(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Registar Contacto
          </Button>
          <Button onClick={() => setShowPromiseModal(true)}>
            <FileText className="h-4 w-4 mr-2" />
            Criar Promessa
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-slate-500">Saldo Total</p>
            <p className="text-xl font-bold">{formatCurrency(client.total_balance)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-slate-500">Vencido Cobrável</p>
            <p className="text-xl font-bold text-red-600">
              {formatCurrency(client.overdue_balance_collectable)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-slate-500">Maior Atraso</p>
            <p className="text-xl font-bold">{client.oldest_overdue_days} dias</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-slate-500">Índice Cobrança</p>
            <p className="text-xl font-bold">{client.collection_index?.toFixed(1)}%</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="documents" className="space-y-4">
        <TabsList>
          <TabsTrigger value="documents">Documentos ({documents.length})</TabsTrigger>
          <TabsTrigger value="history">Histórico ({history.length})</TabsTrigger>
          <TabsTrigger value="info">Informação</TabsTrigger>
        </TabsList>

        {/* Documents Tab */}
        <TabsContent value="documents">
          <Card>
            <CardContent className="p-0">
              <table className="w-full">
                <thead className="bg-slate-50 border-b">
                  <tr>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Documento</th>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Data Venc.</th>
                    <th className="text-center p-3 text-sm font-medium text-slate-600">Dias</th>
                    <th className="text-right p-3 text-sm font-medium text-slate-600">Valor</th>
                    <th className="text-center p-3 text-sm font-medium text-slate-600">Classificação</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {documents.map((doc) => (
                    <tr key={doc.id} className="hover:bg-slate-50">
                      <td className="p-3">
                        <span className="font-medium">{doc.document_type} {doc.document_number}</span>
                      </td>
                      <td className="p-3 text-sm">{formatDate(doc.due_date)}</td>
                      <td className="p-3 text-center">
                        {doc.days_overdue > 0 ? (
                          <span className={doc.days_overdue > 60 ? 'text-red-600 font-medium' : ''}>
                            {doc.days_overdue}
                          </span>
                        ) : '-'}
                      </td>
                      <td className="p-3 text-right font-medium">
                        {formatCurrency(doc.amount_open)}
                      </td>
                      <td className="p-3 text-center">
                        <Badge variant="outline" className="text-xs">
                          {doc.classification === 'collectable' ? 'Cobrável' :
                           doc.classification === 'residual' ? 'Residual' :
                           doc.classification === 'credit' ? 'Crédito' :
                           doc.classification}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                  {documents.length === 0 && (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-slate-500">
                        Sem documentos
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* History Tab - Timeline agrupado por dia */}
        <TabsContent value="history">
          <Card>
            <CardContent className="p-4">
              {history.length === 0 ? (
                <p className="text-center text-slate-500 py-8">
                  Sem histórico de comunicações e ações.
                </p>
              ) : (
                <div className="relative" data-testid="finance-history-timeline">
                  {groupHistoryByDay(history).map(([day, items]) => (
                    <div key={day} className="mb-6" data-testid={`history-day-${day}`}>
                      <div className="sticky top-0 z-10 bg-white pb-2 mb-3 border-b flex items-center gap-2">
                        <Badge className="bg-slate-100 text-slate-700 hover:bg-slate-100">
                          {formatDayLabel(day)}
                        </Badge>
                        <span className="text-xs text-slate-400">
                          {items.length} evento{items.length > 1 ? 's' : ''}
                        </span>
                      </div>
                      <div className="relative pl-8 space-y-4">
                        {/* linha vertical do timeline */}
                        <div className="absolute left-3 top-1 bottom-1 w-px bg-slate-200"></div>
                        {items.map((action) => {
                          const style = actionTypeStyles[action.action_type] ||
                            { bg: 'bg-slate-100', dot: 'bg-slate-400', icon: FileText, iconColor: 'text-slate-500' };
                          const Icon = style.icon;
                          return (
                            <div key={action.id} className="relative" data-testid={`history-item-${action.id}`}>
                              {/* dot */}
                              <div className={`absolute -left-6 top-1 h-3 w-3 rounded-full ring-4 ring-white ${style.dot}`}></div>
                              <div className={`rounded-lg border p-3 ${style.bg}`}>
                                <div className="flex items-start gap-2">
                                  <Icon className={`h-4 w-4 mt-0.5 flex-shrink-0 ${style.iconColor}`} />
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-baseline gap-2 flex-wrap">
                                      <span className="font-semibold text-slate-900">
                                        {actionTypeLabels[action.action_type] || action.action_type}
                                      </span>
                                      <span className="text-xs text-slate-500">
                                        por {action.user_name || '—'}
                                      </span>
                                      <span className="text-xs text-slate-400 ml-auto">
                                        {new Date(action.created_at).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })}
                                      </span>
                                    </div>
                                    {action.notes && (
                                      <p className="text-sm text-slate-700 mt-1 whitespace-pre-wrap break-words">
                                        {action.notes.length > 500 ? action.notes.slice(0, 500) + '…' : action.notes}
                                      </p>
                                    )}
                                    <div className="flex flex-wrap gap-1 mt-2">
                                      {action.delay_reason && (
                                        <Badge variant="outline" className="text-xs">
                                          Motivo: {delayReasonLabels[action.delay_reason] || action.delay_reason}
                                        </Badge>
                                      )}
                                      {action.next_action_date && (
                                        <Badge variant="outline" className="text-xs">
                                          Próx. ação: {action.next_action_date}
                                        </Badge>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Info Tab */}
        <TabsContent value="info">
          <div className="grid md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Contactos</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-500">Email</span>
                  <span>{client.email || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Telefone</span>
                  <span>{client.phone || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Telemóvel</span>
                  <span>{client.mobile || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Localidade</span>
                  <span>{client.locality || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Região</span>
                  <span>{client.region || '-'}</span>
                </div>
              </CardContent>
            </Card>

            <QuickCommunicationPanel
              client={client}
              getAuthHeaders={getAuthHeaders}
              onCommunicationLogged={fetchData}
            />
            
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Dados Financeiros</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-500">Faturação Anual</span>
                  <span>{formatCurrency(client.annual_revenue)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Carteira</span>
                  <span>{formatCurrency(client.portfolio)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Risco</span>
                  <span>{formatCurrency(client.risk_value)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Risco Seguro</span>
                  <span>{formatCurrency(client.insured_risk_value)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Pendente Entrega</span>
                  <span>{formatCurrency(client.pending_delivery)}</span>
                </div>
              </CardContent>
            </Card>
            
            {client.credit_evolution && Object.keys(client.credit_evolution).length > 0 && (
              <Card className="md:col-span-2" data-testid="credit-evolution-card">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center justify-between">
                    <span>Evolução Crédito (trimestral)</span>
                    {client.credit_trend_percentage != null && (
                      <span className={`text-sm font-semibold ${client.credit_trend_percentage > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                        {client.credit_trend_percentage > 0 ? '▲' : '▼'} {Math.abs(client.credit_trend_percentage).toFixed(1)}%
                      </span>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart
                      data={Object.entries(client.credit_evolution)
                        .sort((a, b) => {
                          const [ma, ya] = a[0].split('-');
                          const [mb, yb] = b[0].split('-');
                          return (ya + ma).localeCompare(yb + mb);
                        })
                        .map(([period, value]) => ({ period, value }))}
                      margin={HIST_CHART_MARGIN}
                    >
                      <XAxis dataKey="period" tick={HIST_TICK_STYLE} />
                      <YAxis tick={HIST_TICK_STYLE} width={70}
                        tickFormatter={(v) => `${(v / 1000).toFixed(0)}k€`} />
                      <Tooltip formatter={(v) => [formatCurrency(v), 'Saldo']} />
                      <Line type="monotone" dataKey="value" stroke="#ea580c" strokeWidth={2} dot={HIST_DOT_STYLE} />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}
          </div>
          
          {/* Block/Unblock Actions */}
          {!client.is_blocked && client.financial_status !== 'BLOQUEIO_SUGERIDO' && (
            <Card className="mt-4">
              <CardContent className="p-4">
                <Button 
                  variant="outline" 
                  className="text-yellow-600 border-yellow-300 hover:bg-yellow-50"
                  onClick={() => setShowBlockModal(true)}
                >
                  <AlertTriangle className="h-4 w-4 mr-2" />
                  Sugerir Bloqueio
                </Button>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Action Modal */}
      <Dialog open={showActionModal} onOpenChange={setShowActionModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registar Contacto</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Tipo de Contacto</label>
              <Select value={actionType} onValueChange={setActionType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="phone_call">Telefonema</SelectItem>
                  <SelectItem value="whatsapp">WhatsApp</SelectItem>
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="note">Nota</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Notas</label>
              <Textarea 
                value={actionNotes}
                onChange={(e) => setActionNotes(e.target.value)}
                placeholder="Descreva o contacto..."
                rows={3}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Motivo de Atraso (opcional)</label>
              <Select value={delayReason} onValueChange={setDelayReason}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecionar..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Nenhum</SelectItem>
                  <SelectItem value="esquecimento">Esquecimento</SelectItem>
                  <SelectItem value="processo_administrativo">Processo Administrativo</SelectItem>
                  <SelectItem value="falta_documento">Falta de Documento</SelectItem>
                  <SelectItem value="disputa">Disputa</SelectItem>
                  <SelectItem value="falta_liquidez">Falta de Liquidez</SelectItem>
                  <SelectItem value="cliente_dificil">Cliente Difícil</SelectItem>
                  <SelectItem value="acordo_em_curso">Acordo em Curso</SelectItem>
                  <SelectItem value="outro">Outro</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Próximo Contacto (opcional)</label>
              <Input 
                type="date"
                value={nextActionDate}
                onChange={(e) => setNextActionDate(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowActionModal(false)}>
              Cancelar
            </Button>
            <Button onClick={handleSaveAction} disabled={saving}>
              {saving ? 'A guardar...' : 'Guardar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Promise Modal */}
      <Dialog open={showPromiseModal} onOpenChange={setShowPromiseModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Criar Promessa de Pagamento</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Valor Prometido (€)</label>
              <Input 
                type="number"
                step="0.01"
                value={promiseAmount}
                onChange={(e) => setPromiseAmount(e.target.value)}
                placeholder="0.00"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Data Prometida</label>
              <Input 
                type="date"
                value={promiseDate}
                onChange={(e) => setPromiseDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Observações (opcional)</label>
              <Textarea 
                value={promiseNotes}
                onChange={(e) => setPromiseNotes(e.target.value)}
                placeholder="Notas adicionais..."
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPromiseModal(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleSavePromise} 
              disabled={saving || !promiseAmount || !promiseDate}
            >
              {saving ? 'A criar...' : 'Criar Promessa'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Block Modal */}
      <Dialog open={showBlockModal} onOpenChange={setShowBlockModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sugerir Bloqueio de Cliente</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <p className="text-sm text-slate-600">
              Esta ação irá criar um pedido de bloqueio que será analisado pelo responsável financeiro.
            </p>
            <div className="space-y-2">
              <label className="text-sm font-medium">Motivo do Bloqueio</label>
              <Textarea 
                value={blockReason}
                onChange={(e) => setBlockReason(e.target.value)}
                placeholder="Descreva o motivo para sugerir o bloqueio..."
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBlockModal(false)}>
              Cancelar
            </Button>
            <Button 
              variant="destructive"
              onClick={handleSuggestBlock} 
              disabled={saving || !blockReason}
            >
              {saving ? 'A enviar...' : 'Sugerir Bloqueio'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FinanceClientDetail;
