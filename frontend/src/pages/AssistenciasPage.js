import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../components/ui/select';
import {
  Search, Loader2, ChevronRight, Calendar, FileText, AlertCircle,
  FileCheck, CheckCircle2, Ban, Truck
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STATUS_META = {
  AGUARDA_FATURACAO:    { label: 'Aguarda Faturação', color: 'bg-amber-100 text-amber-800 border border-amber-200' },
  DADOS_INCOMPLETOS:    { label: 'Dados Incompletos', color: 'bg-red-100 text-red-800 border border-red-200' },
  FATURA_ANALISADA:     { label: 'Fatura Analisada',   color: 'bg-blue-100 text-blue-800 border border-blue-200' },
  FATURA_CONFIRMADA:    { label: 'Fatura Confirmada',  color: 'bg-indigo-100 text-indigo-800 border border-indigo-200' },
  ENVIADA_FUNCIONARIO:  { label: 'Enviada ao Func.',   color: 'bg-cyan-100 text-cyan-800 border border-cyan-200' },
  FATURADA_CONCLUIDA:   { label: 'Concluída',          color: 'bg-emerald-100 text-emerald-800 border border-emerald-200' },
  NAO_FATURAVEL:        { label: 'Não Faturável',      color: 'bg-zinc-200 text-zinc-700 border border-zinc-300' },
};

const formatDateTime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-PT', {
      day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
};

const StatCard = ({ icon: Icon, label, value, tone, testid }) => (
  <Card data-testid={testid}>
    <CardContent className="pt-6">
      <div className="flex items-center gap-4">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center ${tone}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-sm text-zinc-500">{label}</p>
        </div>
      </div>
    </CardContent>
  </Card>
);

const AssistenciasPage = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState({});
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (search.trim()) params.set('search', search.trim());
      const [recordsR, statsR] = await Promise.all([
        axios.get(`${API_URL}/api/assistencias/records?${params.toString()}`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/assistencias/stats`, { headers: getAuthHeaders() }),
      ]);
      setRecords(recordsR.data.items || []);
      setStats(statsR.data || {});
    } catch (e) {
      console.error('Failed to load assistencias:', e);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, search, getAuthHeaders]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-zinc-900 flex items-center gap-2" data-testid="assistencias-title">
            <Truck className="h-8 w-8 text-orange-600" /> Assistências
          </h1>
          <p className="text-zinc-500 mt-1">Assistências externas e faturação associada.</p>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        <StatCard icon={Calendar}    label="Hoje"               value={stats.today || 0}                       tone="bg-orange-100 text-orange-700" testid="stat-today" />
        <StatCard icon={FileText}    label="A Faturar"          value={stats.AGUARDA_FATURACAO || 0}           tone="bg-amber-100 text-amber-700"   testid="stat-aguarda" />
        <StatCard icon={AlertCircle} label="Incompletas"        value={stats.DADOS_INCOMPLETOS || 0}           tone="bg-red-100 text-red-700"       testid="stat-incompleta" />
        <StatCard icon={FileCheck}   label="Fatura Carregada"   value={(stats.FATURA_ANALISADA || 0) + (stats.FATURA_CONFIRMADA || 0) + (stats.ENVIADA_FUNCIONARIO || 0)} tone="bg-blue-100 text-blue-700" testid="stat-fatura" />
        <StatCard icon={CheckCircle2} label="Concluídas"        value={stats.FATURADA_CONCLUIDA || 0}          tone="bg-emerald-100 text-emerald-700" testid="stat-concluida" />
        <StatCard icon={Ban}         label="Não Faturável"      value={stats.NAO_FATURAVEL || 0}               tone="bg-zinc-100 text-zinc-700"     testid="stat-nao" />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-400" />
          <Input
            placeholder="Pesquisar (matrícula, fatura, cliente, funcionário)..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()}
            className="pl-9"
            data-testid="search-input"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[220px]" data-testid="status-filter">
            <SelectValue placeholder="Estado" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os estados</SelectItem>
            {Object.entries(STATUS_META).map(([k, m]) => (
              <SelectItem key={k} value={k}>{m.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-orange-600" />
            </div>
          ) : records.length === 0 ? (
            <div className="text-center py-12 text-zinc-500" data-testid="empty-state">
              Nenhuma assistência encontrada.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-zinc-50 border-b">
                  <tr>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-zinc-600 uppercase">Data</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-zinc-600 uppercase">Matrícula</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-zinc-600 uppercase">Funcionário</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-zinc-600 uppercase">Estado</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-zinc-600 uppercase">Fatura</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-zinc-600 uppercase">Total</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {records.map(r => {
                    const m = STATUS_META[r.status] || { label: r.status, color: 'bg-zinc-100' };
                    return (
                      <tr
                        key={r.id}
                        className="border-b hover:bg-orange-50/40 cursor-pointer"
                        onClick={() => navigate(`/assistencias/${r.id}`)}
                        data-testid={`row-${r.id}`}
                      >
                        <td className="py-3 px-4 text-sm">{formatDateTime(r.created_at)}</td>
                        <td className="py-3 px-4 font-mono font-semibold text-zinc-900">{r.registration_plate || '—'}</td>
                        <td className="py-3 px-4 text-sm">{r.employee_name || '—'}</td>
                        <td className="py-3 px-4"><Badge className={m.color}>{m.label}</Badge></td>
                        <td className="py-3 px-4 text-sm">{r.invoice_number || <span className="text-zinc-400">—</span>}</td>
                        <td className="py-3 px-4 text-sm text-right font-semibold">
                          {r.invoice_total != null ? `${Number(r.invoice_total).toFixed(2)} €` : '—'}
                        </td>
                        <td className="py-3 px-2 text-zinc-400">
                          <ChevronRight className="h-4 w-4" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AssistenciasPage;
