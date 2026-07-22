import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import {
  Bot, RefreshCw, CheckCircle2, AlertCircle, Users, ShieldAlert,
  MessageSquare, Truck, Car, Wrench,
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const MODULE_META = {
  pre_ticket:   { label: 'Pré-ticket',        icon: MessageSquare, colour: 'text-indigo-600' },
  renting:      { label: 'Renting',           icon: Car,           colour: 'text-emerald-600' },
  assistencias: { label: 'Assistências',      icon: Truck,         colour: 'text-orange-600' },
  mech_alert:   { label: 'Alertas Mecânica',  icon: Wrench,        colour: 'text-red-600' },
};

export default function AdminTelegramOverview() {
  const { getAuthHeaders } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API_URL}/api/telegram/internal/overview`, {
        headers: getAuthHeaders(),
      });
      setData(r.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const bot = data?.bot || {};
  const wh = data?.webhook || {};
  const counters = data?.counters || {};
  const modules = data?.modules || {};
  const logs = data?.recent_logs || [];

  return (
    <div className="space-y-6" data-testid="admin-telegram-overview">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-zinc-800 flex items-center gap-2">
            <Bot className="h-7 w-7 text-indigo-600" />
            Telegram — Visão Geral
          </h1>
          <p className="text-sm text-zinc-500 mt-1">Estado do bot interno e dos 4 módulos.</p>
        </div>
        <Button variant="outline" onClick={fetchData} disabled={loading} data-testid="tg-overview-refresh">
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Atualizar
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="text-xs uppercase text-zinc-500">Bot</div>
            {bot.configured ? (
              <div className="mt-1">
                <div className="flex items-center gap-2 text-green-700 font-mono text-lg">
                  <CheckCircle2 className="h-5 w-5" /> @{bot.username || '—'}
                </div>
                <div className="text-sm text-zinc-500 mt-1">{bot.first_name || ''}</div>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-amber-700 mt-1">
                <AlertCircle className="h-4 w-4" /> Não configurado
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="text-xs uppercase text-zinc-500">Webhook</div>
            <div className="text-sm mt-2 space-y-1">
              <div><span className="text-zinc-500">URL:</span>{' '}
                <span className="font-mono text-xs break-all">{wh.url_display || '—'}</span></div>
              <div><span className="text-zinc-500">Pending:</span>{' '}
                <span className="font-mono">{wh.pending_update_count ?? '—'}</span></div>
              {wh.last_error_message && (
                <div className="text-red-600 text-xs">Último erro: {wh.last_error_message}</div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="text-xs uppercase text-zinc-500">Utilizadores</div>
            <div className="mt-2 flex items-center gap-4">
              <div>
                <div className="text-2xl font-bold text-zinc-800 flex items-center gap-2">
                  <Users className="h-6 w-6 text-indigo-500" />
                  {counters.authorized_users ?? 0}
                </div>
                <div className="text-xs text-zinc-500">autorizados</div>
              </div>
              {(counters.needs_migration ?? 0) > 0 && (
                <div data-testid="tg-overview-needs-migration">
                  <div className="text-2xl font-bold text-amber-700 flex items-center gap-2">
                    <ShieldAlert className="h-6 w-6" />
                    {counters.needs_migration}
                  </div>
                  <div className="text-xs text-amber-700">precisam migração</div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Módulos</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(MODULE_META).map(([k, meta]) => {
              const Icon = meta.icon;
              return (
                <div key={k} data-testid={`tg-module-${k}`}
                     className="border border-zinc-200 rounded p-3 flex items-center gap-3">
                  <Icon className={`h-6 w-6 ${meta.colour}`} />
                  <div>
                    <div className="font-medium text-zinc-800">{meta.label}</div>
                    <div className="text-xs text-zinc-500">
                      {modules[k] ?? 0} utilizador(es) autorizado(s)
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Últimos eventos</CardTitle></CardHeader>
        <CardContent>
          {logs.length === 0 ? (
            <div className="text-sm text-zinc-500 text-center py-4">Sem eventos recentes.</div>
          ) : (
            <div className="space-y-1 text-sm font-mono">
              {logs.map((l, i) => (
                <div key={i} className="flex items-center gap-2 py-1 border-b border-zinc-100 last:border-none">
                  <span className="text-zinc-400 text-xs w-40 shrink-0">
                    {(l.created_at || '').slice(0, 19).replace('T', ' ')}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-zinc-100">
                    {l.module || 'unknown'}
                  </span>
                  <span className="text-xs">{l.message_type || '—'}</span>
                  <span className="text-xs text-zinc-500">chat={l.chat_id ?? '—'}</span>
                  {l.error && <span className="text-xs text-red-600 truncate">err</span>}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
