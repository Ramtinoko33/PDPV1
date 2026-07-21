/**
 * CRM Finance > Eficácia das Tarefas.
 *
 * Dashboard read-only para medir se o motor de tarefas está a recomendar bem.
 * Não corre IA — apenas mostra padrões (motivos top, task_types com maior/menor
 * taxa de conclusão, valor coberto, etc.) para futura calibração manual das regras.
 */
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from '../../components/ui/select';
import axios from 'axios';
import {
  BarChart3, RefreshCw, TrendingUp, TrendingDown, CheckCircle2, XCircle,
  Clock, Shuffle, Mail, MessageSquare, Phone, Coins, Ban
} from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
  BarChart, Bar,
} from 'recharts';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TASK_TYPE_LABELS = {
  FOLLOW_FAILED_PROMISE:     'Promessa falhada',
  FOLLOW_PROMISE_DUE_TODAY:  'Promessa hoje',
  SEND_ACCOUNT_STATEMENT:    'Conta corrente',
  REQUEST_PAYMENT:           'Pedir pagamento',
  REQUEST_PROOF:             'Pedir comprovativo',
  CALL_HIGH_VALUE_CLIENT:    'Ligar alto valor',
  REVIEW_OLD_DEBT:           'Dívida antiga',
  REVIEW_LOW_VALUE_OLD_DEBT: 'Micro-saldo antigo',
  UPDATE_FINANCE_CONTACT:    'Atualizar contacto',
  REVIEW_RESIDUAL:           'Rever residual',
  SUGGEST_BLOCK:             'Sugerir bloqueio',
  REVIEW_DISPUTE:            'Rever disputa',
  CREATE_PAYMENT_PLAN:       'Plano pagamento',
  SET_NEXT_ACTION:           'Próxima ação',
  UPLOAD_GENES_MAP:          'Upload GENES',
};

const REASON_LABELS = {
  missing_invoice:            'Falta fatura',
  missing_statement:          'Falta conta corrente',
  need_confirm_finance_email: 'Confirmar email',
  awaiting_proof:             'Aguarda comprovativo',
  awaiting_internal_answer:   'Aguarda resposta interna',
  client_requested_later:     'Cliente pediu outra data',
  awaiting_accounting:        'Aguarda contabilidade',
  other:                      'Outro',
  duplicate:                  'Duplicada',
  active_promise:             'Promessa ativa',
  in_dispute:                 'Em disputa',
  residual_handled:           'Residual tratado',
  wrong_client_link:          'Cliente mal associado',
  wrong_document:             'Documento errado',
  data_looks_incorrect:       'Dados incorretos',
  blocked_no_action_needed:   'Bloqueado, sem ação',
};

const SEGMENTS = ['PARTICULAR', 'EMPRESA', 'FROTA', 'SEGURADORA', 'LEASING', 'CONTA_CORRENTE', 'OUTRO', 'UNKNOWN'];

const formatCurrency = (v) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(v || 0);

const todayIso = () => new Date().toISOString().slice(0, 10);
const daysAgoIso = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

export default function TasksEffectiveness() {
  const { getAuthHeaders } = useAuth();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [filters, setFilters] = useState({
    date_from: daysAgoIso(30),
    date_to: todayIso(),
    task_type: 'all',
    customer_segment: 'all',
    status: 'all',
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        date_from: filters.date_from,
        date_to: filters.date_to,
      });
      if (filters.task_type !== 'all') params.append('task_type', filters.task_type);
      if (filters.customer_segment !== 'all') params.append('customer_segment', filters.customer_segment);
      if (filters.status !== 'all') params.append('status', filters.status);
      const res = await axios.get(`${API_URL}/api/finance/tasks/effectiveness?${params}`, {
        headers: getAuthHeaders(),
      });
      setData(res.data);
    } catch (err) {
      console.error('Erro ao carregar eficácia:', err);
    } finally {
      setLoading(false);
    }
  }, [filters, getAuthHeaders]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const totals = data?.totals || {};
  const rates = data?.rates || {};
  const today = data?.today_summary || {};

  return (
    <div className="space-y-6" data-testid="tasks-effectiveness-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-orange-500" /> Eficácia das Tarefas
          </h1>
          <p className="text-slate-500 text-sm">
            Medir se o motor está a recomendar bem — sem IA a decidir sozinha
          </p>
        </div>
        <Button variant="outline" onClick={fetchData} disabled={loading} data-testid="eff-refresh-btn">
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Atualizar
        </Button>
      </div>

      {/* Filtros */}
      <Card>
        <CardContent className="p-4 grid grid-cols-2 md:grid-cols-5 gap-3">
          <div>
            <Label className="text-xs">De</Label>
            <Input type="date" value={filters.date_from}
                   onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
                   data-testid="eff-date-from" />
          </div>
          <div>
            <Label className="text-xs">Até</Label>
            <Input type="date" value={filters.date_to}
                   onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
                   data-testid="eff-date-to" />
          </div>
          <div>
            <Label className="text-xs">Task Type</Label>
            <Select value={filters.task_type} onValueChange={(v) => setFilters({ ...filters, task_type: v })}>
              <SelectTrigger data-testid="eff-task-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {Object.entries(TASK_TYPE_LABELS).map(([k, l]) => (
                  <SelectItem key={k} value={k}>{l}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Segmento</Label>
            <Select value={filters.customer_segment} onValueChange={(v) => setFilters({ ...filters, customer_segment: v })}>
              <SelectTrigger data-testid="eff-segment-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {SEGMENTS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Estado</Label>
            <Select value={filters.status} onValueChange={(v) => setFilters({ ...filters, status: v })}>
              <SelectTrigger data-testid="eff-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="OPEN">Abertas</SelectItem>
                <SelectItem value="DONE">Feitas</SelectItem>
                <SelectItem value="POSTPONED">Adiadas</SelectItem>
                <SelectItem value="CONVERTED">Convertidas</SelectItem>
                <SelectItem value="REJECTED">Rejeitadas</SelectItem>
                <SelectItem value="EXPIRED">Expiradas</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* KPIs de topo */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <KpiCard label="Geradas" value={totals.generated || 0} icon={BarChart3} color="slate" testid="kpi-generated" />
        <KpiCard label="Feitas" value={totals.done || 0} icon={CheckCircle2} color="green" testid="kpi-done" />
        <KpiCard label="Adiadas" value={totals.postponed || 0} icon={Clock} color="yellow" testid="kpi-postponed" />
        <KpiCard label="Convertidas" value={totals.converted || 0} icon={Shuffle} color="purple" testid="kpi-converted" />
        <KpiCard label="Rejeitadas" value={totals.rejected || 0} icon={XCircle} color="slate" testid="kpi-rejected" />
        <KpiCard label="Abertas" value={totals.open || 0} icon={Clock} color="blue" testid="kpi-open" />
      </div>

      {/* Taxas + valores */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard label="Taxa conclusão" value={`${rates.completion_rate || 0}%`} icon={TrendingUp} color="green" testid="kpi-completion-rate" />
        <KpiCard label="Taxa rejeição" value={`${rates.rejection_rate || 0}%`} icon={TrendingDown} color="red" testid="kpi-rejection-rate" />
        <KpiCard label="Taxa adiamento" value={`${rates.postpone_rate || 0}%`} icon={Clock} color="yellow" testid="kpi-postpone-rate" />
        <KpiCard label="Valor coberto" value={formatCurrency(data?.amounts?.covered_by_done)} icon={Coins} color="orange" testid="kpi-amount-covered" />
        <KpiCard label="Prometido" value={formatCurrency(data?.amounts?.promised_total)} icon={Coins} color="blue" testid="kpi-promised" />
      </div>

      {/* Resumo diário */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Resumo diário — {todayIso()}</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <MiniStat label="Planeadas" value={today.planned || 0} />
          <MiniStat label="Concluídas" value={today.done || 0} tone="green" />
          <MiniStat label="Não tratadas" value={today.untreated || 0} tone="red" />
          <MiniStat label="Adiadas" value={today.postponed || 0} tone="yellow" />
          <MiniStat label="Rejeitadas" value={today.rejected || 0} tone="slate" />
        </CardContent>
      </Card>

      {/* Comunicações */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Comunicações no período</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <MiniStat label="Emails" value={data?.communications?.emails || 0} icon={Mail} tone="blue" />
          <MiniStat label="WhatsApps" value={data?.communications?.whatsapps || 0} icon={MessageSquare} tone="green" />
          <MiniStat label="Telefonemas" value={data?.communications?.phone_calls || 0} icon={Phone} tone="slate" />
          <MiniStat label="Promessas criadas" value={data?.promises_created || 0} tone="orange" />
          <MiniStat label="Bloqueios" value={data?.block_task_done || 0} icon={Ban} tone="red" />
        </CardContent>
      </Card>

      {/* Série temporal */}
      {data?.daily_series?.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Evolução diária</CardTitle>
          </CardHeader>
          <CardContent className="h-72" data-testid="eff-daily-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.daily_series}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="generated" stroke="#64748b" name="Geradas" />
                <Line type="monotone" dataKey="done" stroke="#16a34a" name="Feitas" strokeWidth={2} />
                <Line type="monotone" dataKey="rejected" stroke="#dc2626" name="Rejeitadas" />
                <Line type="monotone" dataKey="postponed" stroke="#eab308" name="Adiadas" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Task types performance */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Performance por task_type</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th className="text-left p-3">Task type</th>
                  <th className="text-right p-3">Geradas</th>
                  <th className="text-right p-3">Feitas</th>
                  <th className="text-right p-3">Rejeitadas</th>
                  <th className="text-right p-3">Adiadas</th>
                  <th className="text-right p-3">Taxa conclusão</th>
                  <th className="text-right p-3">Taxa rejeição</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(data?.by_task_type || []).map((t) => (
                  <tr key={t.task_type} className="hover:bg-slate-50" data-testid={`eff-tt-row-${t.task_type}`}>
                    <td className="p-3">{TASK_TYPE_LABELS[t.task_type] || t.task_type}</td>
                    <td className="p-3 text-right">{t.generated}</td>
                    <td className="p-3 text-right text-green-700">{t.done}</td>
                    <td className="p-3 text-right text-red-600">{t.rejected}</td>
                    <td className="p-3 text-right text-yellow-700">{t.postponed}</td>
                    <td className="p-3 text-right">
                      <Badge className={t.completion_rate >= 50 ? 'bg-green-100 text-green-800' : t.completion_rate >= 25 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'}>
                        {t.completion_rate}%
                      </Badge>
                    </td>
                    <td className="p-3 text-right text-slate-500">{t.rejection_rate}%</td>
                  </tr>
                ))}
                {(!data?.by_task_type || data.by_task_type.length === 0) && (
                  <tr><td colSpan={7} className="p-6 text-center text-slate-500">Sem dados no período seleccionado</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Motivos top */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ReasonList
          title="Top motivos de adiamento"
          items={data?.top_postpone_reasons || []}
          testid="eff-top-postpone"
        />
        <ReasonList
          title="Top motivos de rejeição"
          items={data?.top_reject_reasons || []}
          testid="eff-top-reject"
        />
        <ReasonList
          title="Task types mais convertidos"
          items={(data?.top_converted_from_type || []).map((r) => ({ ...r, reason: TASK_TYPE_LABELS[r.reason] || r.reason }))}
          testid="eff-top-converted"
          raw
        />
      </div>

      {/* Segmentos */}
      {data?.by_segment?.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Por segmento</CardTitle>
          </CardHeader>
          <CardContent className="h-72" data-testid="eff-segment-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.by_segment}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="segment" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="generated" fill="#94a3b8" name="Geradas" />
                <Bar dataKey="done" fill="#16a34a" name="Feitas" />
                <Bar dataKey="rejected" fill="#dc2626" name="Rejeitadas" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function KpiCard({ label, value, icon: Icon, color, testid }) {
  const styles = {
    slate:  'bg-slate-50 text-slate-800',
    green:  'bg-green-50 text-green-800',
    red:    'bg-red-50 text-red-800',
    yellow: 'bg-yellow-50 text-yellow-800',
    orange: 'bg-orange-50 text-orange-800',
    blue:   'bg-blue-50 text-blue-800',
    purple: 'bg-purple-50 text-purple-800',
  };
  return (
    <Card className={styles[color]} data-testid={testid}>
      <CardContent className="p-3 flex items-center justify-between">
        <div>
          <div className="text-xs">{label}</div>
          <div className="text-xl font-bold">{value}</div>
        </div>
        {Icon && <Icon className="h-5 w-5 opacity-60" />}
      </CardContent>
    </Card>
  );
}

function MiniStat({ label, value, tone = 'slate', icon: Icon }) {
  const tones = {
    slate:  'text-slate-800',
    green:  'text-green-700',
    red:    'text-red-600',
    yellow: 'text-yellow-700',
    orange: 'text-orange-700',
    blue:   'text-blue-700',
  };
  return (
    <div className="flex flex-col items-start p-2 rounded bg-slate-50">
      <div className="text-xs text-slate-500 flex items-center gap-1">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        {label}
      </div>
      <div className={`text-xl font-bold ${tones[tone]}`}>{value}</div>
    </div>
  );
}

function ReasonList({ title, items, testid, raw = false }) {
  return (
    <Card data-testid={testid}>
      <CardHeader className="pb-3"><CardTitle className="text-base">{title}</CardTitle></CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <div className="text-sm text-slate-400">Sem dados</div>
        ) : (
          <div className="space-y-2">
            {items.map((r, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-slate-700">{raw ? r.reason : (REASON_LABELS[r.reason] || r.reason)}</span>
                <Badge className="bg-slate-100 text-slate-700">{r.count}</Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
