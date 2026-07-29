import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../../components/ui/dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../../components/ui/table';
import { Alert, AlertTitle, AlertDescription } from '../../components/ui/alert';
import { ScrollArea } from '../../components/ui/scroll-area';
import axios from 'axios';
import { toast } from 'sonner';
import {
  GitMerge, ShieldAlert, PlayCircle, CheckCircle2, XCircle, Clock,
  Search, RefreshCw, FileWarning, ChevronRight,
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const StatusBadge = ({ status }) => {
  const map = {
    pending: { cls: 'bg-amber-100 text-amber-800 border-amber-300', label: 'Pendente' },
    applied: { cls: 'bg-emerald-100 text-emerald-800 border-emerald-300', label: 'Aplicado' },
    expired: { cls: 'bg-slate-200 text-slate-700 border-slate-300', label: 'Expirado' },
  };
  const cfg = map[status] || map.expired;
  return (
    <Badge variant="outline" className={cfg.cls} data-testid={`merge-status-${status}`}>
      {cfg.label}
    </Badge>
  );
};

const formatDT = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('pt-PT'); } catch { return iso; }
};

const TTLCountdown = ({ expiresAt }) => {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!expiresAt) return null;
  const remainingMs = new Date(expiresAt).getTime() - now;
  if (remainingMs <= 0) {
    return <span className="text-red-600 font-medium">Expirado</span>;
  }
  const mins = Math.floor(remainingMs / 60000);
  const secs = Math.floor((remainingMs % 60000) / 1000);
  return (
    <span className="text-slate-700 font-medium tabular-nums" data-testid="merge-ttl">
      {mins}m {String(secs).padStart(2, '0')}s
    </span>
  );
};

const MergeDuplicates = () => {
  const { user, getAuthHeaders } = useAuth();

  const isOwner = user?.finance_role === 'OWNER' || user?.role === 'ADMIN';
  const canView = isOwner || user?.finance_role === 'FINANCE_REVIEWER';

  const [reports, setReports] = useState([]);
  const [activeReport, setActiveReport] = useState(null); // full detail with .plan
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [applying, setApplying] = useState(false);
  const [search, setSearch] = useState('');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');

  const loadReports = useCallback(async () => {
    if (!canView) return;
    setLoading(true);
    try {
      const res = await axios.get(
        `${API_URL}/api/finance/merge-duplicates/reports?limit=20`,
        { headers: getAuthHeaders() },
      );
      setReports(res.data.items || []);
    } catch (err) {
      console.error('Erro ao carregar relatórios:', err);
      if (err.response?.status !== 403) {
        toast.error(err.response?.data?.detail || 'Erro ao carregar relatórios');
      }
    } finally {
      setLoading(false);
    }
  }, [canView, getAuthHeaders]);

  useEffect(() => { loadReports(); }, [loadReports]);

  const openReport = async (reportId) => {
    setLoading(true);
    try {
      const res = await axios.get(
        `${API_URL}/api/finance/merge-duplicates/reports/${reportId}`,
        { headers: getAuthHeaders() },
      );
      setActiveReport(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao carregar relatório');
    } finally {
      setLoading(false);
    }
  };

  const generateDryRun = async () => {
    if (!isOwner) return;
    setGenerating(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/finance/merge-duplicates/dry-run`,
        {},
        { headers: getAuthHeaders() },
      );
      toast.success(
        `Dry-run gerado — ${res.data.summary.duplicates} duplicado(s), ` +
        `${res.data.summary.conflicts_preserved} conflito(s) preservado(s).`,
      );
      // Refresh list e abrir o novo report
      await loadReports();
      await openReport(res.data.report_id);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao gerar dry-run');
    } finally {
      setGenerating(false);
    }
  };

  const applyMerge = async () => {
    if (!activeReport || !isOwner) return;
    if (confirmText !== 'APROVAR') return;
    setApplying(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/finance/merge-duplicates/confirm`,
        { report_id: activeReport.id, confirmation: 'APROVAR' },
        { headers: getAuthHeaders() },
      );
      toast.success(
        `Merge aplicado: ${res.data.apply_stats.merged_count} duplicado(s) consolidado(s).`,
      );
      setConfirmOpen(false);
      setConfirmText('');
      await loadReports();
      await openReport(activeReport.id);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao aplicar merge');
    } finally {
      setApplying(false);
    }
  };

  // ---------- Derivadas do report activo ----------
  const plan = activeReport?.plan;
  const summary = plan?.summary;
  const groups = plan?.groups || [];
  const conflicts = plan?.conflicts || [];

  const filteredGroups = useMemo(() => {
    const q = (search || '').trim().toLowerCase();
    if (!q) return groups;
    return groups.filter((g) => {
      const master = g.master || {};
      if (
        (master.name || '').toLowerCase().includes(q) ||
        String(master.genes_code || '').toLowerCase().includes(q) ||
        String(master.id || '').toLowerCase().includes(q)
      ) return true;
      return (g.duplicates || []).some((d) =>
        (d.name || '').toLowerCase().includes(q) ||
        String(d.genes_code || '').toLowerCase().includes(q) ||
        String(d.id || '').toLowerCase().includes(q),
      );
    });
  }, [groups, search]);

  const filteredConflicts = useMemo(() => {
    const q = (search || '').trim().toLowerCase();
    if (!q) return conflicts;
    return conflicts.filter((c) =>
      String(c.master_genes_code || '').toLowerCase().includes(q) ||
      String(c.duplicate_genes_code || '').toLowerCase().includes(q) ||
      String(c.master_id || '').toLowerCase().includes(q) ||
      String(c.duplicate_id || '').toLowerCase().includes(q) ||
      String(c.field || '').toLowerCase().includes(q),
    );
  }, [conflicts, search]);

  const expiresAt = activeReport?.expires_at;
  const isExpired = expiresAt && new Date(expiresAt).getTime() < Date.now();
  const status = activeReport?.status;
  const canConfirm = isOwner && status === 'pending' && !isExpired && (summary?.duplicates || 0) > 0;

  // ---------- Renders ----------

  if (!canView) {
    return (
      <div className="p-8" data-testid="merge-forbidden">
        <Alert variant="destructive">
          <ShieldAlert className="h-4 w-4" />
          <AlertTitle>Acesso negado</AlertTitle>
          <AlertDescription>Esta página requer role FINANCE OWNER ou FINANCE REVIEWER.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="merge-duplicates-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <GitMerge className="h-6 w-6 text-slate-700" />
            <h1 className="text-2xl font-bold text-slate-900">Merge de Duplicados</h1>
          </div>
          <p className="text-slate-500 text-sm mt-1">
            Consolidação segura de clientes financeiros duplicados (bug PROEF / CodPersona / Conta).
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={loadReports}
            disabled={loading}
            data-testid="merge-refresh-btn"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          {isOwner && (
            <Button
              onClick={generateDryRun}
              disabled={generating}
              data-testid="merge-generate-dryrun-btn"
            >
              <PlayCircle className="h-4 w-4 mr-2" />
              {generating ? 'A gerar...' : 'Gerar dry-run'}
            </Button>
          )}
        </div>
      </div>

      {/* Aviso obrigatório */}
      <Alert className="border-amber-300 bg-amber-50" data-testid="merge-warning">
        <FileWarning className="h-4 w-4 text-amber-700" />
        <AlertTitle className="text-amber-900">Antes de aprovar</AlertTitle>
        <AlertDescription className="text-amber-800 text-sm">
          Esta ação altera referências financeiras (finance_open_documents, finance_credit_evolution,
          finance_documents, etc.) do duplicado para o master. Reveja o relatório inteiro, em especial
          os <b>conflitos preservados</b>, antes de escrever <code className="mx-1 px-1 rounded bg-amber-100">APROVAR</code>.
          O dry-run é sempre seguro e não escreve em `finance_clients`.
        </AlertDescription>
      </Alert>

      {/* Histórico de relatórios */}
      <Card data-testid="merge-reports-list">
        <CardHeader>
          <CardTitle className="text-lg">Últimos relatórios</CardTitle>
        </CardHeader>
        <CardContent>
          {reports.length === 0 ? (
            <p className="text-sm text-slate-500 py-6 text-center">
              Ainda não existem relatórios. Gere o primeiro dry-run acima.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead className="text-right">Masters</TableHead>
                    <TableHead className="text-right">Duplicados</TableHead>
                    <TableHead className="text-right">Conflitos</TableHead>
                    <TableHead>Criado por</TableHead>
                    <TableHead>Aplicado por</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reports.map((r) => {
                    const s = r.plan_summary || {};
                    return (
                      <TableRow
                        key={r.id}
                        data-testid={`merge-report-row-${r.id}`}
                        className={activeReport?.id === r.id ? 'bg-slate-50' : ''}
                      >
                        <TableCell className="text-sm">{formatDT(r.created_at)}</TableCell>
                        <TableCell><StatusBadge status={r.status} /></TableCell>
                        <TableCell className="text-right tabular-nums">
                          {s.masters ?? '—'}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {s.duplicates ?? '—'}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {s.conflicts_preserved ?? '—'}
                        </TableCell>
                        <TableCell className="text-sm">{r.created_by_name || '—'}</TableCell>
                        <TableCell className="text-sm">{r.applied_by_name || '—'}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => openReport(r.id)}
                            data-testid={`merge-report-open-${r.id}`}
                          >
                            Abrir <ChevronRight className="h-3 w-3 ml-1" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Detalhe do relatório activo */}
      {activeReport && (
        <Card data-testid="merge-report-detail">
          <CardHeader>
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  Relatório {activeReport.id.slice(0, 8)}…
                  <StatusBadge status={status} />
                </CardTitle>
                <p className="text-xs text-slate-500 mt-1">
                  Gerado em {formatDT(activeReport.created_at)} por {activeReport.created_by_name}
                </p>
              </div>
              <div className="text-right text-sm">
                <div className="flex items-center gap-1 text-slate-600">
                  <Clock className="h-3.5 w-3.5" /> TTL restante:{' '}
                  {status === 'pending' ? <TTLCountdown expiresAt={expiresAt} /> : '—'}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  expira: {formatDT(expiresAt)}
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Summary tiles */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <SummaryTile label="Masters" value={summary?.masters ?? 0} />
              <SummaryTile label="Duplicados" value={summary?.duplicates ?? 0} />
              <SummaryTile
                label="Conflitos preservados"
                value={summary?.conflicts_preserved ?? 0}
                accent={summary?.conflicts_preserved > 0}
              />
              <SummaryTile
                label="Grupos com merge"
                value={groups.length}
              />
            </div>

            {status === 'applied' && (
              <Alert className="border-emerald-300 bg-emerald-50" data-testid="merge-applied-summary">
                <CheckCircle2 className="h-4 w-4 text-emerald-700" />
                <AlertTitle className="text-emerald-900">Merge aplicado</AlertTitle>
                <AlertDescription className="text-emerald-800 text-sm">
                  Aplicado em {formatDT(activeReport.applied_at)} por{' '}
                  {activeReport.applied_by_name}.{' '}
                  {activeReport.apply_stats?.merged_count} duplicado(s) consolidado(s) em{' '}
                  {activeReport.apply_stats?.masters_touched} master(s).
                  {activeReport.apply_stats?.remap_stats && (
                    <div className="mt-2 text-xs font-mono">
                      {Object.entries(activeReport.apply_stats.remap_stats).map(([k, v]) => (
                        <div key={k}>• {k}: {v} doc(s)</div>
                      ))}
                    </div>
                  )}
                </AlertDescription>
              </Alert>
            )}

            {status === 'expired' && (
              <Alert variant="destructive" data-testid="merge-expired-alert">
                <XCircle className="h-4 w-4" />
                <AlertTitle>Relatório expirado</AlertTitle>
                <AlertDescription className="text-sm">
                  Gere um novo dry-run para poder aplicar o merge.
                </AlertDescription>
              </Alert>
            )}

            {/* Pesquisa */}
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 text-slate-400" />
              <Input
                placeholder="Pesquisar por nome, genes_code, master_id, duplicate_id..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                data-testid="merge-search-input"
              />
            </div>

            {/* Tabela de conflitos */}
            {conflicts.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-slate-900 mb-2 flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-amber-600" />
                  Conflitos preservados ({filteredConflicts.length}/{conflicts.length})
                </h3>
                <ScrollArea className="max-h-64 border rounded-md">
                  <Table>
                    <TableHeader className="sticky top-0 bg-white z-10">
                      <TableRow>
                        <TableHead>Master</TableHead>
                        <TableHead>Duplicado</TableHead>
                        <TableHead>Campo</TableHead>
                        <TableHead>Valor Master (preservado)</TableHead>
                        <TableHead>Valor Duplicado (ignorado)</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredConflicts.map((c, i) => (
                        <TableRow key={`${c.duplicate_id}-${c.field}-${i}`}
                                  data-testid="merge-conflict-row">
                          <TableCell className="font-mono text-xs">
                            {c.master_genes_code}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {c.duplicate_genes_code}
                          </TableCell>
                          <TableCell className="text-sm">{c.field}</TableCell>
                          <TableCell className="text-sm text-emerald-700">
                            {String(c.master_value)}
                          </TableCell>
                          <TableCell className="text-sm text-slate-500 line-through">
                            {String(c.duplicate_value)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </div>
            )}

            {/* Grupos */}
            <div>
              <h3 className="text-sm font-semibold text-slate-900 mb-2">
                Grupos master ↔ duplicado ({filteredGroups.length}/{groups.length})
              </h3>
              {filteredGroups.length === 0 ? (
                <p className="text-sm text-slate-500 py-6 text-center border rounded-md">
                  {search ? 'Sem resultados para esta pesquisa.' : 'Nenhum grupo detectado.'}
                </p>
              ) : (
                <div className="space-y-3">
                  {filteredGroups.slice(0, 200).map((g) => (
                    <GroupCard key={g.master.id} group={g} />
                  ))}
                  {filteredGroups.length > 200 && (
                    <p className="text-xs text-slate-500 text-center">
                      A mostrar 200 de {filteredGroups.length}. Use pesquisa para filtrar.
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Confirm */}
            {canConfirm && (
              <div className="pt-3 border-t flex items-center justify-end">
                <Button
                  size="lg"
                  variant="destructive"
                  onClick={() => { setConfirmText(''); setConfirmOpen(true); }}
                  data-testid="merge-open-confirm-btn"
                >
                  <GitMerge className="h-4 w-4 mr-2" />
                  Aplicar merge
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Dialogo de confirmação */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent data-testid="merge-confirm-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-red-600" />
              Confirmar aplicação do merge
            </DialogTitle>
            <DialogDescription>
              Vai consolidar {summary?.duplicates} duplicado(s) em {summary?.masters} master(s),
              preservando {summary?.conflicts_preserved} conflito(s). Esta operação é irreversível.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Alert variant="destructive">
              <ShieldAlert className="h-4 w-4" />
              <AlertDescription className="text-sm">
                Escreva exactamente <b>APROVAR</b> (maiúsculas) para habilitar o botão.
              </AlertDescription>
            </Alert>
            <div>
              <Label htmlFor="merge-confirmation-input" className="text-sm">
                Confirmação
              </Label>
              <Input
                id="merge-confirmation-input"
                autoFocus
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="APROVAR"
                data-testid="merge-confirmation-input"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              disabled={applying}
              data-testid="merge-confirm-cancel-btn"
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              disabled={confirmText !== 'APROVAR' || applying}
              onClick={applyMerge}
              data-testid="merge-confirm-apply-btn"
            >
              {applying ? 'A aplicar...' : 'Aplicar merge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const SummaryTile = ({ label, value, accent }) => (
  <div
    className={`rounded-lg border p-3 ${accent ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-white'}`}
    data-testid={`merge-tile-${label.toLowerCase().replace(/\s/g, '-')}`}
  >
    <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
    <div className={`text-2xl font-bold tabular-nums ${accent ? 'text-amber-800' : 'text-slate-900'}`}>
      {value}
    </div>
  </div>
);

const GroupCard = ({ group }) => {
  const m = group.master || {};
  const dups = group.duplicates || [];
  return (
    <div className="border rounded-md p-3 bg-white" data-testid={`merge-group-${m.id}`}>
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-emerald-600">Master</div>
          <div className="font-medium text-slate-900">
            {m.name || '—'}{' '}
            <span className="font-mono text-xs text-slate-500">
              (genes_code={m.genes_code}, id={String(m.id).slice(0, 8)}…)
            </span>
          </div>
        </div>
        <Badge variant="outline" className="border-slate-300">
          {dups.length} duplicado(s)
        </Badge>
      </div>
      <div className="mt-2 pl-4 border-l-2 border-slate-200 space-y-2">
        {dups.map((d) => (
          <DupRow key={d.id} dup={d} />
        ))}
      </div>
    </div>
  );
};

const DupRow = ({ dup }) => {
  const updates = dup._updates_for_master || {};
  const conflicts = dup._conflicts || [];
  return (
    <div className="text-sm" data-testid={`merge-dup-${dup.id}`}>
      <div className="text-slate-700">
        <span className="text-slate-500">DUP</span>{' '}
        <span className="font-medium">{dup.name || '—'}</span>{' '}
        <span className="font-mono text-xs text-slate-500">
          (genes_code={dup.genes_code}, id={String(dup.id).slice(0, 8)}…)
        </span>
      </div>
      {Object.keys(updates).length > 0 && (
        <div className="text-xs text-emerald-700 mt-0.5">
          MIGRAM →{' '}
          {Object.entries(updates).map(([k, v]) => (
            <span key={k} className="inline-block mr-2 font-mono">
              {k}={JSON.stringify(v)}
            </span>
          ))}
        </div>
      )}
      {conflicts.length > 0 && (
        <div className="text-xs text-amber-700 mt-0.5">
          {conflicts.length} conflito(s) preservam master
        </div>
      )}
    </div>
  );
};

export default MergeDuplicates;
