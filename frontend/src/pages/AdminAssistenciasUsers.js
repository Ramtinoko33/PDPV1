import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import { Truck, Plus, RefreshCw, Trash2, CheckCircle2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function AdminAssistenciasUsers() {
  const { getAuthHeaders } = useAuth();
  const [users, setUsers] = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [botInfo, setBotInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(false);
  const [form, setForm] = useState({ telegram_user_id: '', user_id: '' });
  const [saving, setSaving] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState(`${API_URL}/api/assistencias/webhook`);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [bots, status, sysUsers] = await Promise.all([
        axios.get(`${API_URL}/api/assistencias/bot/users`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/assistencias/bot/status`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/users`, { headers: getAuthHeaders() }),
      ]);
      setUsers(bots.data || []);
      setBotInfo(status.data || null);
      setAllUsers(sysUsers.data || []);
    } catch (e) {
      console.error('Failed to load:', e);
      toast.error('Erro a carregar dados');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const onSave = async () => {
    if (!form.telegram_user_id || !form.user_id) {
      toast.error('Preencha Telegram ID e utilizador');
      return;
    }
    setSaving(true);
    try {
      await axios.post(`${API_URL}/api/assistencias/bot/users`, {
        telegram_user_id: parseInt(form.telegram_user_id, 10),
        user_id: form.user_id,
      }, { headers: getAuthHeaders() });
      toast.success('Autorização gravada');
      setDialog(false);
      setForm({ telegram_user_id: '', user_id: '' });
      fetchAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro a gravar');
    } finally {
      setSaving(false);
    }
  };

  const onRemove = async (telegramId) => {
    if (!window.confirm(`Remover Telegram ID ${telegramId}?`)) return;
    try {
      await axios.delete(`${API_URL}/api/assistencias/bot/users/${telegramId}`, { headers: getAuthHeaders() });
      toast.success('Removido');
      fetchAll();
    } catch (e) {
      toast.error('Erro a remover');
    }
  };

  const onConfigureWebhook = async () => {
    if (!webhookUrl) return;
    try {
      const r = await axios.post(`${API_URL}/api/assistencias/bot/webhook/configure`, { url: webhookUrl }, { headers: getAuthHeaders() });
      if (r.data?.ok) {
        toast.success('Webhook configurado');
        fetchAll();
      } else {
        toast.error('Falha a configurar webhook');
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro');
    }
  };

  const eligibleUsers = allUsers.filter(u =>
    u.has_assistencias_access || ['ADMIN', 'SUPERVISOR'].includes(u.role)
  );

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Truck className="h-7 w-7 text-orange-600" /> Bot de Assistências
          </h1>
          <p className="text-zinc-500 mt-1">Gerir bot e funcionários autorizados a criar assistências.</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchAll} data-testid="refresh-btn">
          <RefreshCw className="h-4 w-4 mr-1" /> Atualizar
        </Button>
      </div>

      {/* Bot status */}
      <Card>
        <CardHeader><CardTitle className="text-base">Estado do Bot</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {botInfo?.configured ? (
            <div className="flex items-center gap-2 text-emerald-700">
              <CheckCircle2 className="h-5 w-5" />
              <span className="font-medium">
                {botInfo.telegram_getMe?.first_name || 'Bot'}
                {botInfo.telegram_getMe?.username && (
                  <span className="text-zinc-500 ml-2">@{botInfo.telegram_getMe.username}</span>
                )}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-amber-700">
              <AlertCircle className="h-5 w-5" />
              <span>Bot não configurado: <code className="text-xs bg-zinc-100 px-1 rounded">TELEGRAM_ASSISTENCIAS_BOT_TOKEN</code> em falta no backend/.env</span>
            </div>
          )}
          <div className="flex flex-wrap gap-2 items-end pt-2">
            <div className="flex-1 min-w-[300px]">
              <Label className="text-xs">URL do webhook</Label>
              <Input value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} data-testid="webhook-url" />
            </div>
            <Button onClick={onConfigureWebhook} disabled={!botInfo?.configured} data-testid="set-webhook-btn">
              Aplicar Webhook
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Authorized users */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Funcionários Autorizados ({users.length})</CardTitle>
          <Button size="sm" onClick={() => setDialog(true)} data-testid="add-user-btn">
            <Plus className="h-4 w-4 mr-1" /> Autorizar
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8 text-zinc-500">A carregar...</div>
          ) : users.length === 0 ? (
            <div className="text-center py-8 text-zinc-500" data-testid="empty-bot-users">
              Ninguém autorizado ainda.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Telegram ID</TableHead>
                  <TableHead>Utilizador</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Adicionado</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map(u => (
                  <TableRow key={u.id} data-testid={`bot-user-${u.telegram_user_id}`}>
                    <TableCell className="font-mono">{u.telegram_user_id}</TableCell>
                    <TableCell>{u.user_name || '—'}</TableCell>
                    <TableCell>
                      {u.active ? <Badge className="bg-emerald-100 text-emerald-700">Ativo</Badge> : <Badge variant="secondary">Inativo</Badge>}
                    </TableCell>
                    <TableCell className="text-xs text-zinc-500">
                      {u.added_at ? new Date(u.added_at).toLocaleDateString('pt-PT') : '—'}
                    </TableCell>
                    <TableCell>
                      <Button size="icon" variant="ghost" onClick={() => onRemove(u.telegram_user_id)} data-testid={`remove-${u.telegram_user_id}`}>
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Add dialog */}
      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Autorizar Funcionário no Bot</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Telegram User ID *</Label>
              <Input
                type="number"
                placeholder="ex: 123456789"
                value={form.telegram_user_id}
                onChange={(e) => setForm(f => ({ ...f, telegram_user_id: e.target.value }))}
                data-testid="tg-id-input"
              />
              <p className="text-xs text-zinc-500 mt-1">
                Para descobrir: peça à pessoa para enviar uma mensagem para <code>@userinfobot</code> no Telegram.
              </p>
            </div>
            <div>
              <Label>Conta de Sistema *</Label>
              <Select value={form.user_id} onValueChange={(v) => setForm(f => ({ ...f, user_id: v }))}>
                <SelectTrigger data-testid="user-select"><SelectValue placeholder="Selecione..." /></SelectTrigger>
                <SelectContent>
                  {eligibleUsers.map(u => (
                    <SelectItem key={u.id} value={u.id}>
                      {u.name} ({u.email}) — {u.role}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-zinc-500 mt-1">
                Só aparecem utilizadores com <strong>has_assistencias_access</strong> ativo (ou ADMIN/SUPERVISOR).
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(false)}>Cancelar</Button>
            <Button onClick={onSave} disabled={saving} data-testid="save-btn">
              {saving ? 'A gravar...' : 'Gravar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
