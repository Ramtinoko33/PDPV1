import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { Checkbox } from '../components/ui/checkbox';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { 
  CheckCircle, 
  XCircle, 
  Wrench,
  FileText,
  Clock,
  User,
  Car,
  AlertCircle,
  Loader2,
  Phone,
  Mail,
  FileDown,
  AlertTriangle,
  MessageSquare,
  Calendar,
  PhoneCall
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Rejection reasons
const REJECTION_REASONS = [
  { code: 'preco_alto', label: 'Preço alto' },
  { code: 'vai_pedir_outra_opiniao', label: 'Vai pedir outra opinião/orçamento' },
  { code: 'resolveu_noutro_local', label: 'Já resolveu noutro local' },
  { code: 'nao_quer_avancar', label: 'Não quer avançar para já' },
  { code: 'nao_entendeu', label: 'Não entendeu o orçamento' },
  { code: 'quer_falar_primeiro', label: 'Quer falar com a oficina primeiro' },
  { code: 'outro', label: 'Outro' }
];

// Acceptance intents
const ACCEPTANCE_INTENTS = [
  { code: 'agendar', label: 'Quero agendar para uma data específica', icon: Calendar },
  { code: 'avancar', label: 'Podem avançar com o serviço', icon: Wrench },
  { code: 'contactar', label: 'Tenho dúvidas / Quero ser contactado', icon: PhoneCall },
];

const QuoteResponse = () => {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [quote, setQuote] = useState(null);
  const [branding, setBranding] = useState(null);
  const [error, setError] = useState(null);
  const [response, setResponse] = useState(null);
  const [comments, setComments] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [selectedOptions, setSelectedOptions] = useState([]);
  const [problemImages, setProblemImages] = useState([]);
  
  // Rejection reason state
  const [showRejectionModal, setShowRejectionModal] = useState(false);
  const [rejectionReasonCode, setRejectionReasonCode] = useState('');
  const [rejectionReasonNote, setRejectionReasonNote] = useState('');
  
  // Acceptance intent state
  const [showAcceptanceModal, setShowAcceptanceModal] = useState(false);
  const [acceptanceIntent, setAcceptanceIntent] = useState('');
  const [preferredDate, setPreferredDate] = useState('');
  const [preferredPeriod, setPreferredPeriod] = useState('');

  useEffect(() => {
    fetchData();
  }, [token]);

  const fetchData = async () => {
    try {
      const [quoteRes, brandingRes] = await Promise.all([
        axios.get(`${API_URL}/api/public/quote/${token}`),
        axios.get(`${API_URL}/api/public/branding`)
      ]);
      
      setQuote(quoteRes.data);
      setBranding(brandingRes.data);

      // Fetch visible problem images
      if (quoteRes.data.ticket_id) {
        try {
          const imgRes = await axios.get(`${API_URL}/api/telegram-alerts/public/tickets/${quoteRes.data.ticket_id}/problem-images`);
          if (imgRes.data.images?.length > 0) {
            setProblemImages(imgRes.data.images);
          }
        } catch { /* silent */ }
      }
      
      // Check if decision already made (use quote_decided_at for definitive status)
      if (quoteRes.data.quote_decided_at || quoteRes.data.response_status) {
        setSubmitted(true);
        setResponse(quoteRes.data.quote_decision || quoteRes.data.response_status);
        // Mark accepted options as selected
        if (quoteRes.data.quote_options) {
          const acceptedIds = quoteRes.data.quote_options
            .filter(o => o.is_accepted)
            .map(o => o.id);
          setSelectedOptions(acceptedIds);
        }
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Link inválido ou expirado');
    } finally {
      setLoading(false);
    }
  };

  const toggleOption = (optionId) => {
    setSelectedOptions(prev => 
      prev.includes(optionId)
        ? prev.filter(id => id !== optionId)
        : [...prev, optionId]
    );
  };

  const getSelectedTotal = () => {
    if (!quote?.quote_options) return 0;
    return quote.quote_options
      .filter(o => selectedOptions.includes(o.id))
      .reduce((sum, o) => sum + o.amount, 0);
  };

  const handleRejectClick = () => {
    // Show rejection reason modal instead of submitting directly
    setShowRejectionModal(true);
  };

  const confirmRejection = async () => {
    // Validate rejection reason
    if (!rejectionReasonCode) {
      toast.error('Selecione um motivo de rejeição');
      return;
    }
    if (rejectionReasonCode === 'outro' && !rejectionReasonNote.trim()) {
      toast.error('Para "Outro" motivo, a observação é obrigatória');
      return;
    }
    
    setSubmitting(true);
    setResponse('REJECTED');
    try {
      const selectedReason = REJECTION_REASONS.find(r => r.code === rejectionReasonCode);
      await axios.post(`${API_URL}/api/public/quote/${token}/respond`, {
        status: 'REJECTED',
        comments,
        accepted_option_ids: [],
        rejection_reason_code: rejectionReasonCode,
        rejection_reason_label: selectedReason?.label || rejectionReasonCode,
        rejection_reason_note: rejectionReasonNote || null
      });
      setSubmitted(true);
      setShowRejectionModal(false);
      toast.success('Orçamento recusado');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao submeter resposta');
      setResponse(null);
    } finally {
      setSubmitting(false);
    }
  };

  const submitResponse = async (status) => {
    if (status === 'REJECTED') {
      handleRejectClick();
      return;
    }
    
    if (status === 'ACCEPTED' && selectedOptions.length === 0 && quote.quote_options?.length > 0) {
      toast.error('Selecione pelo menos uma opção');
      return;
    }
    
    // Show acceptance modal
    setShowAcceptanceModal(true);
  };

  const confirmAcceptance = async () => {
    if (!acceptanceIntent) {
      toast.error('Selecione como pretende avançar');
      return;
    }
    if (acceptanceIntent === 'agendar' && !preferredDate) {
      toast.error('Selecione a data pretendida');
      return;
    }
    if (acceptanceIntent === 'agendar' && !preferredPeriod) {
      toast.error('Selecione a altura do dia (manhã ou tarde)');
      return;
    }

    setSubmitting(true);
    setResponse('ACCEPTED');
    try {
      await axios.post(`${API_URL}/api/public/quote/${token}/respond`, {
        status: 'ACCEPTED',
        comments,
        accepted_option_ids: selectedOptions,
        acceptance_intent: acceptanceIntent,
        preferred_date: acceptanceIntent === 'agendar' ? preferredDate : null,
        preferred_period: acceptanceIntent === 'agendar' ? preferredPeriod : null,
      });
      setSubmitted(true);
      setShowAcceptanceModal(false);
      toast.success('Orçamento aceite!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao submeter resposta');
      setResponse(null);
    } finally {
      setSubmitting(false);
    }
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString('pt-PT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('pt-PT', { 
      style: 'currency', 
      currency: 'EUR' 
    }).format(value);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-100 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 text-orange-600 animate-spin mx-auto mb-4" />
          <p className="text-zinc-600">A carregar orçamento...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-100 flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6 text-center">
            <AlertCircle className="h-16 w-16 text-red-500 mx-auto mb-4" />
            <h2 className="text-xl font-bold text-slate-900 mb-2">Link Inválido</h2>
            <p className="text-zinc-600">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const hasOptions = quote.quote_options && quote.quote_options.length > 0;
  const totalQuoteValue = hasOptions 
    ? quote.quote_options.reduce((sum, o) => sum + o.amount, 0) 
    : quote.quote_value;
  
  const isExpired = quote.quote_valid_until && new Date() > new Date(quote.quote_valid_until);
  const anyOptionHasAttachments = hasOptions && quote.quote_options.some(o => o.attachments?.length > 0);
  const showGeneralPDFs = !anyOptionHasAttachments && quote.ticket_attachments?.length > 0;

  // Open attachment PDF from server
  const openAttachmentPDF = (attachmentId) => {
    window.open(`${API_URL}/api/public/quote/${token}/attachments/${attachmentId}/download`, '_blank');
  };

  // Brand colors - fixed for uniformity
  const BRAND_NAVY = '#0B2E4F';
  const BRAND_YELLOW = '#F4B400';
  const BRAND_GREEN = '#0F5132';
  const LOGO_URL = 'https://customer-assets.emergentagent.com/job_808588e9-0bee-4c5b-a24f-c36fa11718a7/artifacts/bstd2ega_logotipo%20de%20letras%20brancas.png';

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header - Uniform Design */}
      <header style={{ backgroundColor: BRAND_NAVY }} className="py-5 px-4">
        <div className="max-w-xl mx-auto text-center">
          <img 
            src={LOGO_URL} 
            alt="Pneus D. Pedro V" 
            className="h-12 mx-auto mb-2 object-contain"
          />
          <h1 className="text-white text-lg font-bold">Gestor De Pedidos</h1>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-xl mx-auto p-4 md:p-6">
        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-2xl">Orçamento #{quote.ticket_number}</CardTitle>
                <CardDescription>
                  {hasOptions 
                    ? 'Selecione as opções que pretende aceitar'
                    : 'Responda ao orçamento abaixo'
                  }
                </CardDescription>
              </div>
              <Badge className={`text-lg px-4 py-2 ${
                submitted 
                  ? response === 'ACCEPTED' 
                    ? 'bg-emerald-100 text-emerald-700' 
                    : 'bg-red-100 text-red-700'
                  : 'bg-amber-100 text-amber-700'
              }`}>
                {submitted 
                  ? response === 'ACCEPTED' ? 'Aceite' : 'Recusado'
                  : 'Aguarda Resposta'
                }
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-6 space-y-6">
            {/* Customer Info */}
            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-zinc-100 rounded-lg flex items-center justify-center">
                  <User className="h-5 w-5 text-zinc-600" />
                </div>
                <div>
                  <p className="text-xs text-zinc-500 uppercase">Cliente</p>
                  <p className="font-semibold">{quote.customer_name}</p>
                </div>
              </div>
              {quote.vehicle_plate && (
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-zinc-100 rounded-lg flex items-center justify-center">
                    <Car className="h-5 w-5 text-zinc-600" />
                  </div>
                  <div>
                    <p className="text-xs text-zinc-500 uppercase">Matrícula</p>
                    <p className="font-semibold font-mono">{quote.vehicle_plate}</p>
                  </div>
                </div>
              )}
            </div>

            {/* Context text — single line below client info */}
            {quote.quote_context && (
              <p className="text-[12px] text-zinc-400 -mt-2 mb-1">
                {quote.quote_context === 'diagnostic'
                  ? 'Identificado na verificação do veículo'
                  : quote.quote_context === 'customer_request'
                    ? 'Com base no seu pedido'
                    : 'Sujeito a verificação em oficina'
                }
              </p>
            )}

            {/* Quote Options or Single Value */}
            <div 
              className="rounded-lg p-6"
              style={{ 
                backgroundColor: `${branding?.primary_color || '#f97316'}10`,
                border: `2px solid ${branding?.primary_color || '#f97316'}`
              }}
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <FileText 
                    className="h-5 w-5" 
                    style={{ color: branding?.primary_color || '#f97316' }}
                  />
                  <span 
                    className="font-semibold"
                    style={{ color: branding?.primary_color || '#f97316' }}
                  >
                    {hasOptions ? 'Opções de Orçamento' : 'Valor do Orçamento'}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm" style={{ color: branding?.primary_color || '#f97316' }}>
                  <Clock className="h-4 w-4" />
                  {formatDate(quote.quote_sent_at)}
                </div>
              </div>
              {quote.quote_valid_until && (
                <div className={`flex items-center gap-2 text-xs mb-4 px-3 py-1.5 rounded-md ${
                  isExpired ? 'bg-red-100 text-red-700' : 'bg-zinc-100 text-zinc-600'
                }`}>
                  <Clock className="h-3 w-3" />
                  {isExpired
                    ? `Expirado em ${formatDate(quote.quote_valid_until)}`
                    : `Válido até ${formatDate(quote.quote_valid_until)}`}
                </div>
              )}

              {hasOptions ? (
                <>
                <div className="space-y-3">
                  {/* Soft recommendation if critical items exist */}
                  {!submitted && quote.quote_options.some(o => o.display_priority === 'critical') && (
                    <p className="text-[12px] text-zinc-500 leading-relaxed mb-1">
                      <span className="font-medium">Recomendação:</span> Resolva primeiro o ponto prioritário. Pode adicionar os restantes serviços se desejar.
                    </p>
                  )}

                  {(() => {
                    // Sort by priority: critical > safety > normal > tires
                    const priorityOrder = { critical: 0, safety: 1, normal: 2 };
                    const sorted = [...quote.quote_options].sort((a, b) => {
                      const pa = priorityOrder[a.display_priority] ?? 2;
                      const pb = priorityOrder[b.display_priority] ?? 2;
                      if (pa !== pb) return pa - pb;
                      // Tires last within same priority
                      const tireA = a.display_brand_tier != null ? 1 : 0;
                      const tireB = b.display_brand_tier != null ? 1 : 0;
                      return tireA - tireB;
                    });

                    let lastLabel = null;

                    return sorted.map((option) => {
                      const isSelected = selectedOptions.includes(option.id);
                      const isAccepted = option.is_accepted;
                      const isTire = option.display_brand_tier != null;
                      const labelKey = option.display_priority === 'critical'
                        ? 'critical'
                        : option.display_priority === 'safety'
                          ? (isTire ? 'tire' : 'safety')
                          : (isTire ? 'tire' : 'normal');
                      const labels = {
                        critical: { text: 'Atenção prioritária', color: 'text-red-500' },
                        safety: { text: 'Segurança', color: 'text-amber-500' },
                        tire: { text: 'Escolha', color: 'text-blue-500' },
                        normal: { text: 'Manutenção', color: 'text-emerald-500' },
                      };
                      const priorityLabel = labels[labelKey];
                      const showLabel = labelKey !== lastLabel;
                      lastLabel = labelKey;

                      // Tire-specific copy
                      const getMessage = () => {
                        if (isTire) return 'Melhora aderência e segurança na condução';
                        if (option.display_priority === 'critical') return 'Recomendamos resolver de imediato para evitar danos graves';
                        if (option.display_priority === 'safety') return 'Pode afetar a segurança do carro';
                        return 'Ajuda a evitar problemas futuros';
                      };

                      return (
                        <div key={option.id}>
                          {showLabel && (
                            <p className={`text-[12px] font-medium ${priorityLabel.color} mb-1 ml-1 ${lastLabel !== labelKey ? '' : 'mt-2'}`}>
                              {priorityLabel.text}
                            </p>
                          )}
                          <div 
                            className={`p-4 rounded-lg border-2 transition-all ${
                              submitted
                                ? isAccepted 
                                  ? 'bg-emerald-50 border-emerald-300' 
                                  : 'bg-zinc-50 border-zinc-200 opacity-60'
                                : isSelected
                                  ? 'bg-white border-emerald-400 shadow-md'
                                  : 'bg-white border-zinc-200 hover:border-zinc-300'
                            } ${!submitted && !isExpired ? 'cursor-pointer' : ''}`}
                            onClick={() => !submitted && !isExpired && toggleOption(option.id)}
                            data-testid={`quote-option-${option.id}`}
                          >
                            <div className="flex items-center">
                              {!submitted ? (
                                <Checkbox
                                  checked={isSelected}
                                  onCheckedChange={() => !isExpired && toggleOption(option.id)}
                                  className="mr-4 h-5 w-5"
                                  disabled={isExpired}
                                  data-testid={`quote-option-checkbox-${option.id}`}
                                />
                              ) : (
                                <div className="mr-4">
                                  {isAccepted ? (
                                    <CheckCircle className="h-5 w-5 text-emerald-600" />
                                  ) : (
                                    <XCircle className="h-5 w-5 text-zinc-400" />
                                  )}
                                </div>
                              )}
                              <div className="flex-1">
                                <p className="font-medium text-slate-800">
                                  {option.display_title || option.description}
                                </p>
                                {option.display_type === 'package' && option.display_includes?.length > 1 && (
                                  <p className="text-xs text-slate-500 mt-0.5">
                                    Inclui: {option.display_includes.join(' + ')}
                                  </p>
                                )}
                                {option.display_priority_message && (
                                  <p className={`text-xs mt-1 ${
                                    option.display_priority === 'critical'
                                      ? 'text-red-500'
                                      : option.display_priority === 'safety'
                                        ? 'text-amber-500'
                                        : 'text-emerald-600'
                                  }`}>
                                    {getMessage()}
                                  </p>
                                )}
                              </div>
                              {option.display_recommended && (
                                <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full mr-2 shrink-0 bg-emerald-100 text-emerald-700 border border-emerald-200">
                                  Recomendado
                                </span>
                              )}
                              {option.display_priority && option.display_priority !== 'normal' && !option.display_recommended && (
                                <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full mr-3 shrink-0 ${
                                  option.display_priority === 'critical'
                                    ? 'bg-red-100 text-red-700'
                                    : 'bg-amber-100 text-amber-700'
                                }`}>
                                  {option.display_priority === 'critical' ? 'Atenção prioritária' : 'Segurança'}
                                </span>
                              )}
                              <div 
                                className="text-xl font-bold"
                                style={{ color: branding?.primary_color || '#f97316' }}
                              >
                                {formatCurrency(option.amount)}
                              </div>
                            </div>
                            {option.attachments?.length > 0 && (
                              <div className="mt-3 pt-3 border-t border-zinc-200 flex flex-wrap gap-2" onClick={e => e.stopPropagation()}>
                                {option.attachments.map((att) => (
                                  <button
                                    key={att.id}
                                    onClick={() => openAttachmentPDF(att.id)}
                                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-zinc-300 bg-white hover:bg-zinc-50 text-zinc-700 transition-colors"
                                    data-testid={`pdf-option-${att.id}`}
                                  >
                                    <FileDown className="h-3.5 w-3.5 text-red-500" />
                                    Ver detalhes (PDF)
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    });
                  })()}

                  {/* Critical items unselected warning */}
                  {!submitted && quote.quote_options.some(o => o.display_priority === 'critical' && !selectedOptions.includes(o.id)) && selectedOptions.length > 0 && (
                    <p className="text-xs text-amber-600 mt-2" data-testid="critical-unselected-warning">
                      Existe um ponto importante por resolver
                    </p>
                  )}
                  
                  {/* Total */}
                  <div className="pt-4 mt-4 border-t-2 border-dashed flex justify-between items-center">
                    <span className="text-lg font-semibold text-slate-700">
                      {submitted ? 'Total aceite:' : 'Total dos serviços escolhidos:'}
                    </span>
                    <span 
                      className="text-3xl font-black"
                      style={{ color: branding?.primary_color || '#f97316' }}
                    >
                      {formatCurrency(submitted && quote.accepted_total ? quote.accepted_total : getSelectedTotal())}
                    </span>
                  </div>
                  {submitted && quote.accepted_count && (
                    <p className="text-sm text-zinc-500 text-right">
                      {quote.accepted_count} de {quote.quote_options.length} opções aceites
                    </p>
                  )}
                </div>

                {/* Problem Images Section (visible to customer) */}
                {problemImages.length > 0 && (
                  <div className="mt-6 pt-4 border-t">
                    <h4 className="text-sm font-semibold text-slate-600 mb-3">Fotos do problema</h4>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                      {problemImages.map((img) => (
                        <PublicProblemImage key={img.id} ticketId={quote.ticket_id} imageId={img.id} />
                      ))}
                    </div>
                  </div>
                )}
                </>
              ) : (
                <>
                  <div 
                    className="text-4xl font-black"
                    style={{ color: branding?.primary_color || '#f97316' }}
                  >
                    {formatCurrency(quote.quote_value)}
                  </div>
                  {quote.description && (
                    <p className="mt-4 text-slate-700 whitespace-pre-wrap">{quote.description}</p>
                  )}
                </>
              )}
            </div>

            {/* General PDF Section (only if no option-specific PDFs) */}
            {showGeneralPDFs && (
              <div className="rounded-lg border border-zinc-200 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <FileText className="h-4 w-4 text-zinc-600" />
                  <span className="text-sm font-semibold text-zinc-700">Orçamento detalhado (PDF)</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {quote.ticket_attachments.map((att) => (
                    <button
                      key={att.id}
                      onClick={() => openAttachmentPDF(att.id)}
                      className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-md border border-zinc-300 bg-zinc-50 hover:bg-zinc-100 text-zinc-700 transition-colors"
                      data-testid={`pdf-general-${att.id}`}
                    >
                      <FileDown className="h-4 w-4 text-red-500" />
                      {att.original_filename}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Expired Banner */}
            {isExpired && !submitted && (
              <div className="flex items-center gap-3 p-4 rounded-lg bg-red-50 border border-red-200" data-testid="quote-expired-banner">
                <AlertTriangle className="h-5 w-5 text-red-600 shrink-0" />
                <p className="text-red-700 font-medium">Orçamento expirado. Contacte a oficina.</p>
              </div>
            )}

            {/* Response Section */}
            {!submitted ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Comentários (opcional)
                  </label>
                  <Textarea
                    placeholder="Adicione algum comentário ou observação..."
                    value={comments}
                    onChange={(e) => setComments(e.target.value)}
                    className="min-h-[100px]"
                    disabled={isExpired}
                    data-testid="quote-comments-input"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <Button
                    variant="outline"
                    className="h-14 text-lg border-2"
                    style={{ borderColor: '#dc2626', color: '#dc2626' }}
                    onClick={() => submitResponse('REJECTED')}
                    disabled={submitting || isExpired}
                    data-testid="reject-quote-btn"
                  >
                    {submitting && response === 'REJECTED' ? (
                      <Loader2 className="h-5 w-5 animate-spin mr-2" />
                    ) : (
                      <XCircle className="h-5 w-5 mr-2" />
                    )}
                    Recusar Tudo
                  </Button>
                  <Button
                    className="h-14 text-lg font-bold"
                    style={{ backgroundColor: BRAND_YELLOW, color: BRAND_NAVY }}
                    onClick={() => submitResponse('ACCEPTED')}
                    disabled={submitting || isExpired || (hasOptions && selectedOptions.length === 0)}
                    data-testid="accept-quote-btn"
                  >
                    {submitting && response === 'ACCEPTED' ? (
                      <Loader2 className="h-5 w-5 animate-spin mr-2" />
                    ) : (
                      <CheckCircle className="h-5 w-5 mr-2" />
                    )}
                    {hasOptions 
                      ? `Confirmar serviços${selectedOptions.length > 0 ? ` (${selectedOptions.length})` : ''}`
                      : 'Confirmar serviços'
                    }
                  </Button>
                </div>
                {hasOptions && selectedOptions.length === 0 && !isExpired && (
                  <p className="text-sm text-amber-600 text-center">
                    Selecione pelo menos uma opção para aceitar
                  </p>
                )}
              </div>
            ) : (
              <div className={`p-6 rounded-lg text-center ${
                response === 'ACCEPTED' 
                  ? 'bg-emerald-50 border border-emerald-200' 
                  : 'bg-red-50 border border-red-200'
              }`}>
                {response === 'ACCEPTED' ? (
                  <>
                    <CheckCircle className="h-16 w-16 text-emerald-600 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-emerald-800 mb-2">
                      {branding?.quote_page_accepted_title || 'Orçamento Aceite!'}
                    </h3>
                    <p className="text-emerald-700">
                      {branding?.quote_page_accepted_message || 'Obrigado pela sua resposta. Entraremos em contacto em breve para agendar o serviço.'}
                    </p>
                    {quote.quote_decided_at && (
                      <p className="text-sm text-emerald-600 mt-3">
                        Decisão registada em {new Date(quote.quote_decided_at).toLocaleDateString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <XCircle className="h-16 w-16 text-red-600 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-red-800 mb-2">
                      {branding?.quote_page_rejected_title || 'Orçamento Recusado'}
                    </h3>
                    <p className="text-red-700">
                      {branding?.quote_page_rejected_message || 'Obrigado pela sua resposta. Se mudar de ideias, não hesite em contactar-nos.'}
                    </p>
                    {quote.quote_decided_at && (
                      <p className="text-sm text-red-600 mt-3">
                        Decisão registada em {new Date(quote.quote_decided_at).toLocaleDateString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    )}
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Contact Footer */}
        {branding && (branding.company_phone || branding.company_email) && (
          <div className="mt-6 text-center text-sm text-zinc-600">
            <p className="mb-2">Dúvidas? Contacte-nos:</p>
            <div className="flex items-center justify-center gap-4">
              {branding.company_phone && (
                <a 
                  href={`tel:${branding.company_phone}`} 
                  className="flex items-center gap-1 hover:text-orange-600"
                >
                  <Phone className="h-4 w-4" />
                  {branding.company_phone}
                </a>
              )}
              {branding.company_email && (
                <a 
                  href={`mailto:${branding.company_email}`} 
                  className="flex items-center gap-1 hover:text-orange-600"
                >
                  <Mail className="h-4 w-4" />
                  {branding.company_email}
                </a>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Footer - Uniform Design */}
      <footer style={{ backgroundColor: BRAND_NAVY }} className="py-3 px-4 mt-6">
        <div className="max-w-xl mx-auto text-center">
          <p className="text-gray-400 text-xs">
            Pneus D. Pedro V. | Ticket #{quote?.ticket_number}
          </p>
        </div>
      </footer>

      {/* Rejection Reason Modal */}
      {showRejectionModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-red-100 rounded-full">
                  <MessageSquare className="h-6 w-6 text-red-600" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-zinc-900">Confirmar Rejeição</h3>
                  <p className="text-sm text-zinc-500">Antes de concluir, pode indicar o motivo da rejeição?</p>
                </div>
              </div>
              
              <p className="text-sm text-zinc-600 mb-4">
                A sua resposta ajuda-nos a melhorar os nossos serviços.
              </p>

              {/* Rejection Reasons */}
              <div className="space-y-2 mb-4">
                {REJECTION_REASONS.map((reason) => (
                  <label 
                    key={reason.code}
                    className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                      rejectionReasonCode === reason.code 
                        ? 'border-red-500 bg-red-50' 
                        : 'border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50'
                    }`}
                    data-testid={`rejection-reason-${reason.code}`}
                  >
                    <input
                      type="radio"
                      name="rejectionReason"
                      value={reason.code}
                      checked={rejectionReasonCode === reason.code}
                      onChange={(e) => setRejectionReasonCode(e.target.value)}
                      className="w-4 h-4 text-red-600 border-zinc-300 focus:ring-red-500"
                    />
                    <span className="text-sm text-zinc-700">{reason.label}</span>
                  </label>
                ))}
              </div>

              {/* Additional Note */}
              <div className="mb-4">
                <Label htmlFor="rejection-note" className="text-sm text-zinc-600 mb-2 block">
                  Observação adicional {rejectionReasonCode === 'outro' && <span className="text-red-500">*</span>}
                </Label>
                <Textarea
                  id="rejection-note"
                  placeholder={rejectionReasonCode === 'outro' 
                    ? "Por favor, descreva o motivo..." 
                    : "Observação opcional..."
                  }
                  value={rejectionReasonNote}
                  onChange={(e) => setRejectionReasonNote(e.target.value)}
                  className="min-h-[80px]"
                  data-testid="rejection-note-input"
                />
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    setShowRejectionModal(false);
                    setRejectionReasonCode('');
                    setRejectionReasonNote('');
                  }}
                  disabled={submitting}
                >
                  Voltar
                </Button>
                <Button
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white"
                  onClick={confirmRejection}
                  disabled={submitting || !rejectionReasonCode}
                  data-testid="confirm-rejection-btn"
                >
                  {submitting ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <XCircle className="h-4 w-4 mr-2" />
                  )}
                  Confirmar Rejeição
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Acceptance Intent Modal */}
      {showAcceptanceModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 rounded-full" style={{ backgroundColor: `${branding?.primary_color || '#f97316'}20` }}>
                  <CheckCircle className="h-6 w-6" style={{ color: branding?.primary_color || '#f97316' }} />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-zinc-900">Como pretende avançar?</h3>
                  <p className="text-sm text-zinc-500">Ajude-nos a organizar o seu serviço da melhor forma.</p>
                </div>
              </div>

              {/* Acceptance Intents */}
              <div className="space-y-2 mb-4">
                {ACCEPTANCE_INTENTS.map((intent) => {
                  const Icon = intent.icon;
                  return (
                    <label 
                      key={intent.code}
                      className={`flex items-center gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all ${
                        acceptanceIntent === intent.code 
                          ? 'border-emerald-500 bg-emerald-50' 
                          : 'border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50'
                      }`}
                      data-testid={`acceptance-intent-${intent.code}`}
                    >
                      <input
                        type="radio"
                        name="acceptanceIntent"
                        value={intent.code}
                        checked={acceptanceIntent === intent.code}
                        onChange={(e) => {
                          setAcceptanceIntent(e.target.value);
                          if (e.target.value !== 'agendar') {
                            setPreferredDate('');
                            setPreferredPeriod('');
                          }
                        }}
                        className="w-4 h-4 text-emerald-600 border-zinc-300 focus:ring-emerald-500"
                      />
                      <Icon className={`h-5 w-5 shrink-0 ${acceptanceIntent === intent.code ? 'text-emerald-600' : 'text-zinc-400'}`} />
                      <span className="text-sm text-zinc-700 font-medium">{intent.label}</span>
                    </label>
                  );
                })}
              </div>

              {/* Scheduling fields - only show when "agendar" is selected */}
              {acceptanceIntent === 'agendar' && (
                <div className="space-y-3 mb-4 p-4 rounded-lg bg-emerald-50 border border-emerald-200">
                  <div>
                    <Label htmlFor="preferred-date" className="text-sm font-medium text-zinc-700 mb-1.5 block">
                      Data pretendida <span className="text-red-500">*</span>
                    </Label>
                    <input
                      id="preferred-date"
                      type="date"
                      value={preferredDate}
                      min={new Date().toISOString().split('T')[0]}
                      onChange={(e) => setPreferredDate(e.target.value)}
                      className="w-full px-3 py-2 rounded-md border border-zinc-300 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
                      data-testid="preferred-date-input"
                    />
                  </div>
                  <div>
                    <Label className="text-sm font-medium text-zinc-700 mb-1.5 block">
                      Altura do dia <span className="text-red-500">*</span>
                    </Label>
                    <div className="grid grid-cols-2 gap-2">
                      <label
                        className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 cursor-pointer transition-all text-sm font-medium ${
                          preferredPeriod === 'manha'
                            ? 'border-emerald-500 bg-white text-emerald-700'
                            : 'border-zinc-200 hover:border-zinc-300 text-zinc-600'
                        }`}
                        data-testid="period-manha"
                      >
                        <input
                          type="radio"
                          name="preferredPeriod"
                          value="manha"
                          checked={preferredPeriod === 'manha'}
                          onChange={(e) => setPreferredPeriod(e.target.value)}
                          className="sr-only"
                        />
                        Manhã
                      </label>
                      <label
                        className={`flex items-center justify-center gap-2 p-3 rounded-lg border-2 cursor-pointer transition-all text-sm font-medium ${
                          preferredPeriod === 'tarde'
                            ? 'border-emerald-500 bg-white text-emerald-700'
                            : 'border-zinc-200 hover:border-zinc-300 text-zinc-600'
                        }`}
                        data-testid="period-tarde"
                      >
                        <input
                          type="radio"
                          name="preferredPeriod"
                          value="tarde"
                          checked={preferredPeriod === 'tarde'}
                          onChange={(e) => setPreferredPeriod(e.target.value)}
                          className="sr-only"
                        />
                        Tarde
                      </label>
                    </div>
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    setShowAcceptanceModal(false);
                    setAcceptanceIntent('');
                    setPreferredDate('');
                    setPreferredPeriod('');
                  }}
                  disabled={submitting}
                >
                  Voltar
                </Button>
                <Button
                  className="flex-1 text-white font-bold"
                  style={{ backgroundColor: '#059669' }}
                  onClick={confirmAcceptance}
                  disabled={submitting || !acceptanceIntent || (acceptanceIntent === 'agendar' && (!preferredDate || !preferredPeriod))}
                  data-testid="confirm-acceptance-btn"
                >
                  {submitting ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <CheckCircle className="h-4 w-4 mr-2" />
                  )}
                  Confirmar Aceitação
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Sub-component: Public problem image with lazy load
const PublicProblemImage = ({ ticketId, imageId }) => {
  const [src, setSrc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [enlarged, setEnlarged] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const resp = await axios.get(
          `${API_URL}/api/telegram-alerts/public/tickets/${ticketId}/problem-images/${imageId}`
        );
        if (cancelled) return;
        if (resp.data.base64) {
          setSrc(`data:${resp.data.file_type || 'image/jpeg'};base64,${resp.data.base64}`);
        }
      } catch { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    };
    load();
    return () => { cancelled = true; };
  }, [ticketId, imageId]);

  if (!loading && !src) return null;

  return (
    <>
      <div
        className="rounded-lg overflow-hidden border border-zinc-200 bg-zinc-100 aspect-square cursor-pointer hover:ring-2 hover:ring-orange-300 transition-all"
        onClick={() => src && setEnlarged(true)}
      >
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <img src={src} alt="Foto do problema" className="w-full h-full object-cover" />
        )}
      </div>
      {enlarged && (
        <div className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-4" onClick={() => setEnlarged(false)}>
          <img src={src} alt="Foto do problema" className="max-w-full max-h-full object-contain rounded-lg" />
        </div>
      )}
    </>
  );
};

export default QuoteResponse;
