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
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '../components/ui/dialog';
import {
  Search, Loader2, ChevronRight, Calendar, FileText, AlertCircle,
  FileCheck, CheckCircle2, Ban, Truck, Download, BarChart3
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
  const { user, getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState({});
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [advancedStats, setAdvancedStats] = useState(null);
  const [showStats, setShowStats] = useState(false);
  const [statsLoading, setStatsLoading] = useState(false);

  const isOffice = user?.role === 'ADMIN' || user?.role === 'SUPERVISOR';

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

  const onExportCSV = async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      const r = await axios.get(`${API_URL}/api/assistencias/export/csv?${params.toString()}`, {
        headers: getAuthHeaders(), responseType: 'blob',
      });
      const blobUrl = URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `assistencias_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(blobUrl);
    } catch (e) {
      console.error('CSV export failed:', e);
    }
  };

  const onOpenStats = async () => {
    setShowStats(true);
    setStatsLoading(true);
    try {
      const r = await axios.get(`${API_URL}/api/assistencias/stats/advanced`, { headers: getAuthHeaders() });
      setAdvancedStats(r.data);
    } catch (e) {
      console.error('Stats failed:', e);
    } finally {
      setStatsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-zinc-900 flex items-center gap-2" data-testid="assistencias-title">
            <Truck className="h-8 w-8 text-orange-600" /> Assistências
          </h1>
          <p className="text-zinc-500 mt-1">Assistências externas e faturação associada.</p>
        </div>
        {isOffice && (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onOpenStats} data-testid="stats-btn">
              <BarChart3 className="h-4 w-4 mr-1" /> Estatísticas
            </Button>
            <Button variant="outline" size="sm" onClick={onExportCSV} data-testid="csv-btn">
              <Download className="h-4 w-4 mr-1" /> CSV
            </Button>
          </div>
        )}
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
                    <th className="text-left py-3 px-4 text-xs font-semibold text-zinc-600 uppercase">Cliente</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-zinc-600 uppercase">NIF</th>
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
                        <td className="py-3 px-4 text-sm">{r.invoice_customer || <span className="text-zinc-400">—</span>}</td>
                        <td className="py-3 px-4 text-sm font-mono">{r.invoice_nif || <span className="text-zinc-400">—</span>}</td>
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

      <Dialog open={showStats} onOpenChange={setShowStats}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Estatísticas Avançadas</DialogTitle>
          </DialogHeader>
          {statsLoading ? (
            <div className="py-8 text-center"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div>
          ) : advancedStats ? (
            <div className="space-y-6 max-h-[600px] overflow-y-auto">
              {/* Totals */}
              {advancedStats.totals?.count != null && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 bg-orange-50 rounded-lg border border-orange-200">
                    <div className="text-xs text-zinc-500">Total assistências</div>
                    <div className="text-2xl font-bold">{advancedStats.totals.count}</div>
                  </div>
                  <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200">
                    <div className="text-xs text-zinc-500">Faturado total</div>
                    <div className="text-2xl font-bold">{(advancedStats.totals.billed_total || 0).toFixed(2)} €</div>
                  </div>
                </div>
              )}
              {/* By employee */}
              {advancedStats.by_employee?.length > 0 && (
                <div>
                  <h3 className="font-semibold text-sm mb-2">Por Funcionário</h3>
                  <table className="w-full text-sm">
                    <thead className="bg-zinc-50 text-xs">
                      <tr>
                        <th className="text-left py-2 px-3">Funcionário</th>
                        <th className="text-center py-2 px-3">Total</th>
                        <th className="text-center py-2 px-3">Concluídas</th>
                        <th className="text-right py-2 px-3">Faturado €</th>
                      </tr>
                    </thead>
                    <tbody>
                      {advancedStats.by_employee.map((e) => (
                        <tr key={e.employee_id || e.employee_name} className="border-t">
                          <td className="py-2 px-3">{e.employee_name || '—'}</td>
                          <td className="text-center py-2 px-3 font-semibold">{e.count}</td>
                          <td className="text-center py-2 px-3 text-emerald-700">{e.billed_count}</td>
                          <td className="text-right py-2 px-3 font-mono">{e.billed_total.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {/* By month */}
              {advancedStats.by_month?.length > 0 && (
                <div>
                  <h3 className="font-semibold text-sm mb-2">Por Mês</h3>
                  <div className="space-y-1">
                    {advancedStats.by_month.map(m => (
                      <div key={m.month} className="flex items-center justify-between text-sm border-b py-1">
                        <span className="font-mono">{m.month}</span>
                        <span className="text-zinc-500">{m.count} assistências</span>
                        <span className="font-semibold">{m.billed_total.toFixed(2)} €</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center text-zinc-500 py-8">Sem dados</div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AssistenciasPage;
