/**
 * Painel de comunicação manual rápida na ficha do cliente Finance.
 *
 * Suporta:
 *   - WhatsApp: abre wa.me com número + mensagem pré-preenchida numa nova aba
 *   - Copy: copia texto para clipboard
 *   - Email: prepara mailto: com destinatário/assunto/corpo (ou copia)
 *
 * Cada acção regista automaticamente uma entrada em finance_actions
 * (via POST /clients/{id}/actions) para preservar o histórico operacional.
 *
 * Ainda não envia por API externa — sempre manual/controlado (política do utilizador).
 */
import { useState, useMemo, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../../components/ui/dialog';
import {
  Select, SelectTrigger, SelectContent, SelectItem, SelectValue,
} from '../../components/ui/select';
import { toast } from 'sonner';
import axios from 'axios';
import {
  MessageSquare, Mail, Copy, Send, ExternalLink, Sparkles
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const formatCurrency = (v) =>
  new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(v || 0);

const BUCKET_STYLES = {
  green:  'bg-green-100 text-green-800 border-green-200',
  yellow: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  orange: 'bg-orange-100 text-orange-800 border-orange-200',
  red:    'bg-red-100 text-red-800 border-red-200',
  blue:   'bg-blue-100 text-blue-800 border-blue-200',
  purple: 'bg-purple-100 text-purple-800 border-purple-200',
  black:  'bg-slate-800 text-white border-slate-800',
};

function pickWhatsAppNumber(client) {
  const candidates = [client?.finance_mobile, client?.mobile, client?.phone];
  for (const raw of candidates) {
    if (!raw) continue;
    const digits = String(raw).replace(/[^\d+]/g, '');
    if (digits.length >= 9) return digits.startsWith('+') ? digits.slice(1) : (digits.length === 9 ? `351${digits}` : digits);
  }
  return '';
}

function pickEmail(client) {
  return client?.finance_email || client?.email || '';
}

/**
 * Interpola variáveis simples nos templates {{nome}}, {{vencido}}, {{dias}}.
 */
function interpolate(text, client) {
  if (!text) return '';
  return text
    .replace(/{{\s*nome\s*}}/gi, client?.name || 'Cliente')
    .replace(/{{\s*vencido\s*}}/gi, formatCurrency(client?.overdue_balance_collectable || 0))
    .replace(/{{\s*dias\s*}}/gi, String(client?.oldest_overdue_days || 0));
}

export default function QuickCommunicationPanel({ client, getAuthHeaders, onCommunicationLogged }) {
  const [channel, setChannel] = useState('whatsapp');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [bucketInfo, setBucketInfo] = useState(null);
  const [templateKey, setTemplateKey] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [emailTo, setEmailTo] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [messageBody, setMessageBody] = useState('');

  // Deps específicas em vez de `client` completo — impede re-render espúrio
  // que apagava as edições do utilizador quando o parent refaz fetch (e
  // devolve nova referência de client com o mesmo id/campos relevantes).
  const clientId = client?.id;
  const clientFinanceMobile = client?.finance_mobile;
  const clientMobile = client?.mobile;
  const clientPhone = client?.phone;
  const clientFinanceEmail = client?.finance_email;
  const clientEmail = client?.email;

  const defaultNumber = useMemo(
    () => pickWhatsAppNumber({
      finance_mobile: clientFinanceMobile,
      mobile: clientMobile,
      phone: clientPhone,
    }),
    [clientFinanceMobile, clientMobile, clientPhone]
  );
  const defaultEmail = useMemo(
    () => pickEmail({ finance_email: clientFinanceEmail, email: clientEmail }),
    [clientFinanceEmail, clientEmail]
  );

  // Carregar templates + bucket
  useEffect(() => {
    if (!clientId) return;
    (async () => {
      try {
        const [tRes, bRes] = await Promise.all([
          axios.get(`${API_URL}/api/finance/email-templates?active_only=true`, { headers: getAuthHeaders() }),
          axios.get(`${API_URL}/api/finance/clients/${clientId}/dunning-bucket`, { headers: getAuthHeaders() }),
        ]);
        const allTemplates = tRes.data.templates || [];
        setTemplates(allTemplates);
        setBucketInfo(bRes.data);

        // Escolher template recomendado (primeiro do bucket)
        const suggested = (bRes.data?.bucket?.suggested_template_keys || [])[0];
        const initial = suggested && allTemplates.find((t) => t.key === suggested)
          ? suggested
          : (allTemplates[0]?.key || '');
        setTemplateKey(initial);
      } catch (err) {
        console.error('Erro a carregar templates/bucket:', err);
      }
    })();
  }, [clientId, getAuthHeaders]);

  // Actualizar corpo/subject quando muda template ou canal.
  // Dependência em campos primitivos evita reset por nova referência do
  // objecto client vinda do parent após fetches externos.
  const clientName = client?.name;
  const clientOverdue = client?.overdue_balance_collectable;
  const clientDays = client?.oldest_overdue_days;
  useEffect(() => {
    const t = templates.find((x) => x.key === templateKey);
    if (!t) return;
    const clientForInterp = {
      name: clientName,
      overdue_balance_collectable: clientOverdue,
      oldest_overdue_days: clientDays,
    };
    setEmailSubject(interpolate(t.subject, clientForInterp));
    setMessageBody(interpolate(
      channel === 'whatsapp' ? (t.whatsapp_body || t.body) : t.body,
      clientForInterp
    ));
  }, [templateKey, channel, templates, clientName, clientOverdue, clientDays]);

  // Prefill do phoneNumber/emailTo APENAS quando o diálogo abre — nunca
  // durante edição do utilizador. Antes, o efeito disparava a cada render
  // do parent com nova referência de client, apagando o input em curso.
  useEffect(() => {
    if (!dialogOpen) return;
    setPhoneNumber(defaultNumber);
    setEmailTo(defaultEmail);
  }, [dialogOpen, defaultNumber, defaultEmail]);

  const logAction = async (actionType, notes) => {
    try {
      await axios.post(
        `${API_URL}/api/finance/clients/${client.id}/actions`,
        {
          action_type: actionType,
          notes: notes.slice(0, 4000),
          delay_reason: null,
          next_action_date: null,
        },
        { headers: getAuthHeaders() }
      );
      onCommunicationLogged && onCommunicationLogged();
    } catch (err) {
      console.error('Erro a registar comunicação:', err);
      toast.error('Comunicação enviada, mas falhou o registo no histórico');
    }
  };

  const handleOpenWhatsApp = async () => {
    if (!phoneNumber) {
      toast.error('Sem número de telemóvel');
      return;
    }
    const clean = phoneNumber.replace(/[^\d]/g, '');
    const url = `https://wa.me/${clean}?text=${encodeURIComponent(messageBody)}`;
    window.open(url, '_blank', 'noopener,noreferrer');
    const tpl = templates.find((x) => x.key === templateKey);
    await logAction(
      'whatsapp',
      `[WhatsApp aberto → ${clean}] template=${tpl?.label || templateKey}\n\n${messageBody}`
    );
    toast.success('WhatsApp aberto — comunicação registada no histórico');
    setDialogOpen(false);
  };

  const handleCopyMessage = async () => {
    try {
      await navigator.clipboard.writeText(messageBody);
      const tpl = templates.find((x) => x.key === templateKey);
      await logAction(
        channel,
        `[Mensagem copiada / ${channel.toUpperCase()}] template=${tpl?.label || templateKey}\n\n${messageBody}`
      );
      toast.success('Copiado — registado no histórico');
    } catch {
      toast.error('Falha ao copiar');
    }
  };

  const handleOpenEmail = async () => {
    if (!emailTo) {
      toast.error('Sem email financeiro configurado');
      return;
    }
    const mailto = `mailto:${encodeURIComponent(emailTo)}?subject=${encodeURIComponent(emailSubject)}&body=${encodeURIComponent(messageBody)}`;
    window.open(mailto, '_blank', 'noopener,noreferrer');
    const tpl = templates.find((x) => x.key === templateKey);
    await logAction(
      'email',
      `[Email preparado → ${emailTo}] subject="${emailSubject}" template=${tpl?.label || templateKey}\n\n${messageBody}`
    );
    toast.success('Email preparado — comunicação registada no histórico');
    setDialogOpen(false);
  };

  const [sending, setSending] = useState(false);
  const handleSendEmailNow = async () => {
    if (!emailTo || !emailSubject || !messageBody) {
      toast.error('Destinatário, assunto e corpo obrigatórios');
      return;
    }
    setSending(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/finance/clients/${client.id}/send-email`,
        {
          to: emailTo,
          subject: emailSubject,
          body: messageBody,
          template_key: templateKey,
        },
        { headers: getAuthHeaders() }
      );
      if (res.data.sent) {
        toast.success(`Email enviado (id: ${res.data.provider_id?.slice(0, 8) || 'ok'})`);
        onCommunicationLogged && onCommunicationLogged();
        setDialogOpen(false);
      } else {
        toast.error(`Envio falhou: ${res.data.error || 'erro desconhecido'}`);
      }
    } catch (err) {
      console.error('Erro a enviar:', err);
      toast.error(err?.response?.data?.detail || 'Erro ao enviar');
    } finally {
      setSending(false);
    }
  };

  const bucket = bucketInfo?.bucket;
  const bucketStyle = bucket ? (BUCKET_STYLES[bucket.color] || BUCKET_STYLES.yellow) : '';

  return (
    <>
      <Card data-testid="quick-communication-panel">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <MessageSquare className="h-4 w-4" /> Comunicação rápida
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Bucket recomendado */}
          {bucket && (
            <div className="text-sm">
              <div className="flex items-center gap-2 mb-1">
                <Sparkles className="h-4 w-4 text-slate-400" />
                <span className="text-xs text-slate-500">Régua de cobrança</span>
              </div>
              <Badge className={`${bucketStyle} border`} data-testid="dunning-bucket-badge">
                {bucket.label}
              </Badge>
              {bucket.suggested_actions?.length > 0 && (
                <div className="text-xs text-slate-500 mt-1">
                  Ações sugeridas: {bucket.suggested_actions.slice(0, 3).join(', ')}
                </div>
              )}
            </div>
          )}
          <div className="text-xs text-slate-500 pt-2 border-t">
            Todas as comunicações são registadas automaticamente no histórico.
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setChannel('whatsapp'); setDialogOpen(true); }}
              disabled={!defaultNumber}
              data-testid="quick-comm-whatsapp-btn"
            >
              <MessageSquare className="h-4 w-4 mr-1 text-emerald-600" /> WhatsApp
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setChannel('email'); setDialogOpen(true); }}
              disabled={!defaultEmail}
              data-testid="quick-comm-email-btn"
            >
              <Mail className="h-4 w-4 mr-1 text-blue-600" /> Email
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setChannel('whatsapp'); setDialogOpen(true); }}
              data-testid="quick-comm-copy-btn"
            >
              <Copy className="h-4 w-4 mr-1" /> Preparar mensagem
            </Button>
          </div>
          <div className="text-xs text-slate-400 space-y-0.5 pt-2 border-t">
            <div>Nº para WhatsApp: <span className="font-mono">{defaultNumber || '—'}</span></div>
            <div>Email financeiro: <span className="font-mono">{defaultEmail || '—'}</span></div>
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl" data-testid="quick-comm-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {channel === 'whatsapp' ? <MessageSquare className="h-5 w-5 text-emerald-600" /> : <Mail className="h-5 w-5 text-blue-600" />}
              Preparar mensagem — {channel === 'whatsapp' ? 'WhatsApp' : 'Email'}
            </DialogTitle>
            <DialogDescription asChild>
              <div>
                Cliente: <strong>{client?.name}</strong> · #{client?.genes_code} · vencido {formatCurrency(client?.overdue_balance_collectable)}
                {bucket && (
                  <span className="ml-2">
                    · <Badge className={`${bucketStyle} border ml-1`}>{bucket.label}</Badge>
                  </span>
                )}
              </div>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="flex gap-2">
              <Button
                variant={channel === 'whatsapp' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setChannel('whatsapp')}
                data-testid="quick-comm-channel-whatsapp"
              >
                <MessageSquare className="h-4 w-4 mr-1" /> WhatsApp
              </Button>
              <Button
                variant={channel === 'email' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setChannel('email')}
                data-testid="quick-comm-channel-email"
              >
                <Mail className="h-4 w-4 mr-1" /> Email
              </Button>
            </div>

            <div className="space-y-1">
              <Label className="text-xs flex items-center gap-1">
                Modelo
                {bucket && (
                  <span className="text-slate-400">
                    · sugerido para <span className="font-medium">{bucket.label}</span>
                  </span>
                )}
              </Label>
              <Select value={templateKey} onValueChange={setTemplateKey}>
                <SelectTrigger data-testid="quick-comm-template-select">
                  <SelectValue placeholder="Escolher template..." />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((t) => {
                    const isSuggested = bucket?.suggested_template_keys?.includes(t.key);
                    return (
                      <SelectItem key={t.id} value={t.key}>
                        {isSuggested && '⭐ '}{t.label}
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>

            {channel === 'whatsapp' ? (
              <div className="space-y-1">
                <Label className="text-xs">Número WhatsApp (com indicativo, ex: 351912345678)</Label>
                <Input
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="351912345678"
                  data-testid="quick-comm-phone-input"
                />
              </div>
            ) : (
              <>
                <div className="space-y-1">
                  <Label className="text-xs">Destinatário (email)</Label>
                  <Input
                    type="email"
                    value={emailTo}
                    onChange={(e) => setEmailTo(e.target.value)}
                    placeholder="email@cliente.pt"
                    data-testid="quick-comm-email-to-input"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Assunto</Label>
                  <Input
                    value={emailSubject}
                    onChange={(e) => setEmailSubject(e.target.value)}
                    data-testid="quick-comm-email-subject-input"
                  />
                </div>
              </>
            )}

            <div className="space-y-1">
              <Label className="text-xs">Mensagem</Label>
              <Textarea
                rows={8}
                value={messageBody}
                onChange={(e) => setMessageBody(e.target.value)}
                data-testid="quick-comm-body-input"
              />
              <div className="text-xs text-slate-400">{messageBody.length} caracteres</div>
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancelar</Button>
            <Button variant="outline" onClick={handleCopyMessage} data-testid="quick-comm-copy-confirm-btn">
              <Copy className="h-4 w-4 mr-1" /> Copiar
            </Button>
            {channel === 'whatsapp' ? (
              <Button onClick={handleOpenWhatsApp} className="bg-emerald-600 hover:bg-emerald-700" data-testid="quick-comm-whatsapp-open-btn">
                <ExternalLink className="h-4 w-4 mr-1" /> Abrir WhatsApp
              </Button>
            ) : (
              <>
                <Button variant="outline" onClick={handleOpenEmail} data-testid="quick-comm-email-open-btn">
                  <ExternalLink className="h-4 w-4 mr-1" /> Abrir cliente email
                </Button>
                <Button
                  onClick={handleSendEmailNow}
                  disabled={sending}
                  className="bg-blue-600 hover:bg-blue-700"
                  data-testid="quick-comm-email-send-btn"
                >
                  <Send className="h-4 w-4 mr-1" />
                  {sending ? 'A enviar…' : 'Enviar agora'}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
