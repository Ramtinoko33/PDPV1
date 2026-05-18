import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Label } from '../components/ui/label';
import { ArrowLeft, Save, Loader2, Image as ImageIcon, History, CheckCircle2, ShieldAlert, PlayCircle, FileDown, Copy } from 'lucide-react';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const WHEEL_ORDER = ['FE', 'FD', 'TD', 'TE'];
const WHEEL_LABELS = { FE: 'Frente Esquerda', FD: 'Frente Direita', TD: 'Trás Direita', TE: 'Trás Esquerda' };

const CONF_EMOJI = { high: '🟢', medium: '🟡', low: '🔴' };

const STATUS_META = {
  draft: { label: 'Rascunho', color: 'bg-amber-100 text-amber-700 border-amber-200' },
  in_progress: { label: 'Em tratamento', color: 'bg-blue-100 text-blue-700 border-blue-200' },
  completed: { label: 'Concluído', color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
};

const FIELD_LABELS = {
  driver_name: 'Condutor',
  driver_phone: 'Telefone',
  renting_company: 'Empresa Renting',
  license_plate: 'Matrícula',
  km: 'KM',
  service_type: 'Tipo de serviço',
  service_type_label: 'Serviço',
  subtype: 'Subtipo',
  adblue_liters: 'Litros AdBlue',
  description: 'Descrição',
  puncture_wheel: 'Roda furo',
  puncture_wheel_label: 'Roda furo',
  proposed_tires: 'Pneus propostos',
  authorization_number: 'Nº de autorização',
  status: 'Estado',
};

const formatHistoryValue = (field, value) => {
  if (value === null || value === undefined || value === '') return '—';
  if (field === 'status') return STATUS_META[value]?.label || value;
  if (typeof value === 'string' && value.length > 60) return value.slice(0, 60) + '…';
  return String(value);
};

const SUBTYPE_TITLE = {
  tires: 'Pedido de pneus',
  puncture: 'Reparação de furo',
  adblue: 'Reposição AdBlue',
  other: 'Pedido Renting',
};

const buildSummaryText = (rec) => {
  const subtype = rec.subtype || 'tires';
  const lines = [];
  lines.push(`*${SUBTYPE_TITLE[subtype] || 'Pedido Renting'}*`);
  if (rec.renting_company) lines.push(`Renting: ${rec.renting_company}`);
  if (rec.license_plate) lines.push(`Matrícula: ${rec.license_plate}`);
  if (rec.km != null) lines.push(`KM: ${Number(rec.km).toLocaleString('pt-PT')}`);
  if (rec.driver_name || rec.driver_phone) {
    lines.push(`Condutor: ${rec.driver_name || '—'}${rec.driver_phone ? ` (${rec.driver_phone})` : ''}`);
  }
  if (rec.service_type_label) lines.push(`Serviço: ${rec.service_type_label}`);

  if (subtype === 'tires') {
    const wheelsByPos = {};
    (rec.wheels || []).forEach((w) => { wheelsByPos[w.position] = w; });
    lines.push('');
    lines.push('*Pneus:*');
    WHEEL_ORDER.forEach((pos) => {
      const w = wheelsByPos[pos];
      if (!w) {
        lines.push(`- ${WHEEL_LABELS[pos]}: —`);
        return;
      }
      const d = w.data || {};
      const parts = [];
      if (d.size) parts.push(d.size);
      if (d.load_speed) parts.push(d.load_speed);
      const brandModel = [d.brand, d.model].filter(Boolean).join(' ');
      if (brandModel) parts.push(brandModel);
      const extras = [];
      if (d.dot) extras.push(`DOT ${d.dot}`);
      if (d.tread_mm != null) extras.push(`piso ${d.tread_mm}mm`);
      const main = parts.join(' • ') || '—';
      const ex = extras.length ? ` (${extras.join(', ')})` : '';
      lines.push(`- ${WHEEL_LABELS[pos]}: ${main}${ex}`);
    });
  } else if (subtype === 'puncture') {
    lines.push(`Roda do furo: ${rec.puncture_wheel_label || '—'}`);
  } else if (subtype === 'adblue') {
    lines.push(`Litros AdBlue: ${rec.adblue_liters ?? '—'} L`);
  } else if (subtype === 'other') {
    if (rec.description) {
      lines.push('');
      lines.push(`Descrição: ${rec.description}`);
    }
  }
  return lines.join('\n');
};

const FieldWithConfidence = ({ label, value, confidence, confirmed, onChange, type = 'text', placeholder }) => (
  <div>
    <Label className="text-xs text-zinc-500 flex items-center gap-1.5">
      <span>{label}</span>
      {confidence && <span title={`Confiança IA: ${confidence}`}>{CONF_EMOJI[confidence] || '⚪'}</span>}
      {confirmed && <span title="Confirmado pelo mecânico" className="text-emerald-600">✅</span>}
    </Label>
    <Input
      type={type}
      value={value ?? ''}
      placeholder={placeholder}
      onChange={(e) => onChange && onChange(e.target.value)}
      className="mt-1"
    />
  </div>
);

const RentingDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { getAuthHeaders } = useAuth();
  const [rec, setRec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await axios.get(`${API_URL}/api/renting/records/${id}`, { headers: getAuthHeaders() });
      setRec(resp.data);
    } catch {
      toast.error('Registo não encontrado');
      navigate('/renting');
    } finally {
      setLoading(false);
    }
  }, [id, getAuthHeaders, navigate]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (extraUpdates = {}) => {
    if (!rec) return null;
    setSaving(true);
    try {
      const payload = {
        driver_name: rec.driver_name,
        driver_phone: rec.driver_phone,
        renting_company: rec.renting_company,
        license_plate: rec.license_plate,
        km: rec.km ? parseInt(rec.km) : null,
        wheels: rec.wheels,
        adblue_liters: rec.adblue_liters != null ? parseFloat(rec.adblue_liters) : null,
        description: rec.description,
        proposed_tires: rec.proposed_tires ?? '',
        authorization_number: rec.authorization_number ?? '',
        ...extraUpdates,
      };
      const resp = await axios.put(`${API_URL}/api/renting/records/${id}`, payload, { headers: getAuthHeaders() });
      toast.success('Registo guardado');
      setRec(resp.data);
      return resp.data;
    } catch (e) {
      const detail = e?.response?.data?.detail || 'Erro ao guardar';
      toast.error(detail);
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleMarkInProgress = async () => {
    await handleSave({ status: 'in_progress' });
  };

  const handleMarkCompleted = async () => {
    const auth = (rec?.authorization_number || '').trim();
    if (!auth) {
      toast.error('Preencha o nº de autorização antes de concluir.');
      return;
    }
    await handleSave({ status: 'completed' });
  };

  const handleDownloadPdf = async () => {
    if (!rec) return;
    try {
      const resp = await axios.get(`${API_URL}/api/renting/records/${id}/pdf`, {
        headers: getAuthHeaders(),
        responseType: 'blob',
      });
      const blob = new Blob([resp.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      // Best-effort revoke after a delay
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      toast.success('PDF gerado');
    } catch {
      toast.error('Erro ao gerar PDF');
    }
  };

  const handleCopySummary = async () => {
    if (!rec) return;
    const txt = buildSummaryText(rec);
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(txt);
      } else {
        const ta = document.createElement('textarea');
        ta.value = txt;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      toast.success('Resumo copiado para a área de transferência');
    } catch {
      toast.error('Falha ao copiar');
    }
  };

  const updateField = (k, v) => setRec((prev) => ({ ...prev, [k]: v }));
  const updateWheelData = (idx, k, v) => {
    setRec((prev) => {
      const wheels = [...(prev.wheels || [])];
      const data = { ...(wheels[idx].data || {}), [k]: v };
      // Mark this field as confirmed by human and set confidence to high
      const confKey = `${k}_confidence`;
      const confirmKey = `${k}_confirmed_by_human`;
      // Map field name to its confidence key family
      const FAMILY = {
        size: 'size', brand: 'brand', model: 'brand', load_speed: 'load_speed',
        dot: 'dot', tread_mm: 'tread'
      };
      const fam = FAMILY[k];
      if (fam) {
        data[`${fam}_confidence`] = 'high';
        data[`${fam}_confirmed_by_human`] = true;
      }
      // Suppress unused warning
      void confKey; void confirmKey;
      wheels[idx] = { ...wheels[idx], data };
      return { ...prev, wheels };
    });
  };

  if (loading) {
    return <div className="p-8 text-center"><Loader2 className="h-6 w-6 animate-spin mx-auto text-zinc-400" /></div>;
  }
  if (!rec) return null;

  const status = rec.status || 'draft';
  const statusMeta = STATUS_META[status] || STATUS_META.draft;
  const authMissing = !((rec.authorization_number || '').trim());
  const canMarkInProgress = status === 'draft';
  const canMarkCompleted = status === 'in_progress';
  const canReopen = status === 'completed';

  return (
    <div className="space-y-6 max-w-5xl mx-auto" data-testid="renting-detail">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/renting')} data-testid="back-btn">
          <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
        </Button>
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={`${statusMeta.color} border`} variant="secondary" data-testid="status-badge">
            {statusMeta.label}
          </Badge>
          {canMarkInProgress && (
            <Button onClick={handleMarkInProgress} disabled={saving} size="sm" variant="outline" data-testid="mark-in-progress-btn">
              <PlayCircle className="h-4 w-4 mr-1" /> Marcar Em tratamento
            </Button>
          )}
          {canMarkCompleted && (
            <Button
              onClick={handleMarkCompleted}
              disabled={saving || authMissing}
              size="sm"
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
              data-testid="mark-completed-btn"
              title={authMissing ? 'Preencha o nº de autorização para concluir' : 'Marcar como concluído'}
            >
              <CheckCircle2 className="h-4 w-4 mr-1" /> Concluir
            </Button>
          )}
          {canReopen && (
            <Button onClick={handleMarkInProgress} disabled={saving} size="sm" variant="outline" data-testid="reopen-btn">
              Reabrir
            </Button>
          )}
          <Button onClick={handleCopySummary} size="sm" variant="outline" data-testid="copy-summary-btn">
            <Copy className="h-4 w-4 mr-1" /> Copiar resumo
          </Button>
          <Button onClick={handleDownloadPdf} size="sm" variant="outline" data-testid="download-pdf-btn">
            <FileDown className="h-4 w-4 mr-1" /> PDF
          </Button>
          <Button onClick={() => handleSave()} disabled={saving} size="sm" data-testid="save-btn">
            <Save className="h-4 w-4 mr-1" />{saving ? 'A guardar...' : 'Guardar'}
          </Button>
        </div>
      </div>

      {/* Reception desk panel */}
      <Card data-testid="reception-card" className="border-blue-200">
        <CardHeader className="border-b bg-blue-50/40">
          <CardTitle className="text-base flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-blue-600" /> Painel da Rececionista
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 space-y-4">
          <div>
            <Label className="text-xs text-zinc-500">Pneus disponíveis / propostos</Label>
            <Textarea
              data-testid="proposed-tires-input"
              value={rec.proposed_tires || ''}
              onChange={(e) => updateField('proposed_tires', e.target.value)}
              placeholder="Liste os pneus disponíveis ou os que foram propostos à locadora (medida, marca, modelo, preço)..."
              rows={3}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-zinc-500">
              Nº de autorização <span className="text-red-500">*</span> <span className="text-zinc-400 font-normal">(obrigatório para concluir)</span>
            </Label>
            <Input
              data-testid="authorization-number-input"
              value={rec.authorization_number || ''}
              onChange={(e) => updateField('authorization_number', e.target.value)}
              placeholder="Ex: AUTH-2026-00123"
              className="mt-1"
            />
          </div>
          {status === 'in_progress' && authMissing && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2" data-testid="auth-missing-warning">
              ⚠️ Preencha o nº de autorização da locadora para poder marcar como concluído.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Cliente */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            Cliente
            {rec.subtype === 'adblue' && <Badge variant="secondary" className="bg-blue-100 text-blue-700">⛽ AdBlue</Badge>}
            {rec.subtype === 'tires' && <Badge variant="secondary" className="bg-orange-100 text-orange-700">🛞 Pneus Novos</Badge>}
            {rec.subtype === 'puncture' && <Badge variant="secondary" className="bg-red-100 text-red-700">🔧 Furo</Badge>}
            {rec.subtype === 'other' && <Badge variant="secondary" className="bg-purple-100 text-purple-700">📝 Outro</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Condutor" value={rec.driver_name || ''} onChange={(v) => updateField('driver_name', v)} />
          <Field label="Telefone" value={rec.driver_phone || ''} onChange={(v) => updateField('driver_phone', v)} />
          <Field label="Empresa Renting" value={rec.renting_company || ''} onChange={(v) => updateField('renting_company', v)} />
          <Field label="Matrícula" value={rec.license_plate || ''} onChange={(v) => updateField('license_plate', v?.toUpperCase())} />
          <Field label="KM" value={rec.km || ''} onChange={(v) => updateField('km', v)} type="number" />
          {rec.subtype === 'adblue' ? (
            <Field label="Litros AdBlue" value={rec.adblue_liters ?? ''} onChange={(v) => updateField('adblue_liters', v ? parseFloat(v) : null)} type="number" />
          ) : rec.subtype === 'puncture' ? (
            <Field label="Roda do furo" value={rec.puncture_wheel_label || '—'} disabled />
          ) : (
            <Field label="Serviço" value={rec.service_type_label || '—'} disabled />
          )}
          {rec.subtype === 'other' && (
            <div className="md:col-span-2">
              <Field label="Descrição" value={rec.description || ''} onChange={(v) => updateField('description', v)} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Plate & KM photos */}
      <Card>
        <CardHeader><CardTitle className="text-base">Fotos da matrícula e KM</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <PhotoBox recordId={id} kind="plate" label="Matrícula" />
          <PhotoBox recordId={id} kind="km" label="Quilómetros" />
        </CardContent>
      </Card>

      {/* Wheels — only for full tires subtype */}
      {rec.subtype === 'tires' && (
        <Card>
        <CardHeader className="border-b">
          <CardTitle className="text-base flex items-center justify-between">
            <span>Pneus</span>
            <span className="text-[10px] font-normal text-zinc-500">
              🟢 alta confiança · 🟡 média · 🔴 baixa · ✅ confirmado pelo mecânico
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {WHEEL_ORDER.map((pos, idx) => {
            const w = (rec.wheels || []).find((x) => x.position === pos);
            const wheelIdx = (rec.wheels || []).findIndex((x) => x.position === pos);
            return (
              <div key={pos} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-semibold text-sm">{WHEEL_LABELS[pos]} <span className="text-xs text-zinc-400 ml-1">({pos})</span></h4>
                  {!w && <Badge variant="secondary" className="bg-zinc-100">Pendente</Badge>}
                </div>
                {w ? (
                  <>
                    <div className="grid grid-cols-3 gap-2 mb-3">
                      <PhotoBox recordId={id} kind="wheel" wheelIndex={wheelIdx} sub="full" label="Pneu" />
                      <PhotoBox recordId={id} kind="wheel" wheelIndex={wheelIdx} sub="dot" label="DOT" />
                      <PhotoBox recordId={id} kind="wheel" wheelIndex={wheelIdx} sub="tread" label="Piso" />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <FieldWithConfidence
                        label="Medida" value={w.data?.size || ''}
                        confidence={w.data?.size_confidence}
                        confirmed={w.data?.size_confirmed_by_human}
                        placeholder="205/55 R16"
                        onChange={(v) => updateWheelData(wheelIdx, 'size', v)}
                      />
                      <FieldWithConfidence
                        label="Marca" value={w.data?.brand || ''}
                        confidence={w.data?.brand_confidence}
                        confirmed={w.data?.brand_confirmed_by_human}
                        placeholder="Yokohama"
                        onChange={(v) => updateWheelData(wheelIdx, 'brand', v)}
                      />
                      <FieldWithConfidence
                        label="Modelo" value={w.data?.model || ''}
                        confidence={w.data?.brand_confidence}
                        confirmed={w.data?.brand_confirmed_by_human}
                        placeholder="BluEarth"
                        onChange={(v) => updateWheelData(wheelIdx, 'model', v)}
                      />
                      <FieldWithConfidence
                        label="Índice C/V" value={w.data?.load_speed || ''}
                        confidence={w.data?.load_speed_confidence}
                        confirmed={w.data?.load_speed_confirmed_by_human}
                        placeholder="91V"
                        onChange={(v) => updateWheelData(wheelIdx, 'load_speed', v)}
                      />
                      <FieldWithConfidence
                        label="DOT" value={w.data?.dot || ''}
                        confidence={w.data?.dot_confidence}
                        confirmed={w.data?.dot_confirmed_by_human}
                        placeholder="3620"
                        onChange={(v) => updateWheelData(wheelIdx, 'dot', v)}
                      />
                      <FieldWithConfidence
                        label="Piso (mm)" type="number"
                        value={w.data?.tread_mm ?? ''}
                        confidence={w.data?.tread_confidence}
                        confirmed={w.data?.tread_confirmed_by_human}
                        placeholder="5.5"
                        onChange={(v) => updateWheelData(wheelIdx, 'tread_mm', v ? parseFloat(v) : null)}
                      />
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-zinc-500">Sem fotos registadas para esta roda.</p>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
      )}

      {/* Observations */}
      {rec.observations && (
        <Card data-testid="observations-section">
          <CardHeader><CardTitle className="text-base">Observações <span className="text-xs font-normal text-zinc-500">(interno)</span></CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {rec.observations.type === 'text' && (
              <p className="text-sm whitespace-pre-wrap">{rec.observations.text}</p>
            )}
            {rec.observations.type === 'audio' && (
              <ObservationsAudio recordId={id} transcription={rec.observations.text} status={rec.observations.transcription_status} />
            )}
            {rec.observations.type === 'none' && <p className="text-xs text-zinc-500 italic">Sem observações</p>}
          </CardContent>
        </Card>
      )}

      {/* Audit history */}
      <Card data-testid="history-card">
        <CardHeader className="border-b">
          <CardTitle className="text-base flex items-center gap-2">
            <History className="h-4 w-4 text-zinc-500" /> Histórico de alterações
            <span className="text-xs font-normal text-zinc-400 ml-1">({(rec.history || []).length})</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {(!rec.history || rec.history.length === 0) ? (
            <p className="text-xs text-zinc-500 italic" data-testid="history-empty">Sem alterações registadas.</p>
          ) : (
            <ol className="space-y-3" data-testid="history-list">
              {[...rec.history].reverse().map((h, i) => (
                <li key={i} className="border-l-2 border-zinc-200 pl-3 py-1">
                  <div className="text-xs text-zinc-500">
                    {new Date(h.changed_at).toLocaleString('pt-PT')} • <span className="font-medium text-zinc-700">{h.changed_by_name || h.changed_by || '—'}</span>
                  </div>
                  <div className="text-sm mt-0.5">
                    <span className="font-semibold">{FIELD_LABELS[h.field] || h.field}</span>:{' '}
                    <span className="text-zinc-500 line-through">{formatHistoryValue(h.field, h.old_value)}</span>
                    {' → '}
                    <span className="text-zinc-900 font-medium">{formatHistoryValue(h.field, h.new_value)}</span>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

const Field = ({ label, value, onChange, type = 'text', disabled = false }) => (
  <div>
    <Label className="text-xs text-zinc-500">{label}</Label>
    <Input
      type={type}
      value={value ?? ''}
      onChange={(e) => onChange && onChange(e.target.value)}
      disabled={disabled}
      className="mt-1"
    />
  </div>
);

const PhotoBox = ({ recordId, kind, wheelIndex, sub, label }) => {
  const { getAuthHeaders } = useAuth();
  const [src, setSrc] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    if (src) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (wheelIndex !== undefined) params.set('wheel_index', String(wheelIndex));
      if (sub) params.set('sub', sub);
      const resp = await axios.get(
        `${API_URL}/api/renting/records/${recordId}/photo/${kind}?${params}`,
        { headers: getAuthHeaders() }
      );
      setSrc(`data:${resp.data.file_type};base64,${resp.data.base64}`);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  return (
    <>
      <div className="border rounded-lg overflow-hidden bg-zinc-50 aspect-square flex items-center justify-center cursor-pointer" onClick={() => src && setOpen(true)}>
        {loading ? (
          <Loader2 className="h-5 w-5 animate-spin text-zinc-400" />
        ) : src ? (
          <img src={src} alt={label} className="w-full h-full object-cover" />
        ) : (
          <div className="text-center text-zinc-300"><ImageIcon className="h-6 w-6 mx-auto mb-1" /><span className="text-[10px]">{label}</span></div>
        )}
      </div>
      {open && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4" onClick={() => setOpen(false)}>
          <img src={src} alt={label} className="max-w-full max-h-full" />
        </div>
      )}
    </>
  );
};

const ObservationsAudio = ({ recordId, transcription, status }) => {
  const { getAuthHeaders } = useAuth();
  const [audioSrc, setAudioSrc] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API_URL}/api/renting/records/${recordId}/observations-audio`, { headers: getAuthHeaders() });
        if (!cancel && r.data.base64) setAudioSrc(`data:${r.data.file_type || 'audio/ogg'};base64,${r.data.base64}`);
      } catch { /* */ }
      finally { if (!cancel) setLoading(false); }
    })();
    return () => { cancel = true; };
  }, [recordId, getAuthHeaders]);

  return (
    <>
      {loading ? <p className="text-xs text-zinc-500">A carregar áudio...</p> : audioSrc ? (
        <audio controls src={audioSrc} className="w-full" data-testid="observations-audio" />
      ) : <p className="text-xs text-zinc-500">Áudio indisponível</p>}
      {status === 'success' && transcription && (
        <div className="border-t pt-2">
          <p className="text-[10px] uppercase text-zinc-400 mb-1">Transcrição</p>
          <p className="text-sm whitespace-pre-wrap">{transcription}</p>
        </div>
      )}
      {status === 'failed' && <p className="text-xs text-amber-600">Transcrição falhou.</p>}
    </>
  );
};

export default RentingDetail;
