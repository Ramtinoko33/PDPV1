/**
 * OverdueEvolutionChart — Mostra a evolução diária do "Vencido Cobrável"
 * cruzada com "Recuperado" e "Faturas que se tornaram vencidas hoje".
 *
 * Intuição: se `Recuperado ≈ Newly Overdue`, a operação está a correr no lugar
 * (o total vencido não desce). Se `Recuperado > Newly Overdue`, o total vencido
 * está a diminuir (efetivamente a recuperar). Este é o KPI que a cobradora
 * precisa para saber se está a "ganhar terreno".
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '../../context/AuthContext';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// ─── Hoisted constants (avoid creating new objects per render) ──────────
const CHART_MARGIN = { top: 10, right: 20, left: 0, bottom: 0 };
const TOOLTIP_STYLE = { fontSize: 12, borderRadius: 6 };
const LEGEND_STYLE = { fontSize: 11 };
const DOT_STYLE = { r: 3 };
const ACTIVE_DOT_STYLE = { r: 5 };

const fmtEUR = (v) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v || 0);

const fmtDate = (iso) => {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('pt-PT', { day: '2-digit', month: 'short' });
};

const yAxisTick = (v) => (v >= 1000 ? `${(v/1000).toFixed(0)}k` : `${v}`);
const tooltipFormatter = (value, name) => [fmtEUR(value), name];
const tooltipLabelFormatter = (l) => fmtDate(l);

const OverdueEvolutionChart = ({ days: initialDays = 30 }) => {
  const { getAuthHeaders } = useAuth();
  const [days, setDays] = useState(initialDays);
  const [data, setData] = useState({ series: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Period selector options — YTD is computed dynamically from Jan 1 of current year
  const PERIODS = useMemo(() => {
    const now = new Date();
    const jan1 = new Date(now.getFullYear(), 0, 1);
    const ytdDays = Math.max(1, Math.floor((now - jan1) / 86400000) + 1);
    return [
      { key: '7', label: '7d', days: 7 },
      { key: '30', label: '30d', days: 30 },
      { key: '90', label: '90d', days: 90 },
      { key: 'ytd', label: 'YTD', days: ytdDays },
    ];
  }, []);

  const fetchData = useCallback(async (signal) => {
    try {
      setLoading(true);
      setError(null);
      const res = await axios.get(
        `${API_URL}/api/finance/overdue-evolution?days=${days}`,
        { headers: getAuthHeaders(), signal }
      );
      setData(res.data);
    } catch (e) {
      if (!axios.isCancel(e)) {
        setError(e.response?.data?.detail || 'Erro ao carregar histórico');
      }
    } finally {
      setLoading(false);
    }
  }, [days, getAuthHeaders]);

  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
    return () => controller.abort();
  }, [fetchData]);

  const { series, summary } = data;

  // Delta interpretation
  const delta = summary.total_delta ?? 0;
  const trendIcon = delta > 0 ? (
    <TrendingUp className="h-4 w-4 text-red-600" />
  ) : delta < 0 ? (
    <TrendingDown className="h-4 w-4 text-emerald-600" />
  ) : (
    <Minus className="h-4 w-4 text-slate-500" />
  );
  const trendLabel = delta > 0
    ? 'A crescer — falta cobrar mais do que está a vencer'
    : delta < 0
      ? 'A diminuir — cobranças a superar novas vencidas'
      : 'Estagnado — recuperado a compensar novas vencidas';
  const trendClasses = delta > 0
    ? 'bg-red-50 text-red-700 border-red-200'
    : delta < 0
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : 'bg-slate-50 text-slate-700 border-slate-200';

  return (
    <Card data-testid="overdue-evolution-chart" className="border-slate-200">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-lg text-slate-900">Evolução do Vencido Cobrável</CardTitle>
            <p className="text-xs text-slate-500 mt-1">
              Recuperado vs Faturas Novas Vencidas
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Period selector */}
            <div
              className="inline-flex rounded-md border border-slate-200 bg-white overflow-hidden"
              data-testid="period-selector"
              role="group"
              aria-label="Selecionar período"
            >
              {PERIODS.map((p) => {
                const active = days === p.days;
                return (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => setDays(p.days)}
                    data-testid={`period-${p.key}`}
                    className={`px-3 py-1 text-xs font-medium transition-colors ${
                      active
                        ? 'bg-slate-900 text-white'
                        : 'text-slate-600 hover:bg-slate-50'
                    } ${p.key !== '7' ? 'border-l border-slate-200' : ''}`}
                    aria-pressed={active}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium ${trendClasses}`}>
              {trendIcon}
              <span data-testid="overdue-trend-label">{trendLabel}</span>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading && <div className="text-sm text-slate-500 py-8 text-center">A carregar histórico...</div>}
        {error && <div className="text-sm text-red-600 py-8 text-center">{error}</div>}
        {!loading && !error && series.length < 2 && (
          <div className="text-sm text-slate-500 py-8 text-center">
            Ainda não há histórico suficiente para plotar evolução.<br />
            <span className="text-xs">Faz uploads diários para começares a ver a tendência aqui.</span>
          </div>
        )}
        {!loading && !error && series.length >= 2 && (
          <>
            {/* Summary strip */}
            {(() => {
              const activePeriod = PERIODS.find(p => p.days === days);
              const periodLabel = activePeriod?.label || `${days}d`;
              return (
                <div className="grid grid-cols-3 gap-3 mb-4 text-xs">
                  <div className="bg-slate-50 rounded p-2">
                    <div className="text-slate-500 uppercase tracking-wide">Recuperado ({periodLabel})</div>
                    <div className="text-emerald-700 font-semibold" data-testid="summary-total-recovered">
                      {fmtEUR(summary.total_recovered)}
                    </div>
                  </div>
                  <div className="bg-slate-50 rounded p-2">
                    <div className="text-slate-500 uppercase tracking-wide">Novas Vencidas ({periodLabel})</div>
                    <div className="text-red-700 font-semibold" data-testid="summary-newly-overdue">
                      {fmtEUR(summary.total_newly_overdue)}
                    </div>
                  </div>
                  <div className="bg-slate-50 rounded p-2">
                    <div className="text-slate-500 uppercase tracking-wide">Δ Total Vencido</div>
                    <div
                      className={`font-semibold ${delta > 0 ? 'text-red-700' : delta < 0 ? 'text-emerald-700' : 'text-slate-700'}`}
                      data-testid="summary-total-delta"
                    >
                      {delta > 0 ? '+' : ''}{fmtEUR(delta)}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Chart */}
            <div className="w-full" style={{ height: 300 }}>
              <ResponsiveContainer>
                <ComposedChart data={series} margin={CHART_MARGIN}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#64748b" fontSize={11} />
                  <YAxis yAxisId="left" stroke="#64748b" fontSize={11}
                         tickFormatter={yAxisTick} />
                  <YAxis yAxisId="right" orientation="right" stroke="#64748b" fontSize={11}
                         tickFormatter={yAxisTick} />
                  <Tooltip
                    formatter={tooltipFormatter}
                    labelFormatter={tooltipLabelFormatter}
                    contentStyle={TOOLTIP_STYLE}
                  />
                  <Legend wrapperStyle={LEGEND_STYLE} />
                  <ReferenceLine yAxisId="right" y={0} stroke="#94a3b8" strokeDasharray="2 2" />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="total_overdue_collectable"
                    name="Total Vencido Cobrável"
                    stroke="#dc2626"
                    strokeWidth={2.5}
                    dot={DOT_STYLE}
                    activeDot={ACTIVE_DOT_STYLE}
                  />
                  <Bar
                    yAxisId="right"
                    dataKey="recovered_amount"
                    name="Recuperado"
                    fill="#10b981"
                    opacity={0.7}
                    barSize={16}
                  />
                  <Bar
                    yAxisId="right"
                    dataKey="newly_overdue"
                    name="Novas Vencidas"
                    fill="#ef4444"
                    opacity={0.7}
                    barSize={16}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <p className="text-xs text-slate-500 mt-3">
              <b>Linha vermelha</b> = Total Vencido Cobrável (escala esquerda) ·
              <b> Verde</b> = Recuperado no dia ·
              <b> Vermelho</b> = Faturas novas que se tornaram vencidas (escala direita)
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default OverdueEvolutionChart;
