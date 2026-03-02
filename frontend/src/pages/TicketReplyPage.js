import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import {
  CheckCircle,
  Wrench,
  Car,
  User,
  Paperclip,
  X,
  Send,
  Loader2,
  AlertCircle,
  FileText
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const typeLabels = {
  ORCAMENTO_PNEUS: 'Orçamento Pneus',
  ORCAMENTO_MECANICA: 'Orçamento Mecânica',
  MARCACAO: 'Marcação',
  INFORMACAO: 'Informação',
  INTERNO: 'Interno',
  RECLAMACAO: 'Reclamação',
};

const statusLabels = {
  ABERTO: 'Aberto',
  EM_TRATAMENTO: 'Em Tratamento',
  AGUARDA_CLIENTE: 'Aguarda Resposta',
  ACEITE_LINK: 'Aceite',
  REJEITADO_LINK: 'Rejeitado',
  AGENDADO: 'Agendado',
  FECHADO: 'Fechado',
};

export default function TicketReplyPage() {
  const { token } = useParams();
  const [ticket, setTicket] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState('');
  const [files, setFiles] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const fileInputRef = useRef(null);

  // Brand colors - fixed for uniformity
  const BRAND_NAVY = '#0B2E4F';
  const BRAND_YELLOW = '#F4B400';
  const BRAND_GREEN = '#0F5132';
  const LOGO_URL = 'https://customer-assets.emergentagent.com/job_808588e9-0bee-4c5b-a24f-c36fa11718a7/artifacts/bstd2ega_logotipo%20de%20letras%20brancas.png';

  useEffect(() => {
    const fetchTicket = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/public/reply/${token}`);
        setTicket(res.data);
      } catch (err) {
        setError(err.response?.status === 404 ? 'Link não encontrado ou inválido.' : 'Erro ao carregar os dados do pedido.');
      } finally {
        setLoading(false);
      }
    };
    fetchTicket();
  }, [token]);

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    setFiles(prev => [...prev, ...selected]);
    e.target.value = '';
  };

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (!message.trim()) {
      toast.error('Por favor escreva uma mensagem antes de enviar.');
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('body', message.trim());
      files.forEach(f => formData.append('files', f));
      await axios.post(`${API_URL}/api/public/reply/${token}/submit`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setSubmitted(true);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao enviar a mensagem. Tente novamente.');
    } finally {
      setSubmitting(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const primaryColor = ticket?.primary_color || '#f97316';

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-zinc-500">
          <Loader2 className="h-8 w-8 animate-spin" style={{ color: primaryColor }} />
          <p className="text-sm">A carregar...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full border-red-200">
          <CardContent className="pt-8 pb-8 flex flex-col items-center gap-4 text-center">
            <AlertCircle className="h-12 w-12 text-red-500" />
            <p className="text-lg font-semibold text-red-700">{error}</p>
            <p className="text-sm text-zinc-500">Se acredita que este link é válido, contacte a oficina.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-zinc-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-10 pb-10 flex flex-col items-center gap-5 text-center">
            <div className="w-16 h-16 rounded-full flex items-center justify-center" style={{ backgroundColor: `${primaryColor}20` }}>
              <CheckCircle className="h-9 w-9" style={{ color: primaryColor }} />
            </div>
            <div>
              <p className="text-xl font-bold text-slate-800">Mensagem enviada!</p>
              <p className="text-sm text-zinc-500 mt-2">
                A sua resposta foi recebida com sucesso. A nossa equipa irá tratar do seu pedido em breve.
              </p>
            </div>
            <div className="w-full p-4 bg-zinc-50 rounded-lg text-left space-y-1">
              <p className="text-xs text-zinc-500">Referência do pedido</p>
              <p className="font-mono font-bold text-slate-800">{ticket?.ticket_number}</p>
            </div>
            {files.length > 0 && (
              <p className="text-xs text-zinc-500">
                {files.length} ficheiro(s) enviado(s) com sucesso.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50">
      {/* Header */}
      <div className="py-5 px-6 text-white" style={{ backgroundColor: primaryColor }}>
        <div className="max-w-xl mx-auto flex items-center gap-3">
          {ticket.logo_url ? (
            <img src={ticket.logo_url} alt="Logo" className="h-8 w-8 object-contain rounded" />
          ) : (
            <Wrench className="h-6 w-6 text-white/80" />
          )}
          <span className="text-lg font-bold">{ticket.company_name}</span>
        </div>
      </div>

      <div className="max-w-xl mx-auto px-4 py-8 space-y-5">
        {/* Ticket Info */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold text-slate-700 flex items-center gap-2">
              <FileText className="h-4 w-4" style={{ color: primaryColor }} />
              Informações do Pedido
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-bold text-slate-800" data-testid="reply-ticket-number">
                {ticket.ticket_number}
              </span>
              <Badge className="text-xs bg-zinc-100 text-zinc-700 border border-zinc-200">
                {statusLabels[ticket.status] || ticket.status}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="flex items-center gap-2 text-zinc-600">
                <User className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate" data-testid="reply-customer-name">{ticket.customer_name}</span>
              </div>
              {ticket.vehicle_plate && (
                <div className="flex items-center gap-2 text-zinc-600">
                  <Car className="h-3.5 w-3.5 shrink-0" />
                  <span data-testid="reply-vehicle-plate">{ticket.vehicle_plate}</span>
                </div>
              )}
            </div>
            {ticket.ticket_type && (
              <div className="text-xs text-zinc-500">
                {typeLabels[ticket.ticket_type] || ticket.ticket_type}
              </div>
            )}
            {ticket.description && (
              <div className="pt-2 border-t text-sm text-zinc-600 line-clamp-3">
                {ticket.description}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Reply Form */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold text-slate-700">
              Enviar Resposta
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Mensagem <span className="text-red-500">*</span>
              </label>
              <Textarea
                placeholder="Escreva aqui a sua mensagem, dúvidas ou informações adicionais..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                className="min-h-[130px] resize-none"
                data-testid="reply-message-textarea"
              />
            </div>

            {/* File Upload */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Anexar documentos (opcional)
              </label>
              <div
                className="border-2 border-dashed border-zinc-300 rounded-lg p-4 text-center cursor-pointer hover:border-zinc-400 transition-colors"
                onClick={() => fileInputRef.current?.click()}
                data-testid="reply-file-upload-area"
              >
                <Paperclip className="h-5 w-5 mx-auto mb-1 text-zinc-400" />
                <p className="text-sm text-zinc-500">Clique para selecionar ficheiros</p>
                <p className="text-xs text-zinc-400 mt-0.5">PDF, imagens, documentos</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleFileChange}
                data-testid="reply-file-input"
              />
              {files.length > 0 && (
                <div className="mt-3 space-y-2" data-testid="reply-file-list">
                  {files.map((file, idx) => (
                    <div key={idx} className="flex items-center gap-2 p-2 bg-zinc-50 rounded border text-sm">
                      <FileText className="h-4 w-4 text-zinc-400 shrink-0" />
                      <span className="flex-1 truncate text-zinc-700">{file.name}</span>
                      <span className="text-xs text-zinc-400 shrink-0">{formatFileSize(file.size)}</span>
                      <button
                        onClick={() => removeFile(idx)}
                        className="text-zinc-400 hover:text-red-500 transition-colors"
                        data-testid={`remove-file-${idx}`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <Button
              className="w-full h-12 text-base font-bold"
              style={{ backgroundColor: primaryColor }}
              onClick={handleSubmit}
              disabled={submitting || !message.trim()}
              data-testid="reply-submit-btn"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin mr-2" />
                  A enviar...
                </>
              ) : (
                <>
                  <Send className="h-5 w-5 mr-2" />
                  Enviar Resposta
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <p className="text-center text-xs text-zinc-400">
          {ticket.company_name} · Este portal é exclusivo para este pedido.
        </p>
      </div>
    </div>
  );
}
