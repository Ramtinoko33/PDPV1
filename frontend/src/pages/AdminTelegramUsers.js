import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import { Checkbox } from '../components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import { Bot, Plus, RefreshCw, Trash2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const FLOW_OPTIONS = [
  { key: 'pre_ticket', label: 'Pré-ticket (aberto IA)' },
  { key: 'renting', label: 'Renting (deep-link)' },
  { key: 'mech_alert', label: 'Alerta Mecânica (deep-link)' },
];

export default function AdminTelegramUsers() {
  const { getAuthHeaders } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [botInfo, setBotInfo] = useState(null);
  const [dialog, setDialog] = useState(false);
  const [form, setForm] = useState({
    telegram_user_id: '',
    name: '',
    role: 'AGENT',
    allowed_flows: ['pre_ticket', 'renting', 'mech_alert'],
    active: true,
  });
  const [saving, setSaving] = useState(false);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API_URL}/api/telegram/internal/authorized-users`, {
        headers: getAuthHeaders(),
      });
      setUsers(r.data || []);
    } catch (e) {
      toast.error('Erro ao carregar utilizadores');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  const fetchBotInfo = useCallback(async () => {
    try {
      const r = await axios.get(`${API_URL}/api/telegram/internal/info`, {
        headers: getAuthHeaders(),
      });
      setBotInfo(r.data);
    } catch {
      setBotInfo({ configured: false });
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    fetchUsers();
    fetchBotInfo();
  }, [fetchUsers, fetchBotInfo]);

  const openCreate = () => {
    setForm({
      telegram_user_id: '',
      name: '',
      role: 'AGENT',
      allowed_flows: ['pre_ticket', 'renting', 'mech_alert'],
      active: true,
    });
    setDialog(true);
  };

  const handleSave = async () => {
    const tid = parseInt(form.telegram_user_id, 10);
    if (!tid || !form.name.trim()) {
      toast.error('Telegram user ID e nome são obrigatórios');
      return;
    }
    if (form.allowed_flows.length === 0) {
      toast.error('Selecciona pelo menos um fluxo');
      return;
    }
    setSaving(true);
    try {
      await axios.post(
        `${API_URL}/api/telegram/internal/authorized-users`,
        { ...form, telegram_user_id: tid },
        { headers: getAuthHeaders() }
      );
      toast.success('Utilizador autorizado');
      setDialog(false);
      fetchUsers();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro a guardar');
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivate = async (tid) => {
    if (!window.confirm('Desativar este utilizador no bot interno?')) return;
    try {
      await axios.delete(`${API_URL}/api/telegram/internal/authorized-users/${tid}`, {
        headers: getAuthHeaders(),
      });
      toast.success('Utilizador desativado');
      fetchUsers();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro a desativar');
    }
  };

  const toggleFlow = (key) => {
    setForm((f) => ({
      ...f,
      allowed_flows: f.allowed_flows.includes(key)
        ? f.allowed_flows.filter((x) => x !== key)
        : [...f.allowed_flows, key],
    }));
  };

  return (
    <div className="space-y-6" data-testid="admin-telegram-users-page">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-zinc-800 flex items-center gap-2">
            <Bot className="h-7 w-7 text-indigo-600" />
            Utilizadores do Bot Interno
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Gestão de quem pode usar o <strong>PDPV Bot Interno</strong> (Telegram). Apenas utilizadores ativos podem enviar pré-tickets.
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => { fetchUsers(); fetchBotInfo(); }} variant="outline" className="gap-2">
            <RefreshCw className="h-4 w-4" /> Atualizar
          </Button>
          <Button onClick={openCreate} className="gap-2 bg-indigo-600 hover:bg-indigo-700" data-testid="add-telegram-user-btn">
            <Plus className="h-4 w-4" /> Autorizar Utilizador
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-4">
          {botInfo?.configured ? (
            <div className="flex items-center gap-2 text-sm text-green-700">
              <CheckCircle2 className="h-4 w-4" />
              Bot ligado:{' '}
              <span className="font-mono">
                @{botInfo.telegram_getMe?.username || botInfo.telegram_getMe?.result?.username || '—'}
              </span>
              {' · '}
              <span>{botInfo.telegram_getMe?.first_name || botInfo.telegram_getMe?.result?.first_name || ''}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-amber-700">
              <AlertCircle className="h-4 w-4" />
              Bot não configurado.{' '}
              {botInfo?.reason || 'Defina TELEGRAM_INTERNAL_BOT_TOKEN no backend.'}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Lista ({users.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-24">
              <RefreshCw className="h-6 w-6 animate-spin text-zinc-400" />
            </div>
          ) : users.length === 0 ? (
            <div className="text-center py-8 text-zinc-500">
              <Bot className="h-12 w-12 mx-auto mb-3 text-zinc-300" />
              <p>Nenhum utilizador autorizado.</p>
              <p className="text-sm mt-1">Adiciona pelo menos um para começar a testar o bot interno.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Telegram ID</TableHead>
                  <TableHead>Nome</TableHead>
                  <TableHead>Cargo</TableHead>
                  <TableHead>Fluxos Permitidos</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.telegram_user_id} data-testid={`tg-user-row-${u.telegram_user_id}`}>
                    <TableCell className="font-mono">{u.telegram_user_id}</TableCell>
                    <TableCell className="font-medium">{u.name}</TableCell>
                    <TableCell>{u.role}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {(u.allowed_flows || []).map((f) => (
                          <span key={f} className="px-2 py-0.5 rounded text-[11px] bg-indigo-50 text-indigo-700">
                            {f}
                          </span>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      {u.active ? (
                        <span className="inline-flex items-center gap-1 text-green-700 text-xs">
                          <CheckCircle2 className="h-3 w-3" /> Ativo
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-zinc-400 text-xs">Inativo</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {u.active && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDeactivate(u.telegram_user_id)}
                          data-testid={`tg-user-deactivate-${u.telegram_user_id}`}
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                          title="Desativar"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Plus className="h-5 w-5 text-indigo-600" /> Autorizar Utilizador
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Telegram User ID *</Label>
              <Input
                type="number"
                placeholder="Ex: 123456789"
                value={form.telegram_user_id}
                onChange={(e) => setForm({ ...form, telegram_user_id: e.target.value })}
                data-testid="tg-user-id-input"
              />
              <p className="text-xs text-zinc-500 mt-1">
                Cada utilizador descobre o seu ID em @userinfobot ou {' '}
                <span className="font-mono">/start</span> no bot e olha pelos logs.
              </p>
            </div>
            <div>
              <Label>Nome *</Label>
              <Input
                placeholder="Nome do funcionário"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                data-testid="tg-user-name-input"
              />
            </div>
            <div>
              <Label>Cargo</Label>
              <Select
                value={form.role}
                onValueChange={(v) => setForm({ ...form, role: v })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="AGENT">AGENT</SelectItem>
                  <SelectItem value="SUPERVISOR">SUPERVISOR</SelectItem>
                  <SelectItem value="ADMIN">ADMIN</SelectItem>
                  <SelectItem value="MECHANIC">MECHANIC</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Fluxos Permitidos</Label>
              <div className="space-y-2 mt-2">
                {FLOW_OPTIONS.map((opt) => (
                  <label
                    key={opt.key}
                    className="flex items-center gap-2 text-sm cursor-pointer"
                  >
                    <Checkbox
                      checked={form.allowed_flows.includes(opt.key)}
                      onCheckedChange={() => toggleFlow(opt.key)}
                      data-testid={`tg-flow-${opt.key}`}
                    />
                    <span>{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(false)}>Cancelar</Button>
            <Button
              onClick={handleSave}
              disabled={saving}
              className="bg-indigo-600 hover:bg-indigo-700"
              data-testid="tg-user-save-btn"
            >
              {saving ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : null}
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
