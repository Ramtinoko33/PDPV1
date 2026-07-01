import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Textarea } from '../../components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../components/ui/dialog';
import axios from 'axios';
import { toast } from 'sonner';
import { RefreshCw, Ban, ShieldCheck, ShieldX, Unlock } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const formatCurrency = (value) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(value || 0);

const formatDateTime = (dateStr) => (dateStr ? new Date(dateStr).toLocaleString('pt-PT') : '-');

const STATUS_META = {
  pending: { label: 'Pendente', style: 'bg-orange-100 text-orange-800' },
  approved: { label: 'Aprovado', style: 'bg-red-100 text-red-800' },
  rejected: { label: 'Rejeitado', style: 'bg-slate-100 text-slate-700' },
};

const BlockRequests = () => {
  const { user, getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [requests, setRequests] = useState([]);
  const [blockedClients, setBlockedClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accessDenied, setAccessDenied] = useState(false);
  const [reviewDialog, setReviewDialog] = useState(null); // {request, approved}
  const [unblockDialog, setUnblockDialog] = useState(null); // client
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const canReview = user?.role === 'ADMIN' || ['OWNER', 'FINANCE_REVIEWER'].includes(user?.finance_role);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [reqRes, blockedRes] = await Promise.all([
        axios.get(`${API_URL}/api/finance/block-requests`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/finance/clients?is_blocked=true&page_size=100`, { headers: getAuthHeaders() }),
      ]);
      setRequests(reqRes.data.requests || []);
      setBlockedClients(blockedRes.data.clients || []);
      setAccessDenied(false);
    } catch (err) {
      if (err.response?.status === 403) {
        setAccessDenied(true);
      }
      console.error('Erro ao carregar bloqueios:', err);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleReview = async () => {
    if (!reviewDialog) return;
    setSaving(true);
    try {
      await axios.post(
        `${API_URL}/api/finance/block-requests/${reviewDialog.request.id}/review`,
        { approved: reviewDialog.approved, review_notes: notes || null },
        { headers: getAuthHeaders() }
      );
      toast.success(reviewDialog.approved ? 'Bloqueio aprovado — cliente bloqueado' : 'Pedido de bloqueio rejeitado');
      setReviewDialog(null);
      setNotes('');
      fetchData();
    } catch (err) {
      console.error('Erro ao rever pedido:', err);
      toast.error(err.response?.data?.detail || 'Erro ao processar pedido');
    } finally {
      setSaving(false);
    }
  };

  const handleUnblock = async () => {
    if (!unblockDialog) return;
    setSaving(true);
    try {
      await axios.post(
        `${API_URL}/api/finance/clients/${unblockDialog.id}/unblock?reason=${encodeURIComponent(notes || 'Desbloqueado')}`,
        {},
        { headers: getAuthHeaders() }
      );
      toast.success('Cliente desbloqueado');
      setUnblockDialog(null);
      setNotes('');
      fetchData();
    } catch (err) {
      console.error('Erro ao desbloquear:', err);
      toast.error(err.response?.data?.detail || 'Erro ao desbloquear cliente');
    } finally {
      setSaving(false);
    }
  };

  if (accessDenied) {
    return (
      <div className="p-8 text-center" data-testid="block-requests-access-denied">
        <Ban className="h-10 w-10 text-slate-300 mx-auto mb-3" />
        <p className="text-slate-600 font-medium">Acesso restrito</p>
        <p className="text-slate-500 text-sm mt-1">
          Esta página requer permissão de FINANCE_REVIEWER ou OWNER.
        </p>
      </div>
    );
  }

  const pending = requests.filter((r) => r.status === 'pending');
  const history = requests.filter((r) => r.status !== 'pending');

  return (
    <div className="space-y-6" data-testid="block-requests-page">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Bloqueios</h1>
          <p className="text-slate-500 text-sm">Pedidos de bloqueio de crédito e clientes bloqueados</p>
        </div>
        <Button variant="outline" onClick={fetchData} data-testid="block-requests-refresh-btn">
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Pedidos pendentes */}
      <Card className={pending.length > 0 ? 'border-orange-300' : ''}>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Ban className="h-5 w-5 text-orange-600" />
            Pedidos Pendentes ({pending.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {pending.length === 0 ? (
            <p className="p-6 text-center text-slate-500 text-sm">Sem pedidos pendentes</p>
          ) : (
            <div className="divide-y">
              {pending.map((r) => (
                <div key={r.id} className="p-4 flex flex-col md:flex-row md:items-center gap-3" data-testid={`block-request-pending-${r.id}`}>
                  <div className="flex-1">
                    <button
                      className="font-semibold text-slate-900 hover:text-orange-600 hover:underline"
                      onClick={() => navigate(`/finance/clients/${r.client_id}`)}
                    >
                      {r.client_name}
                    </button>
                    <p className="text-sm text-slate-600 mt-0.5">{r.reason}</p>
                    <p className="text-xs text-slate-400 mt-1">
                      Sugerido por {r.suggested_by_name} · {formatDateTime(r.suggested_at)}
                    </p>
                  </div>
                  {canReview && (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        className="bg-red-600 hover:bg-red-700"
                        onClick={() => { setNotes(''); setReviewDialog({ request: r, approved: true }); }}
                        data-testid={`block-request-approve-btn-${r.id}`}
                      >
                        <ShieldX className="h-4 w-4 mr-1.5" />
                        Aprovar Bloqueio
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => { setNotes(''); setReviewDialog({ request: r, approved: false }); }}
                        data-testid={`block-request-reject-btn-${r.id}`}
                      >
                        Rejeitar
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Clientes bloqueados */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <ShieldX className="h-5 w-5 text-red-600" />
            Clientes Bloqueados ({blockedClients.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {blockedClients.length === 0 ? (
            <p className="p-6 text-center text-slate-500 text-sm">Nenhum cliente bloqueado</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50 border-b">
                  <tr>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Cliente</th>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Código</th>
                    <th className="text-right p-3 text-sm font-medium text-slate-600">Vencido Cobrável</th>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Motivo</th>
                    <th className="text-center p-3 text-sm font-medium text-slate-600"></th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {blockedClients.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50" data-testid={`blocked-client-row-${c.genes_code}`}>
                      <td className="p-3 text-sm">
                        <button
                          className="font-medium text-slate-900 hover:text-orange-600 hover:underline"
                          onClick={() => navigate(`/finance/clients/${c.id}`)}
                        >
                          {c.name}
                        </button>
                      </td>
                      <td className="p-3 text-sm text-slate-500">#{c.genes_code}</td>
                      <td className="p-3 text-sm text-right font-semibold text-red-700">
                        {formatCurrency(c.overdue_balance_collectable)}
                      </td>
                      <td className="p-3 text-sm text-slate-500 max-w-[240px] truncate" title={c.block_reason || ''}>
                        {c.block_reason || '-'}
                      </td>
                      <td className="p-3 text-center">
                        {canReview && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => { setNotes(''); setUnblockDialog(c); }}
                            data-testid={`unblock-client-btn-${c.genes_code}`}
                          >
                            <Unlock className="h-3.5 w-3.5 mr-1.5" />
                            Desbloquear
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Histórico */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-slate-500" />
            Histórico de Pedidos ({history.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {history.length === 0 ? (
            <p className="p-6 text-center text-slate-500 text-sm">Sem histórico</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50 border-b">
                  <tr>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Cliente</th>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Motivo</th>
                    <th className="text-center p-3 text-sm font-medium text-slate-600">Decisão</th>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Revisto por</th>
                    <th className="text-left p-3 text-sm font-medium text-slate-600">Data</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {history.map((r) => {
                    const meta = STATUS_META[r.status] || STATUS_META.pending;
                    return (
                      <tr key={r.id} className="hover:bg-slate-50" data-testid={`block-request-history-${r.id}`}>
                        <td className="p-3 text-sm font-medium">{r.client_name}</td>
                        <td className="p-3 text-sm text-slate-500 max-w-[240px] truncate" title={r.reason}>{r.reason}</td>
                        <td className="p-3 text-center"><Badge className={meta.style}>{meta.label}</Badge></td>
                        <td className="p-3 text-sm text-slate-600">{r.reviewed_by_name || '-'}</td>
                        <td className="p-3 text-sm text-slate-500">{formatDateTime(r.reviewed_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dialog aprovar/rejeitar */}
      <Dialog open={!!reviewDialog} onOpenChange={(open) => !open && setReviewDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {reviewDialog?.approved ? 'Aprovar Bloqueio' : 'Rejeitar Pedido de Bloqueio'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              Cliente: <strong>{reviewDialog?.request?.client_name}</strong>
            </p>
            <p className="text-sm text-slate-500">Motivo do pedido: {reviewDialog?.request?.reason}</p>
            {reviewDialog?.approved && (
              <p className="text-sm text-red-600 font-medium">
                ⚠️ O cliente ficará BLOQUEADO para novo crédito.
              </p>
            )}
            <Textarea
              placeholder="Notas de revisão (opcional)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              data-testid="block-review-notes-input"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewDialog(null)}>Cancelar</Button>
            <Button
              className={reviewDialog?.approved ? 'bg-red-600 hover:bg-red-700' : ''}
              onClick={handleReview}
              disabled={saving}
              data-testid="block-review-confirm-btn"
            >
              {saving ? 'A processar...' : reviewDialog?.approved ? 'Confirmar Bloqueio' : 'Confirmar Rejeição'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog desbloquear */}
      <Dialog open={!!unblockDialog} onOpenChange={(open) => !open && setUnblockDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desbloquear Cliente</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              Cliente: <strong>{unblockDialog?.name}</strong>
            </p>
            <Textarea
              placeholder="Motivo do desbloqueio *"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              data-testid="unblock-reason-input"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUnblockDialog(null)}>Cancelar</Button>
            <Button
              onClick={handleUnblock}
              disabled={saving || !notes.trim()}
              data-testid="unblock-confirm-btn"
            >
              {saving ? 'A processar...' : 'Desbloquear'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default BlockRequests;
