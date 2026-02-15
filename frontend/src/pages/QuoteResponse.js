import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
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
  Loader2
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const QuoteResponse = () => {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState(null);
  const [response, setResponse] = useState(null);
  const [comments, setComments] = useState('');
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    fetchQuote();
  }, [token]);

  const fetchQuote = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/public/quote/${token}`);
      setQuote(res.data);
      if (res.data.response_status) {
        setSubmitted(true);
        setResponse(res.data.response_status);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Link inválido ou expirado');
    } finally {
      setLoading(false);
    }
  };

  const submitResponse = async (status) => {
    setSubmitting(true);
    setResponse(status);
    try {
      await axios.post(`${API_URL}/api/public/quote/${token}/respond`, {
        status,
        comments
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

  return (
    <div className="min-h-screen bg-zinc-100">
      {/* Header */}
      <header className="bg-slate-900 py-4 px-6">
        <div className="max-w-2xl mx-auto flex items-center">
          <Wrench className="h-8 w-8 text-orange-500 mr-3" />
          <span className="text-xl font-black tracking-tight text-white">PDPV</span>
          <span className="text-zinc-400 ml-2">Pneus de Pedro V.</span>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-2xl mx-auto p-4 md:p-6">
        <Card>
          <CardHeader className="border-b">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-2xl">Orçamento #{quote.ticket_number}</CardTitle>
                <CardDescription>Responda ao orçamento abaixo</CardDescription>
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

            {/* Quote Details */}
            <div className="bg-orange-50 border border-orange-200 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-orange-600" />
                  <span className="font-semibold text-orange-800">Valor do Orçamento</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-orange-600">
                  <Clock className="h-4 w-4" />
                  {formatDate(quote.quote_sent_at)}
                </div>
              </div>
              <div className="text-4xl font-black text-orange-600">
                {formatCurrency(quote.quote_value)}
              </div>
              {quote.description && (
                <p className="mt-4 text-slate-700 whitespace-pre-wrap">{quote.description}</p>
              )}
            </div>

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
                    data-testid="quote-comments-input"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <Button
                    variant="outline"
                    className="h-14 text-lg border-2 border-red-300 text-red-700 hover:bg-red-50 hover:border-red-400"
                    onClick={() => submitResponse('REJECTED')}
                    disabled={submitting}
                    data-testid="reject-quote-btn"
                  >
                    {submitting && response === 'REJECTED' ? (
                      <Loader2 className="h-5 w-5 animate-spin mr-2" />
                    ) : (
                      <XCircle className="h-5 w-5 mr-2" />
                    )}
                    Recusar
                  </Button>
                  <Button
                    className="h-14 text-lg bg-emerald-600 hover:bg-emerald-700"
                    onClick={() => submitResponse('ACCEPTED')}
                    disabled={submitting}
                    data-testid="accept-quote-btn"
                  >
                    {submitting && response === 'ACCEPTED' ? (
                      <Loader2 className="h-5 w-5 animate-spin mr-2" />
                    ) : (
                      <CheckCircle className="h-5 w-5 mr-2" />
                    )}
                    Aceitar
                  </Button>
                </div>
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
                      Orçamento Aceite!
                    </h3>
                    <p className="text-emerald-700">
                      Obrigado pela sua resposta. Entraremos em contacto em breve para agendar o serviço.
                    </p>
                  </>
                ) : (
                  <>
                    <XCircle className="h-16 w-16 text-red-500 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-red-800 mb-2">
                      Orçamento Recusado
                    </h3>
                    <p className="text-red-700">
                      Obrigado pela sua resposta. Se precisar de ajuda, não hesite em contactar-nos.
                    </p>
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center mt-6 text-sm text-zinc-500">
          <p>PDPV - Pneus de Pedro V.</p>
          <p>Este é um link único e pessoal. Não o partilhe.</p>
        </div>
      </main>
    </div>
  );
};

export default QuoteResponse;
