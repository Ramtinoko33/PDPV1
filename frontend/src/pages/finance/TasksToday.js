/**
 * Página CRM Finance > Tarefas de Hoje.
 *
 * Motor de regras: sugere lista diária conforme modo (30/45/60 min).
 * A cobradora escolhe o modo, gera, e trata cada tarefa com 4 acções:
 *   - Feito (executada)
 *   - Adiar (motivo + próxima data)
 *   - Mudar ação (fecha original, cria nova)
 *   - Não faz sentido (motivo obrigatório)
 */
import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Textarea } from '../../components/ui/textarea';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../../components/ui/dialog';
import {
  Select, SelectTrigger, SelectContent, SelectItem, SelectValue,
} from '../../components/ui/select';
import { toast } from 'sonner';
import axios from 'axios';
import {
  Sparkles, CheckCircle2, Clock, Shuffle, XCircle, RefreshCw,
  AlertTriangle, ArrowRight, Timer
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TASK_TYPE_LABELS = {
  FOLLOW_FAILED_PROMISE:     'Promessa falhada',
  FOLLOW_PROMISE_DUE_TODAY:  'Promessa vence hoje',
  SEND_ACCOUNT_STATEMENT:    'Enviar conta corrente',
  REQUEST_PAYMENT:           'Pedir pagamento',
  REQUEST_PROOF:             'Pedir comprovativo',
  CALL_HIGH_VALUE_CLIENT:    'Ligar cliente alto valor',
  REVIEW_OLD_DEBT:           'Rever dívida antiga',
  REVIEW_LOW_VALUE_OLD_DEBT: 'Rever micro-saldo antigo',
  UPDATE_FINANCE_CONTACT:    'Atualizar contacto',
  REVIEW_RESIDUAL:           'Rever residual',
  SUGGEST_BLOCK:             'Sugerir bloqueio',
  REVIEW_DISPUTE:            'Rever disputa',
  CREATE_PAYMENT_PLAN:       'Criar plano pagamento',
  SET_NEXT_ACTION:           'Definir próxima ação',
  UPLOAD_GENES_MAP:          '⚠️ Carregar mapa GENES',
};

const POSTPONE_REASONS = [
  { key: 'missing_invoice',              label: 'Falta enviar fatura' },
  { key: 'missing_statement',            label: 'Falta enviar conta corrente' },
  { key: 'need_confirm_finance_email',   label: 'Confirmar email financeiro' },
  { key: 'awaiting_proof',               label: 'Aguarda comprovativo' },
  { key: 'awaiting_internal_answer',     label: 'Aguarda resposta interna' },
  { key: 'client_requested_later',       label: 'Cliente pediu contacto noutra data' },
  { key: 'awaiting_accounting',          label: 'Aguarda validação da contabilidade' },
  { key: 'other',                        label: 'Outro' },
];

const REJECT_REASONS = [
  { key: 'duplicate',                label: 'Tarefa duplicada' },
  { key: 'active_promise',           label: 'Cliente já tem promessa ativa' },
  { key: 'in_dispute',               label: 'Cliente em disputa' },
  { key: 'residual_handled',         label: 'Saldo residual já tratado' },
  { key: 'wrong_client_link',        label: 'Cliente mal associado' },
  { key: 'wrong_document',           label: 'Documento errado' },
  { key: 'data_looks_incorrect',     label: 'Dados parecem incorretos' },
  { key: 'blocked_no_action_needed', label: 'Cliente bloqueado, sem ação' },
  { key: 'other',                    label: 'Outro (nota obrigatória)' },
];

const CONVERT_TARGETS = Object.entries(TASK_TYPE_LABELS).filter(([k]) => k !== 'UPLOAD_GENES_MAP');

const STATUS_STYLE = {
  OPEN:      'bg-blue-100 text-blue-800',
  DONE:      'bg-green-100 text-green-800',
  POSTPONED: 'bg-yellow-100 text-yellow-800',
  CONVERTED: 'bg-purple-100 text-purple-800',
  REJECTED:  'bg-slate-100 text-slate-500',
  EXPIRED:   'bg-slate-100 text-slate-400',
  IN_REVIEW: 'bg-indigo-100 text-indigo-800',
};

const formatCurrency = (v) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(v || 0);

export default function TasksToday() {
  const { getAuthHeaders } = useAuth();
  const [mode, setMode] = useState('30');
  const [tasks, setTasks] = useState([]);
  const [summary, setSummary] = useState({});
  const [blockedReason, setBlockedReason] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionDialog, setActionDialog] = useState({ open: false, type: null, task: null });
  const [form, setForm] = useState({});

  const fetchTasks = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/api/finance/tasks/today`, { headers: getAuthHeaders() });
      setTasks(res.data.tasks || []);
      setSummary(res.data.summary || {});
    } catch (err) {
      console.error('Erro a carregar tarefas:', err);
    }
  }, [getAuthHeaders]);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  const generate = async (force = false) => {
    setLoading(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/finance/tasks/generate`,
        { mode, force_regenerate: force },
        { headers: getAuthHeaders() }
      );
      setTasks(res.data.tasks || []);
      setBlockedReason(res.data.blocked_reason);
      toast.success(`${res.data.tasks_created} tarefa(s) geradas (arquivadas: ${res.data.tasks_archived})`);
      fetchTasks();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Erro ao gerar tarefas');
    } finally {
      setLoading(false);
    }
  };

  const openAction = (type, task) => {
    setForm({});
    setActionDialog({ open: true, type, task });
  };

  const confirmAction = async () => {
    const { type, task } = actionDialog;
    if (!task) return;
    try {
      let payload = {};
      let endpoint = '';

      if (type === 'done') {
        endpoint = 'done';
        payload = { outcome: form.outcome || null };
      } else if (type === 'postpone') {
        if (!form.reason || !form.next_action_date) {
          toast.error('Motivo e próxima data são obrigatórios');
          return;
        }
        endpoint = 'postpone';
        payload = { reason: form.reason, next_action_date: form.next_action_date, note: form.note || null };
      } else if (type === 'convert') {
        if (!form.new_task_type) {
          toast.error('Novo tipo de tarefa obrigatório');
          return;
        }
        endpoint = 'convert';
        payload = { new_task_type: form.new_task_type, reason: form.reason || null };
      } else if (type === 'reject') {
        if (!form.reason) { toast.error('Motivo obrigatório'); return; }
        if (form.reason === 'other' && !form.note) { toast.error('Nota obrigatória para "Outro"'); return; }
        endpoint = 'reject';
        payload = { reason: form.reason, note: form.note || null };
      }

      await axios.post(
        `${API_URL}/api/finance/tasks/${task.id}/${endpoint}`,
        payload,
        { headers: getAuthHeaders() }
      );
      toast.success('Tarefa atualizada');
      setActionDialog({ open: false, type: null, task: null });
      fetchTasks();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Erro na acção');
    }
  };

  const openTasks = tasks.filter((t) => t.status === 'OPEN');
  const closedTasks = tasks.filter((t) => t.status !== 'OPEN');

  return (
    <div className="space-y-6" data-testid="tasks-today-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-orange-500" /> Tarefas de Hoje
          </h1>
          <p className="text-slate-500 text-sm">
            Motor de regras — {openTasks.length} abertas · escolha o modo e gere a sua lista diária
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <div className="flex gap-1 items-center bg-slate-100 rounded-md p-1">
            {['30', '45', '60'].map((m) => (
              <Button
                key={m}
                size="sm"
                variant={mode === m ? 'default' : 'ghost'}
                onClick={() => setMode(m)}
                data-testid={`tasks-mode-${m}`}
              >
                <Timer className="h-3.5 w-3.5 mr-1" /> {m} min
              </Button>
            ))}
          </div>
          <Button onClick={() => generate(false)} disabled={loading} data-testid="tasks-generate-btn">
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Gerar
          </Button>
          <Button variant="outline" onClick={() => generate(true)} disabled={loading} data-testid="tasks-regenerate-btn">
            Regerar (força)
          </Button>
        </div>
      </div>

      {blockedReason && (
        <Card className="border-amber-300 bg-amber-50">
          <CardContent className="p-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" />
            <div>
              <div className="font-semibold text-amber-800">Dados desatualizados</div>
              <div className="text-sm text-amber-700">{blockedReason}</div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <SummaryCard label="Abertas" value={summary.open || 0} color="blue" testid="summary-open" />
        <SummaryCard label="Feitas" value={summary.done || 0} color="green" testid="summary-done" />
        <SummaryCard label="Adiadas" value={summary.postponed || 0} color="yellow" testid="summary-postponed" />
        <SummaryCard label="Convertidas" value={summary.converted || 0} color="purple" testid="summary-converted" />
        <SummaryCard label="Rejeitadas" value={summary.rejected || 0} color="slate" testid="summary-rejected" />
        <SummaryCard label="Valor coberto" value={formatCurrency(summary.total_amount)} color="orange" testid="summary-total-amount" />
      </div>

      {/* Open tasks */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Tarefas abertas ({openTasks.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {openTasks.length === 0 ? (
            <div className="p-8 text-center text-slate-500">
              Nenhuma tarefa aberta. Gere uma lista para começar.
            </div>
          ) : (
            <div className="divide-y">
              {openTasks.map((t) => (
                <TaskRow key={t.id} task={t} onAction={openAction} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Closed tasks (colapsável) */}
      {closedTasks.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-600">Já tratadas ({closedTasks.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y">
              {closedTasks.map((t) => (
                <TaskRow key={t.id} task={t} onAction={openAction} readonly />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Dialog acção */}
      <Dialog open={actionDialog.open} onOpenChange={(v) => !v && setActionDialog({ open: false, type: null, task: null })}>
        <DialogContent className="max-w-lg" data-testid="tasks-action-dialog">
          <DialogHeader>
            <DialogTitle>
              {actionDialog.type === 'done' && 'Marcar como Feita'}
              {actionDialog.type === 'postpone' && 'Adiar tarefa'}
              {actionDialog.type === 'convert' && 'Mudar ação'}
              {actionDialog.type === 'reject' && 'Não faz sentido'}
            </DialogTitle>
            <DialogDescription>
              {actionDialog.task?.client_name || 'Tarefa'} · {formatCurrency(actionDialog.task?.amount_collectable)} · {actionDialog.task?.days_overdue}d
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            {actionDialog.type === 'done' && (
              <div>
                <Label className="text-xs">Resultado (opcional)</Label>
                <Textarea
                  rows={3}
                  value={form.outcome || ''}
                  onChange={(e) => setForm({ ...form, outcome: e.target.value })}
                  placeholder="Ex: Cliente pagou, cliente vai enviar amanhã..."
                  data-testid="task-done-outcome"
                />
              </div>
            )}
            {actionDialog.type === 'postpone' && (
              <>
                <div>
                  <Label className="text-xs">Motivo *</Label>
                  <Select value={form.reason || ''} onValueChange={(v) => setForm({ ...form, reason: v })}>
                    <SelectTrigger data-testid="task-postpone-reason"><SelectValue placeholder="Selecionar..." /></SelectTrigger>
                    <SelectContent>
                      {POSTPONE_REASONS.map((r) => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Próxima data *</Label>
                  <Input
                    type="date"
                    value={form.next_action_date || ''}
                    onChange={(e) => setForm({ ...form, next_action_date: e.target.value })}
                    data-testid="task-postpone-date"
                  />
                </div>
                <div>
                  <Label className="text-xs">Nota (opcional)</Label>
                  <Textarea rows={2} value={form.note || ''} onChange={(e) => setForm({ ...form, note: e.target.value })} data-testid="task-postpone-note" />
                </div>
              </>
            )}
            {actionDialog.type === 'convert' && (
              <>
                <div>
                  <Label className="text-xs">Novo tipo *</Label>
                  <Select value={form.new_task_type || ''} onValueChange={(v) => setForm({ ...form, new_task_type: v })}>
                    <SelectTrigger data-testid="task-convert-type"><SelectValue placeholder="Escolher..." /></SelectTrigger>
                    <SelectContent>
                      {CONVERT_TARGETS.map(([k, l]) => (
                        <SelectItem key={k} value={k}>{l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Motivo (opcional)</Label>
                  <Textarea rows={2} value={form.reason || ''} onChange={(e) => setForm({ ...form, reason: e.target.value })} data-testid="task-convert-reason" />
                </div>
              </>
            )}
            {actionDialog.type === 'reject' && (
              <>
                <div>
                  <Label className="text-xs">Motivo *</Label>
                  <Select value={form.reason || ''} onValueChange={(v) => setForm({ ...form, reason: v })}>
                    <SelectTrigger data-testid="task-reject-reason"><SelectValue placeholder="Selecionar..." /></SelectTrigger>
                    <SelectContent>
                      {REJECT_REASONS.map((r) => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Nota{form.reason === 'other' ? ' *' : ' (opcional)'}</Label>
                  <Textarea rows={2} value={form.note || ''} onChange={(e) => setForm({ ...form, note: e.target.value })} data-testid="task-reject-note" />
                </div>
              </>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setActionDialog({ open: false, type: null, task: null })}>Cancelar</Button>
            <Button onClick={confirmAction} data-testid="task-action-confirm">Confirmar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SummaryCard({ label, value, color, testid }) {
  const styles = {
    blue:   'bg-blue-50 text-blue-800',
    green:  'bg-green-50 text-green-800',
    yellow: 'bg-yellow-50 text-yellow-800',
    purple: 'bg-purple-50 text-purple-800',
    slate:  'bg-slate-50 text-slate-700',
    orange: 'bg-orange-50 text-orange-800',
  };
  return (
    <Card className={styles[color]} data-testid={testid}>
      <CardContent className="p-3">
        <div className="text-xs">{label}</div>
        <div className="text-xl font-bold">{value}</div>
      </CardContent>
    </Card>
  );
}

function TaskRow({ task, onAction, readonly = false }) {
  const isUpload = task.task_type === 'UPLOAD_GENES_MAP';
  return (
    <div className={`p-4 hover:bg-slate-50 ${isUpload ? 'bg-amber-50' : ''}`} data-testid={`task-row-${task.id}`}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge className={STATUS_STYLE[task.status] || STATUS_STYLE.OPEN}>{task.status}</Badge>
            <span className="font-semibold text-slate-900">
              {TASK_TYPE_LABELS[task.task_type] || task.task_type}
            </span>
            {task.client_id && (
              <Link to={`/finance/clients/${task.client_id}`} className="text-orange-600 hover:underline">
                {task.client_name}
              </Link>
            )}
            {task.genes_code && <span className="text-xs text-slate-400">#{task.genes_code}</span>}
            {task.customer_segment && task.customer_segment !== 'UNKNOWN' && (
              <Badge variant="outline" className="text-xs">{task.customer_segment}</Badge>
            )}
            <span className="ml-auto text-xs text-slate-400">score {task.priority_score}</span>
          </div>
          <div className="text-sm text-slate-600 mt-1">{task.priority_reason}</div>
          <div className="text-sm text-slate-500 mt-0.5 italic">→ {task.suggested_action}</div>
          {task.client_id && (
            <div className="text-xs text-slate-400 mt-1 space-x-3">
              <span>Vencido: <strong className="text-red-600">{formatCurrency(task.amount_collectable)}</strong></span>
              <span>{task.days_overdue} dias</span>
              {task.bucket && <span>bucket {task.bucket}</span>}
            </div>
          )}
          {task.feedback_action && (
            <div className="text-xs text-slate-400 mt-1">
              → Fechada como <strong>{task.feedback_action}</strong>
              {task.feedback_reason && ` (${task.feedback_reason})`}
              {task.next_action_date && ` · Próxima: ${task.next_action_date}`}
            </div>
          )}
        </div>
        {!readonly && (
          <div className="flex gap-1 flex-shrink-0">
            <Button
              variant="outline" size="sm"
              onClick={() => onAction('done', task)}
              className="text-green-700"
              data-testid={`task-btn-done-${task.id}`}
            ><CheckCircle2 className="h-3.5 w-3.5 mr-1" />Feito</Button>
            <Button
              variant="outline" size="sm"
              onClick={() => onAction('postpone', task)}
              className="text-yellow-700"
              data-testid={`task-btn-postpone-${task.id}`}
            ><Clock className="h-3.5 w-3.5 mr-1" />Adiar</Button>
            <Button
              variant="outline" size="sm"
              onClick={() => onAction('convert', task)}
              className="text-purple-700"
              data-testid={`task-btn-convert-${task.id}`}
            ><Shuffle className="h-3.5 w-3.5 mr-1" />Mudar</Button>
            <Button
              variant="outline" size="sm"
              onClick={() => onAction('reject', task)}
              className="text-slate-500"
              data-testid={`task-btn-reject-${task.id}`}
            ><XCircle className="h-3.5 w-3.5 mr-1" />Não faz</Button>
          </div>
        )}
      </div>
    </div>
  );
}
