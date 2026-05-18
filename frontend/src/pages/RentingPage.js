import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Car, Search, Loader2, ChevronRight, BellRing } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STATUS_LABELS = {
  draft: { label: 'Rascunho', color: 'bg-amber-100 text-amber-700' },
  in_progress: { label: 'Em tratamento', color: 'bg-blue-100 text-blue-700' },
  completed: { label: 'Concluído', color: 'bg-emerald-100 text-emerald-700' },
};

const SUBTYPE_BADGE = (subtype) => {
  if (subtype === 'adblue') return <Badge variant="secondary" className="bg-blue-100 text-blue-700">⛽ AdBlue</Badge>;
  if (subtype === 'tires') return <Badge variant="secondary" className="bg-orange-100 text-orange-700">🛞 Pneus</Badge>;
  if (subtype === 'puncture') return <Badge variant="secondary" className="bg-red-100 text-red-700">🔧 Furo</Badge>;
  if (subtype === 'other') return <Badge variant="secondary" className="bg-purple-100 text-purple-700">📝 Outro</Badge>;
  return null;
};

const formatDateTime = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
};

const RentingPage = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState({ draft: 0, in_progress: 0, completed: 0, total: 0, tires: 0, adblue: 0, puncture: 0, other: 0, pending_unseen: 0 });
  const [records, setRecords] = useState([]);
  const [pendingUnseen, setPendingUnseen] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [subtypeFilter, setSubtypeFilter] = useState('all');
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (subtypeFilter !== 'all') params.set('subtype', subtypeFilter);
      if (search.trim()) params.set('search', search.trim());
      const [recRes, statsRes, unseenRes] = await Promise.all([
        axios.get(`${API_URL}/api/renting/records?${params}`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/renting/stats`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/renting/records?status=unseen&page_size=20`, { headers: getAuthHeaders() }),
      ]);
      setRecords(recRes.data.items || []);
      setStats(statsRes.data || {});
      setPendingUnseen(unseenRes.data.items || []);
    } catch (e) {
      // silent
    } finally {
      setLoading(false);
    }
  }, [statusFilter, subtypeFilter, search, getAuthHeaders]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6" data-testid="renting-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Car className="h-6 w-6 text-orange-500" /> Renting</h1>
          <p className="text-sm text-zinc-500">Pedidos rápidos de pneus para viaturas de renting/frota</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        <StatCard label="Por ler" value={stats.pending_unseen} color="text-red-600" testId="stat-pending-unseen" />
        <StatCard label="Em tratamento" value={stats.in_progress} color="text-blue-600" />
        <StatCard label="Concluídos" value={stats.completed} color="text-emerald-600" />
        <StatCard label="Total" value={stats.total} />
        <StatCard label="🛞 Pneus" value={stats.tires} color="text-orange-600" />
        <StatCard label="🔧 Furo" value={stats.puncture} color="text-red-600" />
        <StatCard label="⛽ AdBlue" value={stats.adblue} color="text-blue-600" />
        <StatCard label="📝 Outro" value={stats.other} color="text-purple-600" />
      </div>

      {/* Pendentes por tratar (Novos por ler) */}
      {pendingUnseen.length > 0 && (
        <Card className="border-red-200 bg-red-50/40" data-testid="pending-unseen-section">
          <CardHeader className="border-b border-red-100">
            <CardTitle className="text-base flex items-center gap-2 text-red-700">
              <BellRing className="h-4 w-4 animate-pulse" /> Pendentes por tratar
              <Badge variant="secondary" className="bg-red-600 text-white">{pendingUnseen.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4 space-y-2">
            {pendingUnseen.map((r) => (
              <div
                key={r.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white border border-red-100 rounded-lg px-4 py-3"
                data-testid={`pending-unseen-card-${r.id}`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="font-bold text-sm">{r.license_plate || '—'}</span>
                    {SUBTYPE_BADGE(r.subtype)}
                    <Badge variant="secondary" className="bg-blue-100 text-blue-700">Em tratamento</Badge>
                    <Badge variant="secondary" className="bg-red-100 text-red-700">Novo</Badge>
                  </div>
                  <div className="text-xs text-zinc-600 truncate">
                    {r.renting_company || '—'} • {r.driver_name || '—'} • {r.driver_phone || '—'}
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5">Criado: {formatDateTime(r.created_at)}</div>
                </div>
                <Button
                  size="sm"
                  onClick={() => navigate(`/renting/${r.id}`)}
                  data-testid={`pending-open-${r.id}`}
                  className="bg-red-600 hover:bg-red-700 text-white"
                >
                  Abrir
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6 flex flex-col sm:flex-row gap-3">
          <div className="flex-1 relative">
            <Search className="h-4 w-4 absolute left-3 top-3 text-zinc-400" />
            <Input
              placeholder="Pesquisar por matrícula, condutor, telefone ou empresa..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
              data-testid="renting-search-input"
            />
          </div>
          <Select value={subtypeFilter} onValueChange={setSubtypeFilter}>
            <SelectTrigger className="sm:w-48" data-testid="renting-subtype-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os tipos</SelectItem>
              <SelectItem value="tires">🛞 Pneus Novos</SelectItem>
              <SelectItem value="puncture">🔧 Furo</SelectItem>
              <SelectItem value="adblue">⛽ AdBlue</SelectItem>
              <SelectItem value="other">📝 Outro</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="sm:w-48" data-testid="renting-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os estados</SelectItem>
              <SelectItem value="unseen">Por ler</SelectItem>
              <SelectItem value="in_progress">Em tratamento</SelectItem>
              <SelectItem value="completed">Concluídos</SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {/* List */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="text-base">Registos ({records.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center"><Loader2 className="h-6 w-6 animate-spin mx-auto text-zinc-400" /></div>
          ) : records.length === 0 ? (
            <div className="p-8 text-center text-sm text-zinc-500">
              Sem registos. Use o bot Telegram <code>/novo_renting</code> para criar um.
            </div>
          ) : (
            <div className="divide-y">
              {records.map((r) => {
                const isUnseen = r.status === 'in_progress' && !r.seen_by_reception;
                return (
                  <button
                    key={r.id}
                    onClick={() => navigate(`/renting/${r.id}`)}
                    data-testid={`renting-row-${r.id}`}
                    className={`w-full flex items-center justify-between px-5 py-3 hover:bg-zinc-50 text-left ${isUnseen ? 'bg-red-50/40' : ''}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className={`text-sm ${isUnseen ? 'font-bold' : 'font-semibold'}`}>{r.license_plate || '—'}</span>
                        <Badge className={STATUS_LABELS[r.status]?.color || 'bg-zinc-100'} variant="secondary">
                          {STATUS_LABELS[r.status]?.label || r.status}
                        </Badge>
                        {SUBTYPE_BADGE(r.subtype)}
                        {isUnseen && (
                          <Badge variant="secondary" className="bg-red-100 text-red-700" data-testid={`badge-unseen-${r.id}`}>Novo</Badge>
                        )}
                      </div>
                      <div className="text-xs text-zinc-500 truncate">
                        {r.driver_name || '—'} • {r.renting_company || '—'} • {r.driver_phone || '—'}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-zinc-400">{new Date(r.created_at).toLocaleDateString('pt-PT')}</div>
                      {r.subtype === 'adblue' && r.adblue_liters != null && (
                        <div className="text-xs text-blue-600 font-medium">{r.adblue_liters} L</div>
                      )}
                      {r.subtype === 'tires' && r.service_type_label && (
                        <div className="text-xs text-zinc-600">{r.service_type_label}</div>
                      )}
                    </div>
                    <ChevronRight className="h-4 w-4 text-zinc-300 ml-2" />
                  </button>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

const StatCard = ({ label, value, color = 'text-zinc-800', testId }) => (
  <Card data-testid={testId}>
    <CardContent className="pt-6">
      <div className={`text-2xl font-bold ${color}`}>{value || 0}</div>
      <div className="text-xs text-zinc-500 mt-1">{label}</div>
    </CardContent>
  </Card>
);

export default RentingPage;
