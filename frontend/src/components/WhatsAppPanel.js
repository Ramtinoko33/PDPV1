import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { toast } from 'sonner';
import {
  MessageCircle, Send, Clock, AlertCircle, CheckCircle2, Link2,
  Check, CheckCheck, AlertTriangle, Loader2,
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STATUS_ICON = {
  pending: <Clock className="h-3 w-3 text-zinc-400" title="A enviar" />,
  sent: <Check className="h-3 w-3 text-zinc-500" title="Enviada" />,
  delivered: <CheckCheck className="h-3 w-3 text-zinc-500" title="Entregue" />,
  read: <CheckCheck className="h-3 w-3 text-blue-500" title="Lida" />,
  failed: <AlertTriangle className="h-3 w-3 text-red-500" title="Falhou" />,
};

const formatTime = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('pt-PT', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
};

const formatRemaining = (expiresIso) => {
  if (!expiresIso) return '';
  try {
    const ms = new Date(expiresIso) - new Date();
    if (ms <= 0) return 'expirado';
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  } catch { return ''; }
};

const WhatsAppPanel = ({ ticketId, ticket }) => {
  const { getAuthHeaders } = useAuth();
  const [messages, setMessages] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [window, setWindow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [composer, setComposer] = useState('');
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [msgsR, winR, tplR] = await Promise.all([
        axios.get(`${API_URL}/api/whatsapp/tickets/${ticketId}/messages`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/whatsapp/tickets/${ticketId}/window`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/whatsapp/templates`, { headers: getAuthHeaders() }),
      ]);
      setMessages(msgsR.data || []);
      setWindow(winR.data || null);
      setTemplates(tplR.data || []);
    } catch (e) {
      console.error('Failed to load WhatsApp data:', e);
    } finally {
      setLoading(false);
    }
  }, [ticketId, getAuthHeaders]);

  useEffect(() => { load(); }, [load]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = async () => {
    if (!composer.trim()) return;
    setSending(true);
    try {
      await axios.post(
        `${API_URL}/api/whatsapp/tickets/${ticketId}/messages`,
        { body: composer.trim() },
        { headers: getAuthHeaders() }
      );
      setComposer('');
      toast.success('Mensagem enviada');
      load();
    } catch (e) {
      const detail = e?.response?.data?.detail || 'Erro a enviar';
      toast.error(detail);
    } finally {
      setSending(false);
    }
  };

  const sendQuoteLink = async () => {
    setSending(true);
    try {
      await axios.post(
        `${API_URL}/api/whatsapp/tickets/${ticketId}/send-quote-link`,
        {},
        { headers: getAuthHeaders() }
      );
      toast.success('Link de orçamento enviado por WhatsApp');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro');
    } finally {
      setSending(false);
    }
  };

  const insertTemplate = (tpl) => {
    let text = tpl.text;
    if (tpl.placeholders) {
      text = text
        .replace('{{nome}}', ticket?.customer_name || 'Cliente')
        .replace('{{matricula}}', ticket?.vehicle_plate || '—')
        .replace('{{link_resposta}}', '');
    }
    setComposer(text);
  };

  if (!ticket?.customer_phone) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-zinc-500">
          <MessageCircle className="h-8 w-8 mx-auto mb-2 text-zinc-300" />
          Ticket sem número de telefone — WhatsApp indisponível.
        </CardContent>
      </Card>
    );
  }

  const isWindowOpen = !!window?.active;

  return (
    <Card data-testid="whatsapp-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center justify-between flex-wrap gap-2">
          <span className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5 text-emerald-600" /> WhatsApp
            <span className="text-xs text-zinc-500 font-normal">({ticket.customer_phone})</span>
          </span>
          {window && (
            isWindowOpen ? (
              <Badge className="bg-emerald-100 text-emerald-700 border border-emerald-200" data-testid="wa-window-open">
                <CheckCircle2 className="h-3 w-3 mr-1" /> Janela aberta · {formatRemaining(window.expires_at)}
              </Badge>
            ) : (
              <Badge className="bg-red-100 text-red-700 border border-red-200" data-testid="wa-window-closed">
                <AlertCircle className="h-3 w-3 mr-1" /> Janela fechada
              </Badge>
            )
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Conversation thread */}
        <div ref={scrollRef} className="bg-zinc-50 rounded-lg p-3 max-h-[400px] overflow-y-auto space-y-2" data-testid="wa-thread">
          {loading ? (
            <div className="text-center py-6"><Loader2 className="h-5 w-5 animate-spin text-zinc-400 mx-auto" /></div>
          ) : messages.length === 0 ? (
            <div className="text-center text-zinc-500 text-sm py-6">Sem mensagens ainda.</div>
          ) : (
            messages.map(m => {
              const isOut = m.direction === 'outbound' || m.direction === 'OUTBOUND';
              return (
                <div key={m.id} className={`flex ${isOut ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[75%] px-3 py-2 rounded-2xl ${
                    isOut ? 'bg-emerald-100 text-zinc-900 rounded-br-sm' : 'bg-white border text-zinc-900 rounded-bl-sm'
                  }`}>
                    {!isOut && m.sender_name && (
                      <div className="text-[10px] font-semibold text-emerald-700 mb-0.5">{m.sender_name}</div>
                    )}
                    <div className="text-sm whitespace-pre-wrap break-words">{m.body}</div>
                    <div className="flex items-center gap-1 justify-end text-[10px] text-zinc-500 mt-0.5">
                      {formatTime(m.created_at)}
                      {isOut && STATUS_ICON[m.status]}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Templates */}
        <div className="flex flex-wrap gap-1.5">
          {templates.map(tpl => (
            <Button
              key={tpl.id}
              size="sm"
              variant="outline"
              disabled={!isWindowOpen}
              onClick={() => insertTemplate(tpl)}
              className="text-xs h-7"
              data-testid={`wa-tpl-${tpl.id}`}
            >
              {tpl.label}
            </Button>
          ))}
          <Button
            size="sm"
            variant="default"
            disabled={!isWindowOpen || sending}
            onClick={sendQuoteLink}
            className="text-xs h-7 ml-auto bg-emerald-600 hover:bg-emerald-700"
            data-testid="wa-send-quote-link"
          >
            <Link2 className="h-3 w-3 mr-1" /> Enviar link de orçamento
          </Button>
        </div>

        {/* Composer */}
        {!isWindowOpen && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800" data-testid="wa-closed-warning">
            <AlertCircle className="h-4 w-4 inline mr-1" />
            A janela WhatsApp está fechada. É necessário template aprovado da Meta (não implementado nesta fase).
          </div>
        )}
        <Textarea
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
          placeholder={isWindowOpen ? 'Escrever mensagem...' : 'Janela fechada — preencher template Meta (futuro)'}
          rows={3}
          disabled={!isWindowOpen || sending}
          data-testid="wa-composer"
        />
        <div className="flex justify-end">
          <Button
            onClick={sendMessage}
            disabled={!isWindowOpen || sending || !composer.trim()}
            className="bg-emerald-600 hover:bg-emerald-700"
            data-testid="wa-send-btn"
          >
            <Send className="h-4 w-4 mr-1" /> {sending ? 'A enviar...' : 'Enviar WhatsApp'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default WhatsAppPanel;
