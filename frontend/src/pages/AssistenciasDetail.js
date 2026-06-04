import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../components/ui/select';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle
} from '../components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger
} from '../components/ui/alert-dialog';
import {
  ArrowLeft, Loader2, MapPin, FileUp, Send, CheckCircle2, Ban,
  Trash2, ExternalLink, History, FileText, Truck
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STATUS_META = {
  AGUARDA_FATURACAO:    { label: 'Aguarda Faturação',  color: 'bg-amber-100 text-amber-800' },
  DADOS_INCOMPLETOS:    { label: 'Dados Incompletos',  color: 'bg-red-100 text-red-800' },
  FATURA_ANALISADA:     { label: 'Fatura Analisada',   color: 'bg-blue-100 text-blue-800' },
  FATURA_CONFIRMADA:    { label: 'Fatura Confirmada',  color: 'bg-indigo-100 text-indigo-800' },
  ENVIADA_FUNCIONARIO:  { label: 'Enviada ao Func.',   color: 'bg-cyan-100 text-cyan-800' },
  FATURADA_CONCLUIDA:   { label: 'Concluída',          color: 'bg-emerald-100 text-emerald-800' },
  NAO_FATURAVEL:        { label: 'Não Faturável',      color: 'bg-zinc-200 text-zinc-700' },
};

const NON_BILLABLE_REASONS = [
  { value: 'warranty', label: 'Garantia' },
  { value: 'monthly_contract', label: 'Avença / Contrato Mensal' },
  { value: 'internal_service', label: 'Serviço Interno' },
  { value: 'commercial_offer', label: 'Oferta Comercial' },
  { value: 'operational_error', label: 'Erro Operacional' },
  { value: 'other', label: 'Outro' },
];

const formatDateTime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-PT', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
};

const PhotoTile = ({ recordId, kind, index = 0, label, onPreview }) => {
  const { getAuthHeaders } = useAuth();
  const [src, setSrc] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await axios.get(
          `${API_URL}/api/assistencias/records/${recordId}/photo/${kind}?index=${index}`,
          { headers: getAuthHeaders() }
        );
        if (!cancelled && resp.data.base64) {
          setSrc(`data:${resp.data.file_type};base64,${resp.data.base64}`);
        }
      } catch (e) {
        console.error('Failed to load photo:', e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [recordId, kind, index, getAuthHeaders]);

  return (
    <div className="relative rounded-lg border bg-zinc-50 overflow-hidden" style={{ aspectRatio: '4/3' }}>
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-zinc-400" />
        </div>
      )}
      {!loading && src && (
        <button
          type="button"
          onClick={() => onPreview && onPreview(src, label)}
          className="block w-full h-full bg-transparent border-0 p-0 cursor-zoom-in"
          aria-label={`Ampliar ${label}`}
          data-testid={`photo-${kind}-${index}`}
        >
          <img src={src} alt={label} className="w-full h-full object-cover" />
        </button>
      )}
      {!loading && !src && (
        <div className="absolute inset-0 flex items-center justify-center text-zinc-400 text-xs">
          (indisponível)
        </div>
      )}
      <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-xs px-2 py-1 truncate">
        {label}
      </div>
    </div>
  );
};

const AudioPlayer = ({ recordId, transcription }) => {
  const { getAuthHeaders } = useAuth();
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API_URL}/api/assistencias/records/${recordId}/audio`, { headers: getAuthHeaders() });
        if (!cancel && r.data.base64) setSrc(`data:${r.data.file_type};base64,${r.data.base64}`);
      } catch (e) { console.error('Failed to load audio:', e); }
    })();
    return () => { cancel = true; };
  }, [recordId, getAuthHeaders]);
  return (
    <div className="space-y-2">
      {src && <audio controls src={src} className="w-full" data-testid="audio-player" />}
      {transcription && (
        <p className="text-sm text-zinc-700 italic border-l-2 border-orange-200 pl-3">
          🎙️ {transcription}
        </p>
      )}
    </div>
  );
};

const AssistenciasDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, getAuthHeaders } = useAuth();
  const [rec, setRec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showInvoiceModal, setShowInvoiceModal] = useState(false);
  const [invoiceForm, setInvoiceForm] = useState({});
  const [nonBillReason, setNonBillReason] = useState('');
  const [nonBillNote, setNonBillNote] = useState('');
  const [lightbox, setLightbox] = useState(null); // {src, label}
  const fileInputRef = useRef(null);

  const isOffice = user?.role === 'ADMIN' || user?.role === 'SUPERVISOR';
  const isAdmin = user?.role === 'ADMIN';

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API_URL}/api/assistencias/records/${id}`, { headers: getAuthHeaders() });
      setRec(r.data);
    } catch (e) {
      console.error('Failed to load assistencia:', e);
      toast.error('Não foi possível carregar a assistência');
    } finally {
      setLoading(false);
    }
  }, [id, getAuthHeaders]);

  useEffect(() => { load(); }, [load]);

  const onUploadInvoice = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.type !== 'application/pdf') {
      toast.error('Apenas PDF é aceite');
      return;
    }
    setBusy(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await axios.post(
        `${API_URL}/api/assistencias/records/${id}/invoice`,
        fd,
        { headers: { ...getAuthHeaders(), 'Content-Type': 'multipart/form-data' } }
      );
      setRec(r.data);
      const ex = r.data.invoice_extracted || {};
      setInvoiceForm({
        invoice_number: ex.invoice_number || '',
        invoice_date: ex.invoice_date || '',
        invoice_total: ex.invoice_total || '',
        invoice_customer: ex.invoice_customer || '',
        invoice_nif: ex.invoice_nif || '',
      });
      setShowInvoiceModal(true);
      toast.success('Fatura analisada — confirme os dados extraídos');
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Erro ao processar PDF';
      toast.error(detail);
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const onConfirmInvoice = async () => {
    setBusy(true);
    try {
      const body = {
        invoice_number: invoiceForm.invoice_number || null,
        invoice_date: invoiceForm.invoice_date || null,
        invoice_total: invoiceForm.invoice_total ? parseFloat(invoiceForm.invoice_total) : null,
        invoice_customer: invoiceForm.invoice_customer || null,
        invoice_nif: invoiceForm.invoice_nif || null,
      };
      const r = await axios.post(`${API_URL}/api/assistencias/records/${id}/invoice/confirm`, body, { headers: getAuthHeaders() });
      setRec(r.data);
      setShowInvoiceModal(false);
      toast.success('Fatura confirmada. Clique em "Enviar ao Funcionário" para entregar.');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Erro');
    } finally { setBusy(false); }
  };

  const onSendInvoice = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API_URL}/api/assistencias/records/${id}/invoice/send`, {}, { headers: getAuthHeaders() });
      setRec(r.data);
      toast.success('Fatura enviada ao funcionário via Telegram');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Erro a enviar');
    } finally { setBusy(false); }
  };

  const onConfirmDelivery = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API_URL}/api/assistencias/records/${id}/delivery/confirm`, {}, { headers: getAuthHeaders() });
      setRec(r.data);
      toast.success('Entrega confirmada — assistência concluída');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Erro');
    } finally { setBusy(false); }
  };

  const onMarkNonBillable = async () => {
    if (!nonBillReason) {
      toast.error('Selecione um motivo');
      return;
    }
    setBusy(true);
    try {
      const r = await axios.post(`${API_URL}/api/assistencias/records/${id}/non-billable`,
        { reason: nonBillReason, internal_note: nonBillNote }, { headers: getAuthHeaders() });
      setRec(r.data);
      toast.success('Marcada como não faturável');
      setNonBillReason('');
      setNonBillNote('');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Erro');
    } finally { setBusy(false); }
  };

  const onDelete = async () => {
    setBusy(true);
    try {
      await axios.delete(`${API_URL}/api/assistencias/records/${id}`, { headers: getAuthHeaders() });
      toast.success('Assistência eliminada');
      navigate('/assistencias');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Erro');
    } finally { setBusy(false); }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-orange-600" />
      </div>
    );
  }
  if (!rec) return <div className="text-center py-20 text-zinc-500">Não encontrada</div>;

  const m = STATUS_META[rec.status] || { label: rec.status, color: 'bg-zinc-100' };
  const canUploadInvoice = isOffice && ['AGUARDA_FATURACAO', 'DADOS_INCOMPLETOS'].includes(rec.status);
  const canConfirmInvoice = isOffice && rec.status === 'FATURA_ANALISADA';
  const canSendInvoice = isOffice && rec.status === 'FATURA_CONFIRMADA';
  const canConfirmDelivery = isOffice && rec.status === 'ENVIADA_FUNCIONARIO';
  const canMarkNonBillable = isOffice && !['FATURADA_CONCLUIDA', 'NAO_FATURAVEL', 'ENVIADA_FUNCIONARIO'].includes(rec.status);

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Button size="sm" variant="outline" onClick={() => navigate('/assistencias')} data-testid="back-btn">
            <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-zinc-900 flex items-center gap-2">
              <Truck className="h-6 w-6 text-orange-600" />
              <span className="font-mono">{rec.registration_plate || '—'}</span>
            </h1>
            <p className="text-sm text-zinc-500">
              Criada por <strong>{rec.employee_name || '—'}</strong> em {formatDateTime(rec.created_at)}
            </p>
          </div>
        </div>
        <Badge className={`${m.color} text-sm px-3 py-1`} data-testid="status-badge">{m.label}</Badge>
      </div>

      {/* Action bar */}
      <Card className="bg-orange-50/30 border-orange-200">
        <CardContent className="pt-6 flex flex-wrap gap-2">
          {canUploadInvoice && (
            <>
              <input ref={fileInputRef} type="file" accept="application/pdf" hidden onChange={onUploadInvoice} data-testid="invoice-file-input" />
              <Button onClick={() => fileInputRef.current?.click()} disabled={busy} data-testid="upload-invoice-btn">
                <FileUp className="h-4 w-4 mr-2" /> {busy ? 'A analisar...' : 'Upload Fatura'}
              </Button>
            </>
          )}
          {canConfirmInvoice && (
            <Button onClick={() => {
              const ex = rec.invoice_extracted || {};
              setInvoiceForm({
                invoice_number: ex.invoice_number || '',
                invoice_date: ex.invoice_date || '',
                invoice_total: ex.invoice_total || '',
                invoice_customer: ex.invoice_customer || '',
                invoice_nif: ex.invoice_nif || '',
              });
              setShowInvoiceModal(true);
            }} data-testid="review-extraction-btn">
              <FileText className="h-4 w-4 mr-2" /> Rever dados da fatura
            </Button>
          )}
          {canSendInvoice && (
            <Button onClick={onSendInvoice} disabled={busy} className="bg-cyan-600 hover:bg-cyan-700" data-testid="send-invoice-btn">
              <Send className="h-4 w-4 mr-2" /> Enviar ao Funcionário
            </Button>
          )}
          {canConfirmDelivery && (
            <Button onClick={onConfirmDelivery} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700" data-testid="confirm-delivery-btn">
              <CheckCircle2 className="h-4 w-4 mr-2" /> Confirmar Entrega
            </Button>
          )}
          {rec.invoice_pdf && (
            <Button variant="outline" onClick={() => window.open(`${API_URL}/api/assistencias/records/${id}/invoice/pdf`, '_blank')} data-testid="view-pdf-btn">
              <ExternalLink className="h-4 w-4 mr-2" /> Abrir PDF
            </Button>
          )}
          {canMarkNonBillable && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" className="border-zinc-300 text-zinc-700" data-testid="non-billable-btn">
                  <Ban className="h-4 w-4 mr-2" /> Marcar Não Faturável
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Marcar como Não Faturável</AlertDialogTitle>
                  <AlertDialogDescription>
                    Indique o motivo. Esta acção exige aprovação de administrador/supervisor.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <div className="space-y-3">
                  <div>
                    <Label>Motivo *</Label>
                    <Select value={nonBillReason} onValueChange={setNonBillReason}>
                      <SelectTrigger data-testid="non-billable-reason"><SelectValue placeholder="Selecione..." /></SelectTrigger>
                      <SelectContent>
                        {NON_BILLABLE_REASONS.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Nota interna</Label>
                    <Textarea value={nonBillNote} onChange={(e) => setNonBillNote(e.target.value)} rows={3} data-testid="non-billable-note" />
                  </div>
                </div>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                  <AlertDialogAction onClick={onMarkNonBillable} className="bg-zinc-700">Confirmar</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
          {isAdmin && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button size="sm" variant="outline" className="border-red-300 text-red-600 hover:bg-red-50 ml-auto" data-testid="delete-btn">
                  <Trash2 className="h-4 w-4 mr-1" /> Eliminar
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Eliminar assistência?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Esta acção é permanente e remove o registo, fotos, áudio e PDF.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                  <AlertDialogAction onClick={onDelete} className="bg-red-600">Eliminar</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left: details */}
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader><CardTitle className="text-base flex items-center gap-2"><MapPin className="h-4 w-4 text-orange-600" /> Localização</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div>Lat/Lon: <span className="font-mono">{rec.latitude}, {rec.longitude}</span></div>
              {rec.google_maps_url && (
                <a href={rec.google_maps_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-orange-600 hover:underline" data-testid="maps-link">
                  Abrir no Google Maps <ExternalLink className="h-3 w-3" />
                </a>
              )}
              <div className="text-xs text-zinc-500">Registada em {formatDateTime(rec.location_timestamp)}</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Anexos</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {rec.plate_photo && <PhotoTile recordId={id} kind="plate" label="Matrícula" onPreview={(s, l) => setLightbox({ src: s, label: l })} />}
                {rec.worksheet_photo && <PhotoTile recordId={id} kind="worksheet" label="Folha de Obra" onPreview={(s, l) => setLightbox({ src: s, label: l })} />}
                {(rec.additional_photos || []).map((_, i) => (
                  <PhotoTile key={`add-${i}`} recordId={id} kind="additional" index={i} label={`Foto ${i + 1}`} onPreview={(s, l) => setLightbox({ src: s, label: l })} />
                ))}
              </div>
            </CardContent>
          </Card>

          {(rec.text_notes || rec.audio_file) && (
            <Card>
              <CardHeader><CardTitle className="text-base">Observações</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {rec.text_notes && <p className="text-sm whitespace-pre-wrap text-zinc-700">{rec.text_notes}</p>}
                {rec.audio_file && <AudioPlayer recordId={id} transcription={rec.audio_transcription} />}
              </CardContent>
            </Card>
          )}

          {rec.invoice_pdf && (
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><FileText className="h-4 w-4 text-blue-600" /> Fatura</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-zinc-500">Nº:</span> <strong>{rec.invoice_number || '—'}</strong></div>
                <div><span className="text-zinc-500">Data:</span> <strong>{rec.invoice_date || '—'}</strong></div>
                <div><span className="text-zinc-500">Total:</span> <strong>{rec.invoice_total != null ? `${Number(rec.invoice_total).toFixed(2)} €` : '—'}</strong></div>
                <div><span className="text-zinc-500">Cliente:</span> <strong>{rec.invoice_customer || '—'}</strong></div>
                <div><span className="text-zinc-500">NIF:</span> <strong>{rec.invoice_nif || '—'}</strong></div>
                {rec.invoice_extracted?.confidence && (
                  <div><span className="text-zinc-500">Conf. IA:</span> <Badge variant="secondary">{rec.invoice_extracted.confidence}</Badge></div>
                )}
              </CardContent>
            </Card>
          )}

          {rec.non_billable_reason && (
            <Card className="bg-zinc-50">
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><Ban className="h-4 w-4" /> Não Faturável</CardTitle></CardHeader>
              <CardContent className="text-sm space-y-1">
                <div><strong>Motivo:</strong> {NON_BILLABLE_REASONS.find(r => r.value === rec.non_billable_reason)?.label || rec.non_billable_reason}</div>
                {rec.internal_note && <div className="whitespace-pre-wrap text-zinc-700">{rec.internal_note}</div>}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right: audit log */}
        <div>
          <Card>
            <CardHeader><CardTitle className="text-base flex items-center gap-2"><History className="h-4 w-4" /> Timeline</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-3 max-h-[600px] overflow-y-auto">
                {(rec.audit_logs || []).slice().reverse().map(log => (
                  <div key={log.id} className="border-l-2 border-orange-300 pl-3 py-1 text-xs">
                    <div className="font-semibold text-zinc-800">{log.action}</div>
                    <div className="text-zinc-500">{formatDateTime(log.timestamp)} · {log.user_name || '—'}</div>
                    {log.details && Object.keys(log.details).length > 0 && (
                      <pre className="mt-1 text-[10px] text-zinc-600 whitespace-pre-wrap break-all">{JSON.stringify(log.details)}</pre>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Lightbox for full-size photos */}
      <Dialog open={!!lightbox} onOpenChange={(o) => !o && setLightbox(null)}>
        <DialogContent className="max-w-5xl p-2 bg-black/95 border-0">
          <DialogHeader>
            <DialogTitle className="text-white text-sm">{lightbox?.label}</DialogTitle>
          </DialogHeader>
          {lightbox && (
            <div className="flex items-center justify-center" style={{ maxHeight: '85vh' }}>
              <img
                src={lightbox.src}
                alt={lightbox.label}
                className="max-w-full max-h-[85vh] object-contain"
                data-testid="lightbox-image"
              />
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Invoice extraction confirmation modal */}
      <Dialog open={showInvoiceModal} onOpenChange={setShowInvoiceModal}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Dados Extraídos da Fatura</DialogTitle>
            <DialogDescription>
              Revise e corrija se necessário. Toda alteração fica registada no timeline.
              {rec.invoice_extracted?.confidence && (
                <Badge variant="secondary" className="ml-2">Confiança IA: {rec.invoice_extracted.confidence}</Badge>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Nº Fatura</Label>
              <Input value={invoiceForm.invoice_number || ''} onChange={(e) => setInvoiceForm(f => ({ ...f, invoice_number: e.target.value }))} data-testid="inv-number" />
            </div>
            <div>
              <Label>Data (YYYY-MM-DD)</Label>
              <Input value={invoiceForm.invoice_date || ''} onChange={(e) => setInvoiceForm(f => ({ ...f, invoice_date: e.target.value }))} data-testid="inv-date" />
            </div>
            <div>
              <Label>Total €</Label>
              <Input type="number" step="0.01" value={invoiceForm.invoice_total || ''} onChange={(e) => setInvoiceForm(f => ({ ...f, invoice_total: e.target.value }))} data-testid="inv-total" />
            </div>
            <div>
              <Label>NIF</Label>
              <Input value={invoiceForm.invoice_nif || ''} onChange={(e) => setInvoiceForm(f => ({ ...f, invoice_nif: e.target.value }))} data-testid="inv-nif" />
            </div>
            <div className="col-span-2">
              <Label>Cliente</Label>
              <Input value={invoiceForm.invoice_customer || ''} onChange={(e) => setInvoiceForm(f => ({ ...f, invoice_customer: e.target.value }))} data-testid="inv-customer" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowInvoiceModal(false)}>Cancelar</Button>
            <Button onClick={onConfirmInvoice} disabled={busy} data-testid="confirm-invoice-btn">
              {busy ? 'A confirmar...' : 'Confirmar Dados'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AssistenciasDetail;
