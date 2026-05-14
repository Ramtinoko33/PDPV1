import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Car, Search, Loader2, ChevronRight } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STATUS_LABELS = {
  draft: { label: 'Rascunho', color: 'bg-amber-100 text-amber-700' },
  completed: { label: 'Concluído', color: 'bg-emerald-100 text-emerald-700' },
};

const RentingPage = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState({ draft: 0, completed: 0, total: 0, incomplete: 0, tires: 0, adblue: 0 });
  const [records, setRecords] = useState([]);
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
      const [recRes, statsRes] = await Promise.all([
        axios.get(`${API_URL}/api/renting/records?${params}`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/renting/stats`, { headers: getAuthHeaders() }),
      ]);
      setRecords(recRes.data.items || []);
      setStats(statsRes.data || {});
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
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        <StatCard label="Total" value={stats.total} />
        <StatCard label="Concluídos" value={stats.completed} color="text-emerald-600" />
        <StatCard label="Rascunhos" value={stats.draft} color="text-amber-600" />
        <StatCard label="Incompletos" value={stats.incomplete} color="text-zinc-600" />
        <StatCard label="Pneus" value={stats.tires} color="text-orange-600" />
        <StatCard label="AdBlue" value={stats.adblue} color="text-blue-600" />
      </div>

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
            <SelectTrigger className="sm:w-40" data-testid="renting-subtype-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os tipos</SelectItem>
              <SelectItem value="tires">🛞 Pneus</SelectItem>
              <SelectItem value="adblue">⛽ AdBlue</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="sm:w-48" data-testid="renting-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os estados</SelectItem>
              <SelectItem value="completed">Concluídos</SelectItem>
              <SelectItem value="draft">Rascunhos</SelectItem>
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
              {records.map((r) => (
                <button
                  key={r.id}
                  onClick={() => navigate(`/renting/${r.id}`)}
                  data-testid={`renting-row-${r.id}`}
                  className="w-full flex items-center justify-between px-5 py-3 hover:bg-zinc-50 text-left"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm">{r.license_plate || '—'}</span>
                      <Badge className={STATUS_LABELS[r.status]?.color || 'bg-zinc-100'} variant="secondary">
                        {STATUS_LABELS[r.status]?.label || r.status}
                      </Badge>
                      {r.subtype === 'adblue' && (
                        <Badge variant="secondary" className="bg-blue-100 text-blue-700">⛽ AdBlue</Badge>
                      )}
                      {r.subtype === 'tires' && (
                        <Badge variant="secondary" className="bg-orange-100 text-orange-700">🛞 Pneus</Badge>
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
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

const StatCard = ({ label, value, color = 'text-zinc-800' }) => (
  <Card>
    <CardContent className="pt-6">
      <div className={`text-2xl font-bold ${color}`}>{value || 0}</div>
      <div className="text-xs text-zinc-500 mt-1">{label}</div>
    </CardContent>
  </Card>
);

export default RentingPage;
