/**
 * OverdueEvolutionChart — Mostra a evolução diária do "Vencido Cobrável"
 * cruzada com "Recuperado" e "Faturas que se tornaram vencidas hoje".
 *
 * Intuição: se `Recuperado ≈ Newly Overdue`, a operação está a correr no lugar
 * (o total vencido não desce). Se `Recuperado > Newly Overdue`, o total vencido
 * está a diminuir (efetivamente a recuperar). Este é o KPI que a cobradora
 * precisa para saber se está a "ganhar terreno".
 */
import { useEffect, useState } from 'react';
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

const fmtEUR = (v) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v || 0);

const fmtDate = (iso) => {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('pt-PT', { day: '2-digit', month: 'short' });
};

const OverdueEvolutionChart = ({ days = 30 }) => {
  const { getAuthHeaders } = useAuth();
  const [data, setData] = useState({ series: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const res = await axios.get(
          `${API_URL}/api/finance/overdue-evolution?days=${days}`,
          { headers: getAuthHeaders() }
        );
        setData(res.data);
      } catch (e) {
        setError('Erro ao carregar histórico');
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

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
              Recuperado vs Faturas Novas Vencidas — últimos {days} dias
            </p>
          </div>
          <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium ${trendClasses}`}>
            {trendIcon}
            <span data-testid="overdue-trend-label">{trendLabel}</span>
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
            <div className="grid grid-cols-3 gap-3 mb-4 text-xs">
              <div className="bg-slate-50 rounded p-2">
                <div className="text-slate-500 uppercase tracking-wide">Recuperado ({days}d)</div>
                <div className="text-emerald-700 font-semibold" data-testid="summary-total-recovered">
                  {fmtEUR(summary.total_recovered)}
                </div>
              </div>
              <div className="bg-slate-50 rounded p-2">
                <div className="text-slate-500 uppercase tracking-wide">Novas Vencidas ({days}d)</div>
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

            {/* Chart */}
            <div className="w-full" style={{ height: 300 }}>
              <ResponsiveContainer>
                <ComposedChart data={series} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="date" tickFormatter={fmtDate} stroke="#64748b" fontSize={11} />
                  <YAxis yAxisId="left" stroke="#64748b" fontSize={11}
                         tickFormatter={(v) => (v >= 1000 ? `${(v/1000).toFixed(0)}k` : `${v}`)} />
                  <YAxis yAxisId="right" orientation="right" stroke="#64748b" fontSize={11}
                         tickFormatter={(v) => (v >= 1000 ? `${(v/1000).toFixed(0)}k` : `${v}`)} />
                  <Tooltip
                    formatter={(value, name) => [fmtEUR(value), name]}
                    labelFormatter={(l) => fmtDate(l)}
                    contentStyle={{ fontSize: 12, borderRadius: 6 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <ReferenceLine yAxisId="right" y={0} stroke="#94a3b8" strokeDasharray="2 2" />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="total_overdue_collectable"
                    name="Total Vencido Cobrável"
                    stroke="#dc2626"
                    strokeWidth={2.5}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
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
