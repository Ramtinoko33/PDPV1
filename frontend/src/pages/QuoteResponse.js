import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { Checkbox } from '../components/ui/checkbox';
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
  AlertTriangle
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

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
      
      if (quoteRes.data.response_status) {
        setSubmitted(true);
        setResponse(quoteRes.data.response_status);
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

  const submitResponse = async (status) => {
    if (status === 'ACCEPTED' && selectedOptions.length === 0 && quote.quote_options?.length > 0) {
      toast.error('Selecione pelo menos uma opção');
      return;
    }
    
    setSubmitting(true);
    setResponse(status);
    try {
      await axios.post(`${API_URL}/api/public/quote/${token}/respond`, {
        status,
        comments,
        accepted_option_ids: status === 'ACCEPTED' ? selectedOptions : []
      });
      setSubmitted(true);
      toast.success(status === 'ACCEPTED' ? 'Orçamento aceite!' : 'Orçamento recusado');
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

  const openPDF = (attachmentId) => {
    window.open(`${API_URL}/api/public/quote/${token}/attachments/${attachmentId}/download`, '_blank');
  };

  return (
    <div className="min-h-screen bg-zinc-100">
      {/* Header */}
      <header 
        className="py-4 px-6"
        style={{ backgroundColor: branding?.secondary_color || '#1f2937' }}
      >
        <div className="max-w-2xl mx-auto flex items-center">
          {branding?.company_logo_url ? (
            <img 
              src={branding.company_logo_url} 
              alt={branding?.company_name || 'Logo'} 
              className="h-10 mr-3 object-contain"
            />
          ) : (
            <Wrench 
              className="h-8 w-8 mr-3" 
              style={{ color: branding?.primary_color || '#f97316' }}
            />
          )}
          <span className="text-xl font-black tracking-tight text-white">
            {branding?.company_name || 'PDPV'}
          </span>
          <span className="text-zinc-400 ml-2">
            {branding?.company_subtitle || 'Pneus de Pedro V.'}
          </span>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-2xl mx-auto p-4 md:p-6">
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
                <div className="space-y-3">
                  {quote.quote_options.map((option) => {
                    const isSelected = selectedOptions.includes(option.id);
                    const isAccepted = option.is_accepted;
                    
                    return (
                      <div 
                        key={option.id}
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
                            <p className="font-medium text-slate-800">{option.description}</p>
                          </div>
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
                                onClick={() => openPDF(att.id)}
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
                    );
                  })}
                  
                  {/* Total */}
                  <div className="pt-4 mt-4 border-t-2 border-dashed flex justify-between items-center">
                    <span className="text-lg font-semibold text-slate-700">
                      {submitted ? 'Total Aceite:' : 'Total Selecionado:'}
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
                      onClick={() => openPDF(att.id)}
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
                    className="h-14 text-lg border-2 border-red-300 text-red-700 hover:bg-red-50 hover:border-red-400"
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
                    className="h-14 text-lg"
                    style={{ backgroundColor: branding?.primary_color || '#16a34a' }}
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
                      ? `Aceitar${selectedOptions.length > 0 ? ` (${selectedOptions.length})` : ''}`
                      : 'Aceitar'
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
    </div>
  );
};

export default QuoteResponse;
