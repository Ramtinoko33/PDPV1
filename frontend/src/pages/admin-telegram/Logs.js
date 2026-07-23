import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from '../../components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../../components/ui/table';
import { FileText, RefreshCw, Filter } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const MODULES = ['pre_ticket', 'renting', 'assistencias', 'mech_alert', 'admin', 'unknown'];

export default function AdminTelegramLogs() {
  const { getAuthHeaders } = useAuth();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    limit: 100,
    kind: 'all',
    module: 'all',
    chat_id: '',
    since: '',
  });

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(filters.limit));
      if (filters.kind && filters.kind !== 'all') params.set('kind', filters.kind);
      if (filters.module && filters.module !== 'all') params.set('module', filters.module);
      if (filters.chat_id) params.set('chat_id', filters.chat_id);
      if (filters.since) params.set('since', filters.since);
      const r = await axios.get(`${API_URL}/api/telegram/internal/logs?${params}`, {
        headers: getAuthHeaders(),
      });
      setRows(r.data?.logs || []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders, filters]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  return (
    <div className="space-y-6" data-testid="admin-telegram-logs">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-zinc-800 flex items-center gap-2">
            <FileText className="h-7 w-7 text-indigo-600" />
            Telegram — Logs
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Eventos do bot interno. Nunca contêm token, URL com token, file_path ou conteúdo bruto.
          </p>
        </div>
        <Button variant="outline" onClick={fetchLogs} disabled={loading} data-testid="tg-logs-refresh">
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Atualizar
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Filter className="h-4 w-4" /> Filtros
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div>
            <Label className="text-xs">Módulo</Label>
            <Select value={filters.module}
                    onValueChange={(v) => setFilters(f => ({ ...f, module: v }))}>
              <SelectTrigger data-testid="tg-logs-filter-module"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {MODULES.map(m => (<SelectItem key={m} value={m}>{m}</SelectItem>))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Tipo</Label>
            <Select value={filters.kind}
                    onValueChange={(v) => setFilters(f => ({ ...f, kind: v }))}>
              <SelectTrigger data-testid="tg-logs-filter-kind"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="error">Só erros</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Chat ID</Label>
            <Input placeholder="Ex: 123456789" value={filters.chat_id}
                   onChange={(e) => setFilters(f => ({ ...f, chat_id: e.target.value }))}
                   data-testid="tg-logs-filter-chat-id" />
          </div>
          <div>
            <Label className="text-xs">Desde (ISO)</Label>
            <Input placeholder="2026-02-20T00:00:00Z" value={filters.since}
                   onChange={(e) => setFilters(f => ({ ...f, since: e.target.value }))}
                   data-testid="tg-logs-filter-since" />
          </div>
          <div>
            <Label className="text-xs">Limite</Label>
            <Input type="number" min={1} max={500} value={filters.limit}
                   onChange={(e) => setFilters(f => ({ ...f, limit: parseInt(e.target.value || '100', 10) }))}
                   data-testid="tg-logs-filter-limit" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Eventos ({rows.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Timestamp</TableHead>
                <TableHead>Módulo</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Ação</TableHead>
                <TableHead>Chat</TableHead>
                <TableHead>User (TG)</TableHead>
                <TableHead>User Sistema</TableHead>
                <TableHead>HTTP</TableHead>
                <TableHead>ms</TableHead>
                <TableHead>Erro</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((l, i) => (
                <TableRow key={i} data-testid="tg-logs-row">
                  <TableCell className="font-mono text-xs">
                    {(l.created_at || '').slice(0, 19).replace('T', ' ')}
                  </TableCell>
                  <TableCell>
                    <span className="text-xs px-2 py-0.5 rounded bg-zinc-100">
                      {l.module || 'unknown'}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs">{l.message_type || '—'}</TableCell>
                  <TableCell className="text-xs font-mono">{l.callback_action || '—'}</TableCell>
                  <TableCell className="font-mono text-xs">{l.chat_id ?? '—'}</TableCell>
                  <TableCell className="font-mono text-xs">{l.telegram_user_id ?? '—'}</TableCell>
                  <TableCell className="font-mono text-xs">{l.internal_user_id ? String(l.internal_user_id).slice(0, 8) + '…' : '—'}</TableCell>
                  <TableCell className="font-mono text-xs">{l.http_status ?? '—'}</TableCell>
                  <TableCell className="font-mono text-xs">{l.processing_time_ms ?? '—'}</TableCell>
                  <TableCell className="text-red-600 text-xs max-w-xs truncate">
                    {l.error_id ? <span className="font-mono">{l.error_id} </span> : ''}
                    {l.error || ''}
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={10} className="text-center py-8 text-zinc-500">
                    Sem eventos.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
