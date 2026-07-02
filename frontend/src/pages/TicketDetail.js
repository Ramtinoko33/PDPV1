import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Checkbox } from '../components/ui/checkbox';
import { ScrollArea } from '../components/ui/scroll-area';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { toast } from 'sonner';
import { 
  ArrowLeft, 
  Phone, 
  Mail, 
  Car, 
  User, 
  Clock,
  Send,
  MessageSquare,
  MessageCircle,
  FileText,
  AlertTriangle,
  Upload,
  Download,
  CheckCircle,
  XCircle,
  History,
  StickyNote,
  Paperclip,
  X,
  Archive,
  RotateCcw,
  Link2,
  Copy,
  ExternalLink,
  ChevronRight,
  Pencil,
  Plus,
  Trash2,
  Bell,
  Calendar,
  Reply,
  RefreshCcw,
  AlertCircle,
  Eye,
  Camera
} from 'lucide-react';
import WhatsAppPanel from '../components/WhatsAppPanel';
import { CreditWarningBanner } from '../components/CreditWarningBanner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Component for generating and managing quote links
const QuoteLinkSection = ({ ticketId, getAuthHeaders, compact = false }) => {
  const [generating, setGenerating] = useState(false);
  const [quoteLink, setQuoteLink] = useState(null);
  
  const generateLink = async () => {
    setGenerating(true);
    try {
      const response = await axios.post(
        `${API_URL}/api/tickets/${ticketId}/generate-quote-link`,
        {},
        { headers: getAuthHeaders() }
      );
      
      const fullLink = `${window.location.origin}/quote/${response.data.token}`;
      setQuoteLink({
        ...response.data,
        fullLink
      });
      
      // Copy to clipboard (may fail in some contexts, but we still want to show success)
      try {
        await navigator.clipboard.writeText(fullLink);
        toast.success(response.data.email_sent 
          ? 'Link gerado, copiado e enviado por email!' 
          : 'Link gerado e copiado!');
      } catch (clipboardError) {
        // Clipboard failed but link was still generated successfully
        toast.success(response.data.email_sent 
          ? 'Link gerado e enviado por email! (copie manualmente)' 
          : 'Link gerado com sucesso! (copie manualmente)');
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao gerar link');
    } finally {
      setGenerating(false);
    }
  };
  
  const copyLink = async () => {
    if (quoteLink?.fullLink) {
      await navigator.clipboard.writeText(quoteLink.fullLink);
      toast.success('Link copiado!');
    }
  };
  
  // Compact version for conversation tab
  if (compact) {
    return !quoteLink ? (
      <Button
        variant="outline"
        size="sm"
        className="border-amber-400 text-amber-700 hover:bg-amber-100"
        onClick={generateLink}
        disabled={generating}
        data-testid="generate-quote-link-btn"
      >
        {generating ? (
          <div className="w-3 h-3 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mr-1" />
        ) : (
          <Link2 className="h-3 w-3 mr-1" />
        )}
        Gerar Link
      </Button>
    ) : (
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={copyLink}
          className="border-amber-400 text-amber-700"
          title="Copiar link"
        >
          <Copy className="h-3 w-3 mr-1" />
          Copiar
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => window.open(quoteLink.fullLink, '_blank')}
          className="border-amber-400 text-amber-700"
          title="Abrir link"
        >
          <ExternalLink className="h-3 w-3" />
        </Button>
      </div>
    );
  }
  
  // Full version for documents tab
  return (
    <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg space-y-3">
      <div className="flex items-center gap-2">
        <Link2 className="h-5 w-5 text-amber-600" />
        <span className="font-semibold text-amber-800">Link de Aceitação de Orçamento</span>
      </div>
      
      {!quoteLink ? (
        <Button
          variant="outline"
          className="border-amber-300 text-amber-700 hover:bg-amber-100"
          onClick={generateLink}
          disabled={generating}
          data-testid="generate-quote-link-btn-full"
        >
          {generating ? (
            <div className="w-4 h-4 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mr-2" />
          ) : (
            <Link2 className="h-4 w-4 mr-2" />
          )}
          Gerar Link para Cliente
        </Button>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Input
              value={quoteLink.fullLink}
              readOnly
              className="flex-1 bg-white text-sm font-mono"
            />
            <Button
              variant="outline"
              size="icon"
              onClick={copyLink}
              className="border-amber-300"
              data-testid="copy-quote-link-btn"
            >
              <Copy className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => window.open(quoteLink.fullLink, '_blank')}
              className="border-amber-300"
              data-testid="open-quote-link-btn"
            >
              <ExternalLink className="h-4 w-4" />
            </Button>
          </div>
          <p className="text-xs text-amber-600">
            Link válido até {new Date(quoteLink.expires_at).toLocaleDateString('pt-PT')}
          </p>
        </div>
      )}
    </div>
  );
};

// Component for generating and managing customer reply links
const ReplyLinkSection = ({ ticketId, getAuthHeaders, existingToken = null }) => {
  const [generating, setGenerating] = useState(false);
  const [replyLink, setReplyLink] = useState(
    existingToken ? `${window.location.origin}/ticket/reply/${existingToken}` : null
  );

  const generateLink = async () => {
    setGenerating(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/tickets/${ticketId}/generate-reply-link`,
        {},
        { headers: getAuthHeaders() }
      );
      const fullLink = `${window.location.origin}/ticket/reply/${res.data.token}`;
      setReplyLink(fullLink);
      try {
        await navigator.clipboard.writeText(fullLink);
        toast.success('Link de resposta copiado!');
      } catch {
        toast.success('Link de resposta gerado! (copie manualmente)');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao gerar link');
    } finally {
      setGenerating(false);
    }
  };

  const copyLink = async () => {
    if (replyLink) {
      await navigator.clipboard.writeText(replyLink);
      toast.success('Link copiado!');
    }
  };

  return (
    <Card>
      <CardHeader className="border-b pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <Reply className="h-5 w-5 text-blue-600" />
          Link de Resposta
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        <p className="text-xs text-zinc-500 mb-3">
          Este link é incluído automaticamente nos emails. Gere-o para partilhar manualmente.
        </p>
        {!replyLink ? (
          <Button
            variant="outline"
            className="border-blue-300 text-blue-700 hover:bg-blue-100 w-full"
            onClick={generateLink}
            disabled={generating}
            data-testid="generate-reply-link-btn"
          >
            {generating ? (
              <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mr-2" />
            ) : (
              <Reply className="h-4 w-4 mr-2" />
            )}
            Gerar Link de Resposta
          </Button>
        ) : (
          <div className="space-y-2">
            <Input
              value={replyLink}
              readOnly
              className="text-xs bg-zinc-50 border-blue-200 text-blue-800 font-mono"
              data-testid="reply-link-url"
            />
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={copyLink}
                className="flex-1 border-blue-300 text-blue-700 hover:bg-blue-100"
                data-testid="copy-reply-link-btn"
              >
                <Copy className="h-4 w-4 mr-1" />
                Copiar
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.open(replyLink, '_blank')}
                className="border-blue-300 text-blue-700 hover:bg-blue-100"
                data-testid="open-reply-link-btn"
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// Component for displaying quote value change history
const QuoteHistorySection = ({ ticketId, getAuthHeaders, formatDate }) => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  
  useEffect(() => {
    fetchHistory();
  }, [ticketId]);
  
  const fetchHistory = async () => {
    try {
      const response = await axios.get(
        `${API_URL}/api/tickets/${ticketId}/quote-history`,
        { headers: getAuthHeaders() }
      );
      setHistory(response.data);
    } catch (error) {
      console.error('Error fetching quote history:', error);
    } finally {
      setLoading(false);
    }
  };
  
  if (loading) return null;
  if (history.length === 0) return null;
  
  return (
    <Card>
      <CardHeader className="border-b cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <History className="h-5 w-5" />
            Histórico de Alterações do Orçamento
            <Badge variant="outline" className="ml-2">{history.length}</Badge>
          </CardTitle>
          <ChevronRight className={`h-5 w-5 transition-transform ${expanded ? 'rotate-90' : ''}`} />
        </div>
      </CardHeader>
      {expanded && (
        <CardContent className="p-0">
          <div className="divide-y">
            {history.map((entry) => (
              <div key={entry.id} className="p-4 hover:bg-zinc-50">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-amber-100 rounded-full flex items-center justify-center">
                      <FileText className="h-4 w-4 text-amber-600" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-900">
                        {entry.old_value !== null ? (
                          <><span className="text-zinc-500 line-through">{entry.old_value?.toFixed(2)}€</span> → </>
                        ) : null}
                        <span className="text-amber-600">{entry.new_value?.toFixed(2)}€</span>
                      </p>
                      <p className="text-xs text-zinc-500">
                        {entry.changed_by_name || 'Sistema'} • {formatDate(entry.changed_at)}
                      </p>
                    </div>
                  </div>
                </div>
                {entry.reason && (
                  <p className="mt-2 text-sm text-zinc-600 pl-11">{entry.reason}</p>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
};

// Component for Ticket Reminders
const RemindersSection = ({ ticketId, getAuthHeaders, users, currentUser }) => {
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newReminder, setNewReminder] = useState({ description: '', due_at: '', assigned_to_user_id: '' });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchReminders();
  }, [ticketId]);

  const fetchReminders = async () => {
    try {
      const response = await axios.get(
        `${API_URL}/api/tickets/${ticketId}/reminders`,
        { headers: getAuthHeaders() }
      );
      setReminders(response.data);
    } catch (error) {
      console.error('Error fetching reminders:', error);
    } finally {
      setLoading(false);
    }
  };

  const createReminder = async (e) => {
    e.preventDefault();
    if (!newReminder.description || !newReminder.due_at) {
      toast.error('Preencha descrição e data/hora');
      return;
    }
    setCreating(true);
    try {
      await axios.post(
        `${API_URL}/api/tickets/${ticketId}/reminders`,
        {
          description: newReminder.description,
          due_at: new Date(newReminder.due_at).toISOString(),
          assigned_to_user_id: newReminder.assigned_to_user_id || null
        },
        { headers: getAuthHeaders() }
      );
      toast.success('Lembrete criado');
      setNewReminder({ description: '', due_at: '', assigned_to_user_id: '' });
      setShowCreate(false);
      fetchReminders();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar lembrete');
    } finally {
      setCreating(false);
    }
  };

  const toggleComplete = async (reminder) => {
    try {
      if (reminder.is_done) {
        await axios.put(`${API_URL}/api/reminders/${reminder.id}/reopen`, {}, { headers: getAuthHeaders() });
        toast.success('Lembrete reaberto');
      } else {
        await axios.put(`${API_URL}/api/reminders/${reminder.id}/complete`, {}, { headers: getAuthHeaders() });
        toast.success('Lembrete concluído');
      }
      fetchReminders();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro');
    }
  };

  const deleteReminder = async (reminderId) => {
    if (!window.confirm('Eliminar este lembrete?')) return;
    try {
      await axios.delete(`${API_URL}/api/reminders/${reminderId}`, { headers: getAuthHeaders() });
      toast.success('Lembrete eliminado');
      fetchReminders();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro');
    }
  };

  const formatDateTime = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleString('pt-PT', { 
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  };

  const canManage = ['ADMIN', 'SUPERVISOR'].includes(currentUser?.role);

  return (
    <Card>
      <CardHeader className="border-b pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Bell className="h-5 w-5 text-purple-600" />
            Lembretes
            {reminders.length > 0 && (
              <Badge variant="outline" className="ml-1">{reminders.filter(r => !r.is_done).length}</Badge>
            )}
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowCreate(!showCreate)}
            className="border-purple-400 text-purple-700 hover:bg-purple-50"
          >
            <Plus className="h-4 w-4 mr-1" />
            Criar
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-4">
        {/* Create Form */}
        {showCreate && (
          <form onSubmit={createReminder} className="mb-4 p-4 bg-purple-50 border border-purple-200 rounded-lg space-y-3">
            <div>
              <Label className="text-purple-700">Descrição *</Label>
              <Input
                value={newReminder.description}
                onChange={(e) => setNewReminder({ ...newReminder, description: e.target.value })}
                placeholder="Ex: Ligar ao cliente para confirmar"
                className="border-purple-300"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-purple-700">Data/Hora *</Label>
                <Input
                  type="datetime-local"
                  value={newReminder.due_at}
                  onChange={(e) => setNewReminder({ ...newReminder, due_at: e.target.value })}
                  className="border-purple-300"
                />
              </div>
              <div>
                <Label className="text-purple-700">Atribuir a</Label>
                {['ADMIN', 'SUPERVISOR'].includes(user?.role) ? (
                  <Select
                    value={newReminder.assigned_to_user_id || "self"}
                    onValueChange={(v) => setNewReminder({ ...newReminder, assigned_to_user_id: v === "self" ? "" : v })}
                  >
                    <SelectTrigger className="border-purple-300">
                      <SelectValue placeholder="Eu próprio" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="self">Eu próprio</SelectItem>
                      {users.map(u => (
                        <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input value="Eu próprio" disabled className="bg-zinc-100 border-purple-300" />
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowCreate(false)}>
                Cancelar
              </Button>
              <Button type="submit" size="sm" disabled={creating} className="bg-purple-600 hover:bg-purple-700">
                {creating ? 'A criar...' : 'Criar Lembrete'}
              </Button>
            </div>
          </form>
        )}

        {/* Reminders List */}
        {loading ? (
          <p className="text-zinc-500 text-center py-4">A carregar...</p>
        ) : reminders.length === 0 ? (
          <p className="text-zinc-500 text-center py-4">Sem lembretes</p>
        ) : (
          <div className="space-y-2">
            {reminders.map((reminder) => (
              <div
                key={reminder.id}
                className={`flex items-center gap-3 p-3 rounded-lg border ${
                  reminder.is_done 
                    ? 'bg-zinc-50 border-zinc-200' 
                    : reminder.is_overdue 
                      ? 'bg-red-50 border-red-300' 
                      : 'bg-white border-zinc-200'
                }`}
              >
                <Checkbox
                  checked={reminder.is_done}
                  onCheckedChange={() => toggleComplete(reminder)}
                  className={reminder.is_overdue && !reminder.is_done ? 'border-red-500' : ''}
                />
                <div className="flex-1 min-w-0">
                  <p className={`font-medium ${reminder.is_done ? 'line-through text-zinc-500' : ''}`}>
                    {reminder.description}
                  </p>
                  <div className="flex items-center gap-2 text-xs text-zinc-500">
                    <Calendar className="h-3 w-3" />
                    <span className={reminder.is_overdue && !reminder.is_done ? 'text-red-600 font-semibold' : ''}>
                      {formatDateTime(reminder.due_at)}
                    </span>
                    {reminder.is_overdue && !reminder.is_done && (
                      <Badge className="bg-red-100 text-red-700 text-xs">ATRASADO</Badge>
                    )}
                    {reminder.assigned_to_name && (
                      <span>• {reminder.assigned_to_name}</span>
                    )}
                  </div>
                </div>
                {(canManage || reminder.created_by_user_id === currentUser?.id) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteReminder(reminder.id)}
                    className="h-8 w-8 p-0 text-zinc-400 hover:text-red-600"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

const TicketDetail = () => {
  const { id } = useParams();
  const { user, getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const messageFileInputRef = useRef(null);

  const [ticket, setTicket] = useState(null);
  const [messages, setMessages] = useState([]);
  const [notes, setNotes] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [attachmentUrls, setAttachmentUrls] = useState({}); // Blob URLs for authenticated preview
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [newMessage, setNewMessage] = useState('');
  const [newNote, setNewNote] = useState('');
  const [quoteValue, setQuoteValue] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [sendingNote, setSendingNote] = useState(false);
  const [uploadingFile, setUploadingFile] = useState(false);
  const [isQuoteResponse, setIsQuoteResponse] = useState(false);
  const [messageAttachments, setMessageAttachments] = useState([]);
  const [uploadingMessageFile, setUploadingMessageFile] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [allStatuses, setAllStatuses] = useState([]);
  const [quoteOptions, setQuoteOptions] = useState([]);
  const [savingOptions, setSavingOptions] = useState(false);
  const [optionPreviews, setOptionPreviews] = useState({});
  const [showPreviews, setShowPreviews] = useState(true);
  const previewTimers = useRef({});
  const [suggestionStates, setSuggestionStates] = useState({});
  // suggestionStates[index] = { mode: 'preview'|'editing'|'ignored', editText: '' }
  const [quoteContext, setQuoteContext] = useState('unknown');
  const [contextAutoDetected, setContextAutoDetected] = useState(true);
  const [contextSuggestion, setContextSuggestion] = useState(null);
  const [suggestionDismissed, setSuggestionDismissed] = useState(false);

  const fetchData = async () => {
    try {
      const [ticketRes, messagesRes, notesRes, alertsRes, attachmentsRes, optionsRes] = await Promise.all([
        axios.get(`${API_URL}/api/tickets/${id}`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/messages`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/notes`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/alerts`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/attachments`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/quote-options`, { headers: getAuthHeaders() }).catch(() => ({ data: [] }))
      ]);
      
      setTicket(ticketRes.data);
      setMessages(messagesRes.data);
      setNotes(notesRes.data);
      setAlerts(alertsRes.data);
      setAttachments(attachmentsRes.data);
      setQuoteValue(ticketRes.data.quote_value || '');

      // Fetch quote context
      try {
        const ctxRes = await axios.get(`${API_URL}/api/tickets/${id}/quote-context`, { headers: getAuthHeaders() });
        setQuoteContext(ctxRes.data.quote_context || 'unknown');
        setContextAutoDetected(ctxRes.data.auto_detected);
      } catch (err) { console.warn('quote-context fetch failed:', err?.message || err); }
      
      // Set quote options or create default empty one
      if (optionsRes.data && optionsRes.data.length > 0) {
        setQuoteOptions(optionsRes.data);
      } else {
        setQuoteOptions([{ id: 'temp-1', description: '', amount: '', attachment_ids: [] }]);
      }
    } catch (error) {
      toast.error('Erro ao carregar ticket');
      navigate('/tickets');
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    if (['ADMIN', 'SUPERVISOR'].includes(user?.role)) {
      try {
        const response = await axios.get(`${API_URL}/api/users`, { headers: getAuthHeaders() });
        // Filter active users with AGENT or SUPERVISOR role
        setUsers(response.data.filter(u => u.is_active !== false && ['AGENT', 'SUPERVISOR', 'ADMIN'].includes(u.role)));
      } catch (error) {
        console.error('Error fetching users:', error);
      }
    }
  };

  const fetchStatuses = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/ticket-statuses`, { headers: getAuthHeaders() });
      setAllStatuses(response.data);
    } catch (error) {
      console.error('Error fetching statuses:', error);
    }
  };

  useEffect(() => {
    fetchData();
    fetchUsers();
    fetchStatuses();
  }, [id]);

  // Create blob URLs for authenticated attachment preview
  useEffect(() => {
    const loadAttachmentUrls = async () => {
      const urls = {};
      for (const att of attachments) {
        const isImage = att.file_type?.startsWith('image/');
        const isPdf = att.file_type === 'application/pdf';
        
        if (isImage || isPdf) {
          try {
            const response = await fetch(`${API_URL}/api/attachments/${att.id}/download`, {
              headers: getAuthHeaders()
            });
            if (response.ok) {
              const blob = await response.blob();
              urls[att.id] = URL.createObjectURL(blob);
            }
          } catch (error) {
            console.error(`Error loading attachment ${att.id}:`, error);
          }
        }
      }
      setAttachmentUrls(urls);
    };

    if (attachments.length > 0) {
      loadAttachmentUrls();
    }

    // Cleanup: revoke blob URLs when component unmounts or attachments change
    return () => {
      Object.values(attachmentUrls).forEach(url => {
        if (url) URL.revokeObjectURL(url);
      });
    };
  }, [attachments]);

  const updateTicket = async (updates) => {
    try {
      await axios.put(`${API_URL}/api/tickets/${id}`, updates, { headers: getAuthHeaders() });
      toast.success('Ticket atualizado');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao atualizar ticket');
    }
  };

  const openEditDialog = () => {
    setEditForm({
      customer_name: ticket.customer_name || '',
      customer_phone: ticket.customer_phone || '',
      customer_email: ticket.customer_email || '',
      vehicle_plate: ticket.vehicle_plate || '',
      description: ticket.description || '',
      type: ticket.type || 'INFORMACAO',
      priority: ticket.priority || 'NORMAL'
    });
    setEditDialogOpen(true);
  };

  const saveTicketEdit = async () => {
    setSavingEdit(true);
    try {
      await axios.put(`${API_URL}/api/tickets/${id}`, editForm, { headers: getAuthHeaders() });
      toast.success('Ticket atualizado com sucesso');
      setEditDialogOpen(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao atualizar ticket');
    } finally {
      setSavingEdit(false);
    }
  };

  // Quote Options Management
  const addQuoteOption = () => {
    if (quoteOptions.length >= 10) {
      toast.error('Máximo de 10 opções');
      return;
    }
    setQuoteOptions([...quoteOptions, { id: `temp-${Date.now()}`, description: '', amount: '', attachment_ids: [] }]);
  };

  const removeQuoteOption = (index) => {
    if (quoteOptions.length <= 1) {
      toast.error('Mínimo de 1 opção');
      return;
    }
    setQuoteOptions(quoteOptions.filter((_, i) => i !== index));
  };

  const updateQuoteOption = (index, field, value) => {
    const updated = [...quoteOptions];
    updated[index] = { ...updated[index], [field]: value };
    setQuoteOptions(updated);

    // Debounced preview fetch for description changes
    if (field === 'description' && showPreviews) {
      if (previewTimers.current[index]) clearTimeout(previewTimers.current[index]);
      if (!value || value.trim().length < 2) {
        setOptionPreviews(prev => { const n = {...prev}; delete n[index]; return n; });
        return;
      }
      previewTimers.current[index] = setTimeout(async () => {
        try {
          const resp = await axios.get(`${API_URL}/api/normalize-preview`, {
            params: { description: value },
            headers: getAuthHeaders()
          });
          setOptionPreviews(prev => ({ ...prev, [index]: resp.data }));
        } catch (err) { console.warn('normalize-preview failed:', err?.message || err); }
      }, 400);
    }
  };

  const startEditSuggestion = (index) => {
    const preview = optionPreviews[index];
    setSuggestionStates(prev => ({
      ...prev,
      [index]: { mode: 'editing', editText: preview?.title || '' }
    }));
  };

  const ignoreSuggestion = (index) => {
    setSuggestionStates(prev => ({ ...prev, [index]: { mode: 'ignored' } }));
  };

  const updateSuggestionEdit = (index, text) => {
    setSuggestionStates(prev => ({
      ...prev,
      [index]: { ...prev[index], editText: text }
    }));
  };

  const saveSuggestionEdit = (index) => {
    setSuggestionStates(prev => ({
      ...prev,
      [index]: { ...prev[index], mode: 'edited' }
    }));
  };

  // Send learning events for all options with suggestions
  const sendLearningEvents = async (options) => {
    for (let i = 0; i < options.length; i++) {
      const preview = optionPreviews[i];
      if (!preview || !options[i]?.description) continue;

      const state = suggestionStates[i];
      const original = options[i].description;
      const suggested = preview.title || '';

      let action = 'implicit_accept';
      let finalText = suggested;

      if (state?.mode === 'ignored') {
        action = 'rejected';
        finalText = original;
      } else if (state?.mode === 'edited') {
        finalText = state.editText || '';
        // Similarity check: <30% different = modified, >=30% = rejected
        const maxLen = Math.max(suggested.length, finalText.length, 1);
        let diff = 0;
        for (let c = 0; c < maxLen; c++) {
          if ((suggested[c] || '') !== (finalText[c] || '')) diff++;
        }
        action = (diff / maxLen) < 0.3 ? 'modified' : 'rejected';
      }

      try {
        await axios.post(`${API_URL}/api/normalization-learning`, {
          original, suggested, final: finalText, action,
        }, { headers: getAuthHeaders() });
      } catch (err) { console.warn('normalization-learning failed:', err?.message || err); }
    }
  };



  const saveQuoteOptions = async () => {
    const validOptions = quoteOptions.filter(o => o.description && o.amount);
    if (validOptions.length === 0) {
      toast.error('Adicione pelo menos uma opção com descrição e valor');
      return;
    }
    
    setSavingOptions(true);
    try {
      const response = await axios.post(
        `${API_URL}/api/tickets/${id}/quote-options`,
        { options: validOptions.map(o => ({ description: o.description, amount: parseFloat(o.amount), attachment_ids: o.attachment_ids || [] })) },
        { headers: getAuthHeaders() }
      );
      setQuoteOptions(response.data);
      const total = validOptions.reduce((sum, o) => sum + parseFloat(o.amount || 0), 0);
      setQuoteValue(total.toString());
      toast.success('Opções de orçamento guardadas');
      fetchData();

      // Send learning events silently
      sendLearningEvents(validOptions);
      // Reset suggestion states
      setSuggestionStates({});

      // Check for context suggestion after save
      if (!suggestionDismissed && quoteContext !== 'diagnostic') {
        try {
          const sugRes = await axios.post(
            `${API_URL}/api/tickets/${id}/quote-suggestion`,
            { descriptions: validOptions.map(o => o.description) },
            { headers: getAuthHeaders() }
          );
          if (sugRes.data.should_suggest) {
            setContextSuggestion(sugRes.data);
          }
        } catch (err) { console.warn('quote-suggestion failed:', err?.message || err); }
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao guardar opções');
    } finally {
      setSavingOptions(false);
    }
  };

  // Context handlers
  const handleContextChange = async (newContext) => {
    setQuoteContext(newContext);
    setContextAutoDetected(false);
    try {
      await axios.put(
        `${API_URL}/api/tickets/${id}/quote-context`,
        { quote_context: newContext },
        { headers: getAuthHeaders() }
      );
    } catch (err) { console.warn('quote-context update failed:', err?.message || err); }
  };

  const handleSuggestionAccept = async () => {
    if (!contextSuggestion) return;
    setQuoteContext('diagnostic');
    setContextSuggestion(null);
    setSuggestionDismissed(true);
    try {
      await axios.put(`${API_URL}/api/tickets/${id}/quote-context`, { quote_context: 'diagnostic' }, { headers: getAuthHeaders() });
      await axios.post(`${API_URL}/api/tickets/${id}/quote-context-learn`, {
        user_action: 'accepted',
        descriptions: quoteOptions.filter(o => o.description).map(o => o.description),
        suggestion_score: contextSuggestion.score,
        signals: contextSuggestion.signals,
        suggested_context: 'diagnostic',
      }, { headers: getAuthHeaders() });
      toast.success('Contexto atualizado para diagnóstico');
    } catch (err) { console.warn('suggestion accept failed:', err?.message || err); }
  };

  const handleSuggestionIgnore = async () => {
    setContextSuggestion(null);
    setSuggestionDismissed(true);
    try {
      await axios.post(`${API_URL}/api/tickets/${id}/quote-context-learn`, {
        user_action: 'ignored',
        descriptions: quoteOptions.filter(o => o.description).map(o => o.description),
        suggestion_score: contextSuggestion?.score || 0,
        signals: contextSuggestion?.signals || [],
        suggested_context: 'diagnostic',
      }, { headers: getAuthHeaders() });
    } catch (err) { console.warn('suggestion ignore failed:', err?.message || err); }
  };


  const getQuoteOptionsTotal = () => {
    return quoteOptions.reduce((sum, o) => sum + (parseFloat(o.amount) || 0), 0);
  };

  // Check if quote is locked (sent to customer)
  const isQuoteLocked = ticket?.quote_locked_at && !ticket?.quote_decided_at;
  const isQuoteDecided = ticket?.quote_decided_at;
  const canEditQuote = !ticket?.quote_locked_at;

  const createNewQuoteVersion = async () => {
    if (!window.confirm('Criar nova versão do orçamento?\n\nIsto irá desbloquear o orçamento para edição e invalidar o link anterior.')) {
      return;
    }
    try {
      await axios.post(`${API_URL}/api/tickets/${id}/quote-new-version`, {}, { headers: getAuthHeaders() });
      toast.success('Nova versão criada - pode editar o orçamento');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar nova versão');
    }
  };

  // WhatsApp Helper Functions
  const normalizePhone = (phone) => {
    if (!phone) return null;
    // Remove spaces and +
    let normalized = phone.replace(/[\s+]/g, '');
    // If starts with 9 and has 9 digits, prepend 351 (Portugal)
    if (/^9\d{8}$/.test(normalized)) {
      normalized = '351' + normalized;
    }
    // If starts with 351, keep as is
    if (/^351\d{9}$/.test(normalized)) {
      return normalized;
    }
    // Otherwise invalid
    return null;
  };

  const getWhatsAppMessage = () => {
    const ticketCode = ticket?.ticket_number || 'N/A';
    // Check if there's a public quote link
    if (ticket?.quote_link_token && ticket?.quote_sent) {
      const frontendUrl = window.location.origin;
      const quoteLink = `${frontendUrl}/quote/${ticket.quote_link_token}`;
      return `PDPV - Ticket ${ticketCode}
O seu orçamento está pronto.

Pode escolher e aceitar aqui:
${quoteLink}

Qualquer dúvida responda a esta mensagem.`;
    }
    return `PDPV - Ticket ${ticketCode}
Respondemos ao seu pedido.

Qualquer dúvida estamos disponíveis.`;
  };

  const copyWhatsAppMessage = async () => {
    const message = getWhatsAppMessage();
    try {
      await navigator.clipboard.writeText(message);
      toast.success('Mensagem copiada!');
    } catch (err) {
      // Fallback for environments without clipboard permission
      const textarea = document.createElement('textarea');
      textarea.value = message;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      toast.success('Mensagem copiada!');
    }
  };

  const openWhatsApp = async () => {
    const phone = normalizePhone(ticket?.customer_phone);
    if (!phone) {
      toast.error('Número de telefone inválido');
      return;
    }
    const message = encodeURIComponent(getWhatsAppMessage());
    
    // Log to history
    try {
      await axios.post(
        `${API_URL}/api/tickets/${id}/notes`,
        { body: '📲 Mensagem enviada por WhatsApp (manual)' },
        { headers: getAuthHeaders() }
      );
      fetchData(); // Refresh to show new note
    } catch (err) {
      // Silent fail - don't block WhatsApp opening
      console.warn('WhatsApp note log failed:', err?.message || err);
    }
    
    window.open(`https://wa.me/${phone}?text=${message}`, '_blank');
  };

  const normalizedPhone = ticket ? normalizePhone(ticket.customer_phone) : null;

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!newMessage.trim()) return;
    
    setSendingMessage(true);
    try {
      await axios.post(
        `${API_URL}/api/tickets/${id}/messages`,
        { 
          body: newMessage, 
          channel: 'EMAIL',
          is_quote_response: isQuoteResponse,
          attachment_ids: messageAttachments.map(a => a.id)
        },
        { headers: getAuthHeaders() }
      );
      
      if (isQuoteResponse) {
        toast.success('Orçamento enviado - Estado alterado para "Aguarda Cliente"');
      } else {
        toast.success('Mensagem enviada');
      }
      
      setNewMessage('');
      setIsQuoteResponse(false);
      setMessageAttachments([]);
      fetchData();
    } catch (error) {
      toast.error('Erro ao enviar mensagem');
    } finally {
      setSendingMessage(false);
    }
  };

  const handleMessageFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingMessageFile(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await axios.post(
        `${API_URL}/api/tickets/${id}/attachments`,
        formData,
        { headers: { ...getAuthHeaders(), 'Content-Type': 'multipart/form-data' } }
      );
      
      setMessageAttachments(prev => [...prev, response.data]);
      toast.success('Anexo adicionado');
    } catch (error) {
      toast.error('Erro ao anexar ficheiro');
    } finally {
      setUploadingMessageFile(false);
      if (messageFileInputRef.current) messageFileInputRef.current.value = '';
    }
  };

  const removeMessageAttachment = (attachmentId) => {
    setMessageAttachments(prev => prev.filter(a => a.id !== attachmentId));
  };

  const addNote = async (e) => {
    e.preventDefault();
    if (!newNote.trim()) return;
    
    setSendingNote(true);
    try {
      await axios.post(
        `${API_URL}/api/tickets/${id}/notes`,
        { body: newNote },
        { headers: getAuthHeaders() }
      );
      toast.success('Nota adicionada');
      setNewNote('');
      fetchData();
    } catch (error) {
      toast.error('Erro ao adicionar nota');
    } finally {
      setSendingNote(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingFile(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      await axios.post(
        `${API_URL}/api/tickets/${id}/attachments`,
        formData,
        { headers: { ...getAuthHeaders(), 'Content-Type': 'multipart/form-data' } }
      );
      toast.success('Ficheiro enviado');
      fetchData();
    } catch (error) {
      toast.error('Erro ao enviar ficheiro');
    } finally {
      setUploadingFile(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const downloadFile = async (attachmentId, filename) => {
    try {
      const response = await axios.get(
        `${API_URL}/api/attachments/${attachmentId}/download`,
        { headers: getAuthHeaders(), responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      toast.error('Erro ao descarregar ficheiro');
    }
  };

  const resolveAlert = async (alertId) => {
    try {
      await axios.put(`${API_URL}/api/alerts/${alertId}/resolve`, {}, { headers: getAuthHeaders() });
      toast.success('Alerta resolvido');
      fetchData();
    } catch (error) {
      toast.error('Erro ao resolver alerta');
    }
  };

  const handleArchive = async () => {
    setArchiving(true);
    try {
      await axios.post(`${API_URL}/api/tickets/${id}/archive`, {}, { headers: getAuthHeaders() });
      toast.success('Ticket arquivado com sucesso');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao arquivar ticket');
    } finally {
      setArchiving(false);
    }
  };

  const handleRestore = async () => {
    setArchiving(true);
    try {
      await axios.post(`${API_URL}/api/tickets/${id}/restore`, {}, { headers: getAuthHeaders() });
      toast.success('Ticket restaurado com sucesso');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao restaurar ticket');
    } finally {
      setArchiving(false);
    }
  };

  const canArchive = user?.role === 'ADMIN' || user?.role === 'SUPERVISOR';

  // Filter out automatic statuses (is_auto: true) from manual selection
  const statusOptions = allStatuses
    .filter(s => !s.is_auto)
    .map(s => ({ value: s.code, label: s.label, color: s.color }));

  // Build status class map dynamically
  const getStatusClass = (status) => {
    const statusObj = allStatuses.find(s => s.code === status);
    if (statusObj) {
      // Return inline style-compatible color
      return `bg-opacity-20 border`;
    }
    const defaultClasses = {
      ABERTO: 'status-aberto',
      EM_TRATAMENTO: 'status-em-tratamento',
      AGUARDA_CLIENTE: 'status-aguarda-cliente',
      FECHADO: 'status-fechado',
      ACEITE_LINK: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      REJEITADO_LINK: 'bg-red-100 text-red-800 border-red-300',
      AGENDADO: 'bg-purple-100 text-purple-800 border-purple-300'
    };
    return defaultClasses[status] || 'bg-zinc-100 text-zinc-700';
  };

  const getStatusLabel = (status) => {
    const statusObj = allStatuses.find(s => s.code === status);
    if (statusObj) return statusObj.label;
    // Fallback labels for known statuses
    const fallbackLabels = {
      ABERTO: 'Aberto',
      EM_TRATAMENTO: 'Em Tratamento',
      AGUARDA_CLIENTE: 'Aguarda Cliente',
      ACEITE_LINK: 'Aceite (Link)',
      REJEITADO_LINK: 'Rejeitado (Link)',
      AGENDADO: 'Agendado',
      FECHADO: 'Fechado'
    };
    return fallbackLabels[status] || status;
  };

  const getStatusColor = (status) => {
    const statusObj = allStatuses.find(s => s.code === status);
    if (statusObj) return statusObj.color;
    // Fallback colors for known statuses
    const fallbackColors = {
      ABERTO: '#22c55e',
      EM_TRATAMENTO: '#3b82f6',
      AGUARDA_CLIENTE: '#f59e0b',
      ACEITE_LINK: '#10b981',
      REJEITADO_LINK: '#ef4444',
      AGENDADO: '#8b5cf6',
      FECHADO: '#6b7280'
    };
    return fallbackColors[status] || '#6b7280';
  };

  const typeLabels = {
    ORCAMENTO_PNEUS: 'Orçamento Pneus',
    ORCAMENTO_MECANICA: 'Orçamento Mecânica',
    MARCACAO: 'Marcação',
    INFORMACAO: 'Informação',
    INTERNO: 'Interno',
    RECLAMACAO: 'Reclamação'
  };

  const channelLabels = {
    TELEFONE: 'Telefone',
    BALCAO: 'Balcão',
    FORMULARIO: 'Formulário',
    EMAIL: 'Email',
    WHATSAPP: 'WhatsApp',
    TELEGRAM: 'Telegram'
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-12 h-12 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!ticket) return null;

  // Check if user can edit (normal permissions OR creator within 5 min)
  const canEdit = ['ADMIN', 'SUPERVISOR'].includes(user?.role) || 
    (user?.role === 'AGENT' && ticket.assigned_to_user_id === user.id) ||
    ticket.creator_can_edit;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <Button 
            variant="ghost" 
            onClick={() => navigate('/tickets')}
            className="mb-2"
            data-testid="back-to-tickets-btn"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Voltar
          </Button>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-3xl font-black text-slate-900 tracking-tight font-mono">
              {ticket.ticket_number}
            </h1>
            {ticket.creator_can_edit && (
              <Badge className="bg-blue-100 text-blue-700 text-sm">
                <Clock className="h-4 w-4 mr-1" />
                Pode editar (5 min)
              </Badge>
            )}
            {ticket.is_overdue && (
              <Badge className="sla-overdue text-sm">
                <AlertTriangle className="h-4 w-4 mr-1" />
                SLA Atrasado
              </Badge>
            )}
            {ticket.priority === 'URGENTE' && (
              <Badge className="priority-urgente text-sm">URGENTE</Badge>
            )}
          </div>
          <p className="text-zinc-500 mt-1">
            Criado em {formatDate(ticket.created_at)}
            {ticket.created_by_name && (
              <span className="ml-2">por <span className="font-medium text-zinc-600">{ticket.created_by_name}</span></span>
            )}
          </p>
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Status */}
          {canEdit ? (
            // Check if current status is automatic (set by system, like ACEITE_LINK)
            allStatuses.find(s => s.code === ticket.status)?.is_auto ? (
              // Show badge for automatic statuses + dropdown to change to next logical status
              <div className="flex items-center gap-2">
                <Badge 
                  className="text-sm py-2 px-4 font-semibold"
                  style={{ 
                    backgroundColor: `${getStatusColor(ticket.status)}20`, 
                    color: getStatusColor(ticket.status),
                    borderColor: getStatusColor(ticket.status)
                  }}
                  data-testid="status-badge-auto"
                >
                  {getStatusLabel(ticket.status)}
                </Badge>
                <Select
                  value=""
                  onValueChange={(value) => updateTicket({ status: value })}
                >
                  <SelectTrigger className="h-10 w-40 font-semibold border-dashed" data-testid="status-change-select">
                    <span className="text-zinc-500 text-sm">Alterar para...</span>
                  </SelectTrigger>
                  <SelectContent>
                    {statusOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <Select
                value={ticket.status}
                onValueChange={(value) => updateTicket({ status: value })}
              >
                <SelectTrigger className={`h-10 w-44 font-semibold ${getStatusClass(ticket.status)}`} data-testid="status-select">
                  <SelectValue placeholder={getStatusLabel(ticket.status)} />
                </SelectTrigger>
                <SelectContent>
                  {statusOptions.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )
          ) : (
            <Badge 
              className="text-sm py-2 px-4"
              style={{ 
                backgroundColor: `${getStatusColor(ticket.status)}20`, 
                color: getStatusColor(ticket.status),
                borderColor: getStatusColor(ticket.status)
              }}
            >
              {getStatusLabel(ticket.status)}
            </Badge>
          )}

          {/* Assign - Different UI for agents vs admin/supervisor */}
          {['ADMIN', 'SUPERVISOR'].includes(user?.role) && (
            <Select
              value={ticket.assigned_to_user_id || 'none'}
              onValueChange={(value) => updateTicket({ assigned_to_user_id: value === 'none' ? '' : value })}
            >
              <SelectTrigger className="h-10 w-40" data-testid="assign-select">
                <SelectValue placeholder="Atribuir a..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Ninguém</SelectItem>
                {users.map(u => (
                  <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          
          {/* Agent self-assign button - only show when ticket is unassigned */}
          {user?.role === 'AGENT' && !ticket.assigned_to_user_id && (
            <Button
              variant="outline"
              className="h-10 border-blue-400 text-blue-700 hover:bg-blue-50"
              onClick={() => updateTicket({ assigned_to_user_id: user.id })}
              data-testid="self-assign-btn"
            >
              <User className="h-4 w-4 mr-2" />
              Atribuir a mim
            </Button>
          )}

          {/* Edit Button */}
          {canEdit && !ticket.archived_at && (
            <Button
              variant="outline"
              className="h-10 border-blue-400 text-blue-700 hover:bg-blue-50"
              onClick={openEditDialog}
              data-testid="edit-ticket-btn"
            >
              <Pencil className="h-4 w-4 mr-2" />
              Editar
            </Button>
          )}

          {/* Archive/Restore Button */}
          {canArchive && (
            ticket.archived_at ? (
              <Button
                variant="outline"
                className="h-10 border-emerald-400 text-emerald-700 hover:bg-emerald-50"
                onClick={handleRestore}
                disabled={archiving}
                data-testid="restore-ticket-btn"
              >
                {archiving ? (
                  <div className="w-4 h-4 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin mr-2" />
                ) : (
                  <RotateCcw className="h-4 w-4 mr-2" />
                )}
                Restaurar
              </Button>
            ) : (
              <Button
                variant="outline"
                className="h-10 border-zinc-300 text-zinc-600 hover:bg-zinc-50"
                onClick={handleArchive}
                disabled={archiving}
                data-testid="archive-ticket-btn"
              >
                {archiving ? (
                  <div className="w-4 h-4 border-2 border-zinc-600 border-t-transparent rounded-full animate-spin mr-2" />
                ) : (
                  <Archive className="h-4 w-4 mr-2" />
                )}
                Arquivar
              </Button>
            )
          )}
        </div>
      </div>

      {/* Archived Banner */}
      {ticket.archived_at && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center gap-3">
          <Archive className="h-5 w-5 text-amber-600" />
          <div>
            <p className="font-semibold text-amber-800">Ticket Arquivado</p>
            <p className="text-sm text-amber-600">Arquivado em {formatDate(ticket.archived_at)}</p>
          </div>
        </div>
      )}

      {/* Aviso financeiro genérico (sem valores) */}
      <CreditWarningBanner phone={ticket.customer_phone} />

      {/* Customer Info Card */}
      <Card>
        <CardContent className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-zinc-100 rounded-lg flex items-center justify-center">
                <User className="h-5 w-5 text-zinc-600" />
              </div>
              <div>
                <p className="text-xs text-zinc-500 font-medium uppercase">Cliente</p>
                <p className="font-semibold text-slate-900">{ticket.customer_name}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-zinc-100 rounded-lg flex items-center justify-center">
                <Phone className="h-5 w-5 text-zinc-600" />
              </div>
              <div className="flex-1">
                <p className="text-xs text-zinc-500 font-medium uppercase">Telefone</p>
                <p className="font-semibold text-slate-900">{ticket.customer_phone}</p>
              </div>
              {normalizedPhone && (
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={copyWhatsAppMessage}
                    className="h-8 px-2 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                    title="Copiar mensagem WhatsApp"
                    data-testid="copy-whatsapp-btn"
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={openWhatsApp}
                    className="h-8 px-2 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                    title="Abrir WhatsApp"
                    data-testid="open-whatsapp-btn"
                  >
                    <MessageSquare className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
            {ticket.customer_email && (
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-zinc-100 rounded-lg flex items-center justify-center">
                  <Mail className="h-5 w-5 text-zinc-600" />
                </div>
                <div>
                  <p className="text-xs text-zinc-500 font-medium uppercase">Email</p>
                  <p className="font-semibold text-slate-900">{ticket.customer_email}</p>
                </div>
              </div>
            )}
            {ticket.vehicle_plate && (
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-zinc-100 rounded-lg flex items-center justify-center">
                  <Car className="h-5 w-5 text-zinc-600" />
                </div>
                <div>
                  <p className="text-xs text-zinc-500 font-medium uppercase">Matrícula</p>
                  <p className="font-semibold text-slate-900 font-mono">{ticket.vehicle_plate}</p>
                </div>
              </div>
            )}
          </div>
          {/* Type, Channel, Assigned */}
          <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t">
            <Badge variant="outline">{typeLabels[ticket.type]}</Badge>
            <Badge variant="outline">{channelLabels[ticket.channel]}</Badge>
            {ticket.assigned_to_name && (
              <Badge variant="outline">Atribuído: {ticket.assigned_to_name}</Badge>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Description */}
      {ticket.description && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Descrição</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-slate-700 whitespace-pre-wrap">{ticket.description}</p>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <Tabs defaultValue="conversa" className="space-y-4">
        <TabsList className="bg-zinc-100 p-1">
          <TabsTrigger value="conversa" className="data-[state=active]:bg-white" data-testid="tab-conversa">
            <MessageSquare className="h-4 w-4 mr-2" />
            Conversa
          </TabsTrigger>
          {ticket?.customer_phone && (
            <TabsTrigger value="whatsapp" className="data-[state=active]:bg-white" data-testid="tab-whatsapp">
              <MessageCircle className="h-4 w-4 mr-2" />
              WhatsApp
            </TabsTrigger>
          )}
          <TabsTrigger value="documentos" className="data-[state=active]:bg-white" data-testid="tab-documentos">
            <FileText className="h-4 w-4 mr-2" />
            Documentos
          </TabsTrigger>
          <TabsTrigger value="slas" className="data-[state=active]:bg-white" data-testid="tab-slas">
            <AlertTriangle className="h-4 w-4 mr-2" />
            SLAs/Alertas
            {alerts.filter(a => !a.is_resolved).length > 0 && (
              <Badge className="ml-2 bg-red-100 text-red-700">{alerts.filter(a => !a.is_resolved).length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="historico" className="data-[state=active]:bg-white" data-testid="tab-historico">
            <History className="h-4 w-4 mr-2" />
            Histórico
          </TabsTrigger>
        </TabsList>

        {/* Conversa Tab */}
        <TabsContent value="conversa" className="space-y-4">
          {/* Messages Timeline */}
          <Card>
            <CardHeader className="border-b">
              <CardTitle className="text-lg">Mensagens</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-[400px]">
                {messages.length === 0 ? (
                  <div className="p-8 text-center text-zinc-500">
                    Nenhuma mensagem
                  </div>
                ) : (
                  <div className="divide-y">
                    {messages.map((msg) => (
                      <div 
                        key={msg.id} 
                        className={`p-4 ${msg.direction === 'INBOUND' ? 'bg-blue-50/50' : 'bg-zinc-50/50'}`}
                      >
                        <div className="flex items-start gap-3">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold ${
                            msg.direction === 'INBOUND' ? 'bg-blue-600' : 'bg-orange-600'
                          }`}>
                            {msg.direction === 'INBOUND' ? 'C' : 'A'}
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-semibold text-sm">
                                {msg.direction === 'INBOUND' ? ticket.customer_name : (msg.created_by_name || 'Sistema')}
                              </span>
                              <Badge variant="outline" className="text-xs">
                                {msg.channel}
                              </Badge>
                              {msg.from_customer && (
                                <Badge className="text-xs bg-blue-100 text-blue-700 border-0">
                                  Via Portal
                                </Badge>
                              )}
                              <span className="text-xs text-zinc-500">
                                {formatDate(msg.created_at)}
                              </span>
                            </div>
                            <p className="text-slate-700 whitespace-pre-wrap">{msg.body}</p>
                            
                            {/* Message Attachments */}
                            {msg.attachment_ids && msg.attachment_ids.length > 0 && (
                              <div className="mt-3 flex flex-wrap gap-2">
                                {msg.attachment_ids.map((attachId) => {
                                  const att = attachments.find(a => a.id === attachId);
                                  if (!att) return null;
                                  
                                  const isImage = att.file_type?.startsWith('image/');
                                  const isPdf = att.file_type === 'application/pdf';
                                  
                                  return (
                                    <div 
                                      key={attachId}
                                      className="flex items-center gap-2 bg-white border border-zinc-200 rounded-lg p-2 hover:border-orange-300 transition-colors cursor-pointer group"
                                      onClick={() => downloadFile(attachId, att.original_filename)}
                                      data-testid={`msg-attachment-${attachId}`}
                                    >
                                      {isImage && attachmentUrls[attachId] ? (
                                        <div className="w-10 h-10 rounded overflow-hidden bg-zinc-100">
                                          <img 
                                            src={attachmentUrls[attachId]} 
                                            alt={att.original_filename}
                                            className="w-full h-full object-cover"
                                            onError={(e) => { e.target.style.display = 'none'; }}
                                          />
                                        </div>
                                      ) : (
                                        <div className={`w-10 h-10 rounded flex items-center justify-center ${isPdf ? 'bg-red-100' : 'bg-zinc-100'}`}>
                                          <FileText className={`h-5 w-5 ${isPdf ? 'text-red-600' : 'text-zinc-600'}`} />
                                        </div>
                                      )}
                                      <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-slate-700 truncate max-w-[150px]">
                                          {att.original_filename}
                                        </p>
                                        <p className="text-xs text-zinc-500">
                                          {(att.file_size / 1024).toFixed(1)} KB
                                        </p>
                                      </div>
                                      <Download className="h-4 w-4 text-zinc-400 group-hover:text-orange-600" />
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Reply Form */}
          {canEdit && (
            <Card>
              <CardHeader className="border-b pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Send className="h-5 w-5 text-orange-600" />
                  Responder por Email
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4">
                {/* Quote Options Section */}
                <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-lg space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="h-5 w-5 text-amber-600" />
                      <span className="font-semibold text-amber-800">Opções de Orçamento</span>
                      {ticket.quote_locked_at && (
                        <span className={`text-xs px-2 py-0.5 rounded ${isQuoteDecided ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-200 text-zinc-600'}`}>
                          {isQuoteDecided ? `${ticket.quote_decision === 'ACCEPTED' ? '✓ Aceite' : '✗ Recusado'}` : '🔒 Bloqueado'}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {ticket.quote_locked_at && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={createNewQuoteVersion}
                          className="border-amber-400 text-amber-700 hover:bg-amber-100 text-xs"
                          data-testid="new-quote-version-btn"
                        >
                          <RefreshCcw className="h-3 w-3 mr-1" />
                          Nova Versão
                        </Button>
                      )}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowPreviews(p => !p)}
                        className={`text-xs ${showPreviews ? 'text-blue-600 bg-blue-50' : 'text-zinc-500'}`}
                        data-testid="toggle-preview-btn"
                      >
                        <Eye className="h-3 w-3 mr-1" />
                        {showPreviews ? 'Preview ON' : 'Preview OFF'}
                      </Button>
                      <Checkbox
                        id="quote_sent_conv"
                        checked={ticket.quote_sent}
                        onCheckedChange={(checked) => updateTicket({ quote_sent: checked })}
                        data-testid="quote-sent-checkbox-conv"
                        disabled={!canEditQuote}
                      />
                      <Label htmlFor="quote_sent_conv" className="text-sm text-amber-700">
                        Enviado
                      </Label>
                    </div>
                  </div>
                  
                  {/* Context Selector */}
                  {canEditQuote && (
                    <div className="flex items-center gap-4 py-2 px-1" data-testid="quote-context-selector">
                      <span className="text-xs font-semibold text-zinc-500">Contexto:</span>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="radio"
                          name="quoteContext"
                          checked={quoteContext === 'customer_request'}
                          onChange={() => handleContextChange('customer_request')}
                          className="accent-amber-600 w-3.5 h-3.5"
                          data-testid="context-customer-request"
                        />
                        <span className="text-xs text-zinc-700">Pedido do cliente</span>
                      </label>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="radio"
                          name="quoteContext"
                          checked={quoteContext === 'diagnostic'}
                          onChange={() => handleContextChange('diagnostic')}
                          className="accent-amber-600 w-3.5 h-3.5"
                          data-testid="context-diagnostic"
                        />
                        <span className="text-xs text-zinc-700">Diagnóstico da oficina</span>
                      </label>
                    </div>
                  )}
                  {!canEditQuote && (
                    <p className="text-xs text-zinc-400 px-1 pb-1">
                      Contexto: {quoteContext === 'diagnostic' ? 'Diagnóstico da oficina' : quoteContext === 'customer_request' ? 'Pedido do cliente' : 'Não definido'}
                    </p>
                  )}

                  {/* Suggestion Banner */}
                  {contextSuggestion && !suggestionDismissed && (
                    <div className="flex items-center gap-3 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm" data-testid="context-suggestion-banner">
                      <AlertCircle className="h-4 w-4 text-blue-600 shrink-0" />
                      <span className="text-blue-800 flex-1">Este orçamento pode resultar de verificação do veículo</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-blue-700 hover:bg-blue-100 h-7 px-2"
                        onClick={handleSuggestionAccept}
                        data-testid="suggestion-accept-btn"
                      >
                        Marcar como diagnóstico
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-zinc-500 hover:bg-zinc-100 h-7 px-2"
                        onClick={handleSuggestionIgnore}
                        data-testid="suggestion-ignore-btn"
                      >
                        Ignorar
                      </Button>
                    </div>
                  )}

                  {/* Quote Options List */}
                  <div className="space-y-2">
                    {quoteOptions.map((option, index) => (
                      <div key={option.id || index} className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-amber-700 font-medium text-sm w-6">{index + 1}.</span>
                          <Input
                            placeholder="Descrição (ex: Revisão completa)"
                            value={option.description}
                            onChange={(e) => updateQuoteOption(index, 'description', e.target.value)}
                            className={`flex-1 border-amber-300 focus:border-amber-500 text-sm ${!canEditQuote ? 'bg-zinc-100' : ''}`}
                            data-testid={`quote-option-desc-${index}`}
                            readOnly={!canEditQuote}
                            disabled={!canEditQuote}
                          />
                          <div className="flex items-center gap-1">
                            <Input
                              type="number"
                              step="0.01"
                              placeholder="0.00"
                              value={option.amount}
                              onChange={(e) => updateQuoteOption(index, 'amount', e.target.value)}
                              className={`w-24 border-amber-300 focus:border-amber-500 text-sm ${!canEditQuote ? 'bg-zinc-100' : ''}`}
                              data-testid={`quote-option-amount-${index}`}
                              readOnly={!canEditQuote}
                              disabled={!canEditQuote}
                            />
                            <span className="text-amber-700 text-sm">€</span>
                          </div>
                          {option.is_accepted && (
                            <CheckCircle className="h-4 w-4 text-emerald-600" title="Aceite pelo cliente" />
                          )}
                          {canEditQuote && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => removeQuoteOption(index)}
                              className="h-8 w-8 p-0 text-red-500 hover:text-red-700 hover:bg-red-50"
                              disabled={quoteOptions.length <= 1}
                              data-testid={`quote-option-remove-${index}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                        {/* Client Preview / Suggestion */}
                        {showPreviews && optionPreviews[index] && option.description?.trim().length >= 2 && suggestionStates[index]?.mode !== 'ignored' && (
                          <div className="ml-6 mt-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2" data-testid={`quote-preview-${index}`}>
                            <div className="flex items-center justify-between mb-1">
                              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Sugestão automática</p>
                              {suggestionStates[index]?.mode !== 'editing' && suggestionStates[index]?.mode !== 'edited' && (
                                <div className="flex gap-1">
                                  <button onClick={() => startEditSuggestion(index)}
                                    className="text-[10px] text-blue-600 hover:text-blue-800 font-medium px-1.5 py-0.5 rounded hover:bg-blue-50"
                                    data-testid={`suggestion-edit-${index}`}>
                                    Editar
                                  </button>
                                  <button onClick={() => ignoreSuggestion(index)}
                                    className="text-[10px] text-zinc-400 hover:text-zinc-600 font-medium px-1.5 py-0.5 rounded hover:bg-zinc-100"
                                    data-testid={`suggestion-ignore-${index}`}>
                                    Ignorar
                                  </button>
                                </div>
                              )}
                            </div>
                            {suggestionStates[index]?.mode === 'editing' ? (
                              <div className="flex gap-2 items-center">
                                <input
                                  value={suggestionStates[index]?.editText || ''}
                                  onChange={e => updateSuggestionEdit(index, e.target.value)}
                                  className="flex-1 text-sm border border-slate-300 rounded px-2 py-1 bg-white"
                                  data-testid={`suggestion-edit-input-${index}`}
                                />
                                <button onClick={() => saveSuggestionEdit(index)}
                                  className="text-[11px] text-emerald-600 hover:text-emerald-800 font-semibold px-2 py-1 rounded hover:bg-emerald-50"
                                  data-testid={`suggestion-save-edit-${index}`}>
                                  OK
                                </button>
                              </div>
                            ) : suggestionStates[index]?.mode === 'edited' ? (
                              <p className="text-sm font-medium text-slate-700">{suggestionStates[index]?.editText}</p>
                            ) : (
                              <p className="text-sm font-medium text-slate-700">{optionPreviews[index].title}</p>
                            )}
                            {suggestionStates[index]?.mode !== 'editing' && (
                              <>
                                {optionPreviews[index].type === 'package' && optionPreviews[index].includes?.length > 1 && (
                                  <p className="text-xs text-slate-500 mt-0.5">Inclui: {optionPreviews[index].includes.join(' + ')}</p>
                                )}
                                <div className="flex items-center gap-2 mt-1 flex-wrap">
                                  {optionPreviews[index].recommended && (
                                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Recomendado</span>
                                  )}
                                  {optionPreviews[index].brand_tier && (
                                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-full ${
                                      optionPreviews[index].brand_tier === 'premium' ? 'bg-violet-100 text-violet-700'
                                      : optionPreviews[index].brand_tier === 'mid' ? 'bg-blue-100 text-blue-700'
                                      : 'bg-zinc-100 text-zinc-600'
                                    }`}>{optionPreviews[index].brand_tier}</span>
                                  )}
                                  {optionPreviews[index].priority !== 'normal' && (
                                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-full ${
                                      optionPreviews[index].priority === 'critical' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                                    }`}>{optionPreviews[index].priority === 'critical' ? 'Urgente' : 'Seguranca'}</span>
                                  )}
                                </div>
                                {optionPreviews[index].priority_message && (
                                  <p className={`text-[11px] mt-1 ${
                                    optionPreviews[index].priority === 'critical' ? 'text-red-500'
                                    : optionPreviews[index].priority === 'safety' ? 'text-amber-500'
                                    : 'text-emerald-500'
                                  }`}>{optionPreviews[index].priority_message}</p>
                                )}
                              </>
                            )}
                          </div>
                        )}
                        {/* Ignored indicator */}
                        {showPreviews && suggestionStates[index]?.mode === 'ignored' && option.description?.trim().length >= 2 && (
                          <p className="ml-6 mt-1 text-[11px] text-zinc-400 italic">Sugestão ignorada — texto original será usado</p>
                        )}
                        {/* PDFs section - show both available PDFs and already linked PDFs */}
                        {canEditQuote && (
                          <div className="ml-6 space-y-1">
                            {/* Already linked PDFs with remove button */}
                            {(option.attachment_ids || []).length > 0 && (
                              <div className="flex flex-wrap gap-2 items-center">
                                <span className="text-xs text-zinc-400">Anexados:</span>
                                {(option.attachment_ids || []).map(attId => {
                                  const att = attachments.find(a => a.id === attId);
                                  const filename = att?.original_filename || `PDF ${attId.slice(0,8)}...`;
                                  return (
                                    <div key={attId} className="flex items-center gap-1 bg-amber-50 border border-amber-200 rounded px-2 py-0.5">
                                      <FileText className="h-3 w-3 text-red-400" />
                                      <span className="text-xs text-amber-800">{filename}</span>
                                      <button
                                        type="button"
                                        onClick={() => {
                                          const updated = (option.attachment_ids || []).filter(id => id !== attId);
                                          updateQuoteOption(index, 'attachment_ids', updated);
                                        }}
                                        className="ml-1 text-red-400 hover:text-red-600 hover:bg-red-100 rounded p-0.5"
                                        title="Remover PDF"
                                        data-testid={`pdf-remove-${index}-${attId}`}
                                      >
                                        <X className="h-3 w-3" />
                                      </button>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                            {/* Available PDFs to add (not already linked) */}
                            {attachments.filter(a => 
                              (a.file_type?.includes('pdf') || a.original_filename?.toLowerCase().endsWith('.pdf')) &&
                              !(option.attachment_ids || []).includes(a.id)
                            ).length > 0 && (
                              <div className="flex flex-wrap gap-2 items-center">
                                <span className="text-xs text-zinc-400">Adicionar:</span>
                                {attachments.filter(a => 
                                  (a.file_type?.includes('pdf') || a.original_filename?.toLowerCase().endsWith('.pdf')) &&
                                  !(option.attachment_ids || []).includes(a.id)
                                ).map(att => (
                                  <button
                                    key={att.id}
                                    type="button"
                                    onClick={() => {
                                      const updated = [...(option.attachment_ids || []), att.id];
                                      updateQuoteOption(index, 'attachment_ids', updated);
                                    }}
                                    className="flex items-center gap-1 text-xs text-zinc-500 hover:text-amber-700 hover:bg-amber-50 rounded px-2 py-0.5 border border-dashed border-zinc-300 hover:border-amber-400"
                                    title="Adicionar PDF"
                                    data-testid={`pdf-add-${index}-${att.id}`}
                                  >
                                    <Plus className="h-3 w-3" />
                                    <FileText className="h-3 w-3 text-red-400" />
                                    {att.original_filename}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                  
                  {/* Add Option & Total */}
                  <div className="flex items-center justify-between pt-2 border-t border-amber-200">
                    {canEditQuote ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={addQuoteOption}
                        className="border-amber-400 text-amber-700 hover:bg-amber-100"
                        disabled={quoteOptions.length >= 10}
                        data-testid="add-quote-option-btn"
                      >
                        <Plus className="h-4 w-4 mr-1" />
                        Adicionar Opção
                      </Button>
                    ) : (
                      <span className="text-xs text-zinc-500">🔒 Orçamento bloqueado para edição</span>
                    )}
                    <div className="flex items-center gap-3">
                      <span className="text-amber-800 font-semibold">
                        Total: {getQuoteOptionsTotal().toFixed(2)}€
                      </span>
                      {canEditQuote && (
                        <Button
                          type="button"
                          size="sm"
                          onClick={saveQuoteOptions}
                          disabled={savingOptions}
                          className="bg-amber-600 hover:bg-amber-700 text-white"
                          data-testid="save-quote-options-btn"
                        >
                          {savingOptions ? (
                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          ) : (
                            'Guardar'
                          )}
                        </Button>
                      )}
                    </div>
                  </div>
                  
                  {/* Generate Link Button */}
                  {getQuoteOptionsTotal() > 0 && (
                    <div className="pt-2 border-t border-amber-200">
                      <QuoteLinkSection ticketId={id} getAuthHeaders={getAuthHeaders} compact={false} />
                    </div>
                  )}
                  
                  {/* Quote Response Status */}
                  {ticket.quote_response_status && (
                    <div className={`flex items-center gap-2 p-3 rounded ${
                      ticket.quote_response_status === 'ACCEPTED' 
                        ? 'bg-emerald-100 text-emerald-700' 
                        : 'bg-red-100 text-red-700'
                    }`}>
                      {ticket.quote_response_status === 'ACCEPTED' ? (
                        <CheckCircle className="h-5 w-5" />
                      ) : (
                        <XCircle className="h-5 w-5" />
                      )}
                      <div className="flex-1">
                        <span className="font-medium">
                          {ticket.quote_response_status === 'ACCEPTED' ? 'Aceite' : 'Recusado'} pelo Cliente
                        </span>
                        {ticket.quote_response_at && (
                          <span className="text-sm ml-2">• {formatDate(ticket.quote_response_at)}</span>
                        )}
                        {ticket.accepted_total && (
                          <div className="text-sm mt-1">
                            Total aceite: <strong>{ticket.accepted_total.toFixed(2)}€</strong>
                            {ticket.accepted_count && ` (${ticket.accepted_count} de ${quoteOptions.length} opções)`}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {/* Rejection Reason Details */}
                  {ticket.quote_response_status === 'REJECTED' && ticket.rejection_reason_code && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mt-2" data-testid="rejection-reason-card">
                      <h4 className="font-medium text-red-800 flex items-center gap-2 mb-2">
                        <AlertCircle className="h-4 w-4" />
                        Motivo da Rejeição
                      </h4>
                      <div className="space-y-1 text-sm">
                        <p className="text-red-700">
                          <span className="font-medium">Motivo:</span> {ticket.rejection_reason_label || ticket.rejection_reason_code}
                        </p>
                        {ticket.rejection_reason_note && (
                          <p className="text-red-600">
                            <span className="font-medium">Observação:</span> {ticket.rejection_reason_note}
                          </p>
                        )}
                        {ticket.rejected_at && (
                          <p className="text-red-500 text-xs mt-2">
                            Rejeitado em {formatDate(ticket.rejected_at)} via {ticket.rejected_via === 'link' ? 'link do cliente' : ticket.rejected_via}
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Acceptance Intent Details */}
                  {ticket.quote_response_status === 'ACCEPTED' && ticket.acceptance_intent && (
                    <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 mt-2" data-testid="acceptance-intent-card">
                      <h4 className="font-medium text-emerald-800 flex items-center gap-2 mb-2">
                        <CheckCircle className="h-4 w-4" />
                        Intenção do Cliente
                      </h4>
                      <div className="space-y-1 text-sm">
                        <p className="text-emerald-700">
                          <span className="font-medium">
                            {ticket.acceptance_intent === 'agendar' && '📅 '}
                            {ticket.acceptance_intent === 'avancar' && '🔧 '}
                            {ticket.acceptance_intent === 'contactar' && '📞 '}
                          </span>
                          {ticket.acceptance_intent_label || ticket.acceptance_intent}
                        </p>
                        {ticket.acceptance_intent === 'agendar' && ticket.preferred_date && (
                          <p className="text-emerald-700 font-semibold">
                            Data pretendida: {new Date(ticket.preferred_date + 'T00:00:00').toLocaleDateString('pt-PT')}
                            {ticket.preferred_period && (
                              <span className="ml-1">
                                ({ticket.preferred_period === 'manha' ? 'Manhã' : 'Tarde'})
                              </span>
                            )}
                          </p>
                        )}
                        {ticket.quote_response_at && (
                          <p className="text-emerald-500 text-xs mt-2">
                            Aceite em {formatDate(ticket.quote_response_at)} via link do cliente
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <form onSubmit={sendMessage} className="space-y-4">
                  <Textarea
                    placeholder="Escreva a sua resposta..."
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    className="min-h-[100px] border-2 focus:border-orange-500"
                    data-testid="message-input"
                  />
                  
                  {/* Attachments section */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="file"
                        ref={messageFileInputRef}
                        onChange={handleMessageFileUpload}
                        className="hidden"
                        accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => messageFileInputRef.current?.click()}
                        disabled={uploadingMessageFile}
                        className="border-zinc-300"
                      >
                        {uploadingMessageFile ? (
                          <div className="w-4 h-4 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin mr-2" />
                        ) : (
                          <Paperclip className="h-4 w-4 mr-2" />
                        )}
                        Anexar Ficheiro
                      </Button>
                      <span className="text-xs text-zinc-500">
                        PDF, Word, Excel, Imagens
                      </span>
                    </div>
                    
                    {/* List of attached files */}
                    {messageAttachments.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {messageAttachments.map((att) => (
                          <div 
                            key={att.id}
                            className="flex items-center gap-2 bg-zinc-100 px-3 py-1.5 rounded-full text-sm"
                          >
                            <FileText className="h-3 w-3 text-zinc-500" />
                            <span className="max-w-[150px] truncate">{att.original_name}</span>
                            <button
                              type="button"
                              onClick={() => removeMessageAttachment(att.id)}
                              className="text-zinc-400 hover:text-red-500"
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  
                  {/* Quote response checkbox */}
                  <div className="flex items-center space-x-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                    <Checkbox
                      id="quote-response"
                      checked={isQuoteResponse}
                      onCheckedChange={(checked) => setIsQuoteResponse(checked)}
                      data-testid="quote-response-checkbox"
                    />
                    <Label 
                      htmlFor="quote-response" 
                      className="text-sm font-medium text-amber-800 cursor-pointer"
                    >
                      Esta é uma resposta de orçamento (altera o estado para "Aguarda Cliente")
                    </Label>
                  </div>
                  
                  <div className="flex justify-end">
                    <Button 
                      type="submit" 
                      className="h-12 px-6 font-bold bg-orange-600 hover:bg-orange-700"
                      disabled={sendingMessage || !newMessage.trim()}
                      data-testid="send-message-btn"
                    >
                      {sendingMessage ? (
                        <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <>
                          <Send className="h-4 w-4 mr-2" />
                          {isQuoteResponse ? 'Enviar Orçamento' : 'Enviar Email'}
                        </>
                      )}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          )}

          {/* Internal Note Form */}
          {canEdit && (
            <Card>
              <CardHeader className="border-b pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <StickyNote className="h-5 w-5 text-amber-600" />
                  Nota Interna
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4">
                <form onSubmit={addNote} className="space-y-4">
                  <Textarea
                    placeholder="Adicione uma nota interna (não visível para o cliente)..."
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    className="min-h-[80px] border-2 focus:border-amber-500"
                    data-testid="note-input"
                  />
                  <div className="flex justify-end">
                    <Button 
                      type="submit" 
                      variant="outline"
                      className="h-10 border-2 border-amber-500 text-amber-700 hover:bg-amber-50"
                      disabled={sendingNote || !newNote.trim()}
                      data-testid="add-note-btn"
                    >
                      {sendingNote ? (
                        <div className="w-4 h-4 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <>
                          <StickyNote className="h-4 w-4 mr-2" />
                          Adicionar Nota
                        </>
                      )}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          )}

          {/* Quick Actions Section - Reminders & Reply Link */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Reminders */}
            <RemindersSection 
              ticketId={id} 
              getAuthHeaders={getAuthHeaders} 
              users={users} 
              currentUser={user} 
            />

            {/* Reply Link */}
            {canEdit && (
              <ReplyLinkSection
                ticketId={id}
                getAuthHeaders={getAuthHeaders}
                existingToken={ticket?.reply_link_token || null}
              />
            )}
          </div>
        </TabsContent>

        {/* WhatsApp Tab */}
        {ticket?.customer_phone && (
          <TabsContent value="whatsapp" className="space-y-4">
            <WhatsAppPanel ticketId={id} ticket={ticket} />
          </TabsContent>
        )}

        {/* Documentos Tab */}
        <TabsContent value="documentos" className="space-y-4">
          {/* Quote History */}
          <QuoteHistorySection ticketId={id} getAuthHeaders={getAuthHeaders} formatDate={formatDate} />

          {/* Problem Images (from Telegram Alerts) */}
          <ProblemImagesSection ticketId={id} getAuthHeaders={getAuthHeaders} canEdit={canEdit} />

          {/* Mechanic Comment (from Telegram Alerts — internal) */}
          <MechanicCommentSection ticketId={id} getAuthHeaders={getAuthHeaders} canEdit={canEdit} />

          {/* Attachments */}
          <Card>
            <CardHeader className="border-b">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Ficheiros</CardTitle>
                {canEdit && (
                  <div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      className="hidden"
                      onChange={handleFileUpload}
                      accept=".pdf,.png,.jpg,.jpeg,.doc,.docx"
                    />
                    <Button
                      variant="outline"
                      className="border-2"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploadingFile}
                      data-testid="upload-file-btn"
                    >
                      {uploadingFile ? (
                        <div className="w-4 h-4 border-2 border-zinc-500 border-t-transparent rounded-full animate-spin mr-2" />
                      ) : (
                        <Upload className="h-4 w-4 mr-2" />
                      )}
                      Carregar Ficheiro
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {attachments.length === 0 ? (
                <div className="p-8 text-center text-zinc-500">
                  Nenhum ficheiro anexado
                </div>
              ) : (
                <div className="divide-y">
                  {attachments.map((att) => {
                    const isImage = att.file_type?.startsWith('image/');
                    const isPdf = att.file_type === 'application/pdf';
                    
                    return (
                      <div key={att.id} className="p-4 hover:bg-zinc-50">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                              isImage ? 'bg-blue-100' : isPdf ? 'bg-red-100' : 'bg-zinc-100'
                            }`}>
                              <FileText className={`h-5 w-5 ${
                                isImage ? 'text-blue-600' : isPdf ? 'text-red-600' : 'text-zinc-600'
                              }`} />
                            </div>
                            <div>
                              <p className="font-semibold text-slate-900">{att.original_filename}</p>
                              <p className="text-xs text-zinc-500">
                                {(att.file_size / 1024).toFixed(1)} KB • {formatDate(att.uploaded_at)} • {att.uploaded_by_name}
                              </p>
                            </div>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => downloadFile(att.id, att.original_filename)}
                            data-testid={`download-${att.id}`}
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                        </div>
                        
                        {/* Preview Section */}
                        {isImage && attachmentUrls[att.id] && (
                          <div className="mt-2 rounded-lg overflow-hidden border border-zinc-200 max-w-md">
                            <img 
                              src={attachmentUrls[att.id]}
                              alt={att.original_filename}
                              className="w-full h-auto max-h-64 object-contain bg-zinc-50"
                              loading="lazy"
                            />
                          </div>
                        )}
                        
                        {isPdf && attachmentUrls[att.id] && (
                          <div className="mt-2 rounded-lg overflow-hidden border border-zinc-200">
                            <iframe
                              src={`${attachmentUrls[att.id]}#toolbar=0`}
                              title={att.original_filename}
                              className="w-full h-96 bg-zinc-50"
                              data-testid={`pdf-preview-${att.id}`}
                            />
                          </div>
                        )}
                        
                        {(isImage || isPdf) && !attachmentUrls[att.id] && (
                          <div className="mt-2 p-4 rounded-lg border border-zinc-200 bg-zinc-50 text-center text-zinc-500 text-sm">
                            A carregar preview...
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* SLAs Tab */}
        <TabsContent value="slas" className="space-y-4">
          {/* SLA Info */}
          <Card>
            <CardHeader className="border-b">
              <CardTitle className="text-lg">Prazos SLA</CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              {/* Main SLA Status */}
              <div className={`p-4 rounded-lg border-2 ${
                ticket.sla_breached ? 'bg-red-50 border-red-300' :
                ticket.sla_paused_at ? 'bg-amber-50 border-amber-300' :
                ticket.first_response_done ? 'bg-emerald-50 border-emerald-300' :
                'bg-zinc-50 border-zinc-200'
              }`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-full ${
                      ticket.sla_breached ? 'bg-red-100' :
                      ticket.sla_paused_at ? 'bg-amber-100' :
                      ticket.first_response_done ? 'bg-emerald-100' :
                      'bg-zinc-100'
                    }`}>
                      <Clock className={`h-6 w-6 ${
                        ticket.sla_breached ? 'text-red-600' :
                        ticket.sla_paused_at ? 'text-amber-600' :
                        ticket.first_response_done ? 'text-emerald-600' :
                        'text-zinc-500'
                      }`} />
                    </div>
                    <div>
                      <p className="font-semibold text-slate-800">
                        {ticket.sla_breached ? 'SLA Violado' :
                         ticket.sla_paused_at ? 'SLA Pausado' :
                         ticket.first_response_done ? 'SLA Cumprido' :
                         'SLA em Curso'}
                      </p>
                      <p className="text-sm text-zinc-500">
                        {ticket.sla_policy_key || `Tipo: ${ticket.type}`}
                      </p>
                    </div>
                  </div>
                  {ticket.sla_target_minutes && (
                    <div className="text-right">
                      <p className="text-sm text-zinc-500">Tempo Alvo</p>
                      <p className="font-semibold text-slate-800">
                        {Math.floor(ticket.sla_target_minutes / 60)}h {ticket.sla_target_minutes % 60}m úteis
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* SLA Details Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* SLA Due */}
                <div className="flex items-center gap-3 p-4 bg-zinc-50 rounded-lg">
                  <Clock className={`h-5 w-5 ${ticket.is_overdue ? 'text-red-500' : 'text-zinc-400'}`} />
                  <div>
                    <p className="text-sm text-zinc-500">Prazo SLA</p>
                    {ticket.sla_due ? (
                      <p className={`font-medium ${ticket.is_overdue ? 'text-red-600' : 'text-slate-700'}`}>
                        {formatDate(ticket.sla_due)}
                      </p>
                    ) : (
                      <p className="text-zinc-400">Não definido</p>
                    )}
                  </div>
                </div>

                {/* SLA Started */}
                <div className="flex items-center gap-3 p-4 bg-zinc-50 rounded-lg">
                  <Clock className="h-5 w-5 text-zinc-400" />
                  <div>
                    <p className="text-sm text-zinc-500">Início SLA</p>
                    {ticket.sla_started_at ? (
                      <p className="font-medium text-slate-700">{formatDate(ticket.sla_started_at)}</p>
                    ) : (
                      <p className="text-zinc-400">{formatDate(ticket.created_at)}</p>
                    )}
                  </div>
                </div>

                {/* First Response */}
                <div className="flex items-center gap-3 p-4 bg-zinc-50 rounded-lg">
                  <CheckCircle className={`h-5 w-5 ${ticket.first_response_done ? 'text-emerald-500' : 'text-zinc-400'}`} />
                  <div>
                    <p className="text-sm text-zinc-500">1ª Resposta</p>
                    <p className={`font-medium ${ticket.first_response_done ? 'text-emerald-600' : 'text-zinc-400'}`}>
                      {ticket.first_response_done ? 'Concluída' : 'Pendente'}
                    </p>
                  </div>
                </div>

                {/* Paused Minutes */}
                {(ticket.sla_paused_minutes > 0 || ticket.sla_paused_at) && (
                  <div className="flex items-center gap-3 p-4 bg-amber-50 rounded-lg">
                    <AlertCircle className="h-5 w-5 text-amber-500" />
                    <div>
                      <p className="text-sm text-amber-600">Tempo Pausado</p>
                      <p className="font-medium text-amber-700">
                        {ticket.sla_paused_minutes || 0} min úteis
                        {ticket.sla_paused_at && ' (ativo)'}
                      </p>
                    </div>
                  </div>
                )}

                {/* Breached At */}
                {ticket.sla_breached && ticket.sla_breached_at && (
                  <div className="flex items-center gap-3 p-4 bg-red-50 rounded-lg">
                    <AlertCircle className="h-5 w-5 text-red-500" />
                    <div>
                      <p className="text-sm text-red-600">Violado em</p>
                      <p className="font-medium text-red-700">{formatDate(ticket.sla_breached_at)}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Quote Status */}
              <div className="pt-4 border-t">
                <p className="text-sm font-medium text-zinc-600 mb-3">Estado do Orçamento</p>
                <div className="flex items-center gap-3 p-4 bg-zinc-50 rounded-lg">
                  <FileText className={`h-5 w-5 ${ticket.quote_sent ? 'text-emerald-500' : 'text-zinc-400'}`} />
                  <div>
                    <p className="text-sm text-zinc-500">Orçamento</p>
                    <p className={`font-medium ${ticket.quote_sent ? 'text-emerald-600' : 'text-zinc-400'}`}>
                      {ticket.quote_sent ? 
                        `Enviado${ticket.quote_value ? ` - ${ticket.quote_value.toFixed(2)}€` : ''}` : 
                        'Não enviado'}
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Alerts */}
          <Card>
            <CardHeader className="border-b">
              <CardTitle className="text-lg">Alertas</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {alerts.length === 0 ? (
                <div className="p-8 text-center text-zinc-500">
                  Nenhum alerta
                </div>
              ) : (
                <div className="divide-y">
                  {alerts.map((alert) => (
                    <div 
                      key={alert.id} 
                      className={`flex items-center justify-between p-4 ${alert.is_resolved ? 'bg-zinc-50/50' : 'bg-red-50/50'}`}
                    >
                      <div className="flex items-center gap-3">
                        {alert.is_resolved ? (
                          <CheckCircle className="h-5 w-5 text-emerald-600" />
                        ) : (
                          <AlertTriangle className="h-5 w-5 text-red-600" />
                        )}
                        <div>
                          <p className={`font-semibold ${alert.is_resolved ? 'text-zinc-500' : 'text-slate-900'}`}>
                            {alert.body}
                          </p>
                          <p className="text-xs text-zinc-500">{formatDate(alert.created_at)}</p>
                        </div>
                      </div>
                      {!alert.is_resolved && canEdit && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => resolveAlert(alert.id)}
                          data-testid={`resolve-alert-${alert.id}`}
                        >
                          <CheckCircle className="h-4 w-4 mr-1" />
                          Resolver
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Histórico Tab */}
        <TabsContent value="historico" className="space-y-4">
          <Card>
            <CardHeader className="border-b">
              <CardTitle className="text-lg">Notas e Histórico</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {notes.length === 0 ? (
                <div className="p-8 text-center text-zinc-500">
                  Nenhuma nota ou alteração registada
                </div>
              ) : (
                <ScrollArea className="h-[400px]">
                  <div className="divide-y">
                    {notes.map((note) => (
                      <div key={note.id} className="p-4">
                        <div className="flex items-start gap-3">
                          <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-sm font-bold text-slate-600">
                            {note.created_by_name?.charAt(0) || 'S'}
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-semibold text-sm">
                                {note.created_by_name || 'Sistema'}
                              </span>
                              <span className="text-xs text-zinc-500">
                                {formatDate(note.created_at)}
                              </span>
                            </div>
                            <p className="text-slate-700 whitespace-pre-wrap">{note.body}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Edit Ticket Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pencil className="h-5 w-5 text-orange-600" />
              Editar Ticket
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="edit-name">Nome do Cliente *</Label>
                <Input
                  id="edit-name"
                  value={editForm.customer_name || ''}
                  onChange={(e) => setEditForm({ ...editForm, customer_name: e.target.value })}
                  data-testid="edit-customer-name"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-phone">Telefone *</Label>
                <Input
                  id="edit-phone"
                  value={editForm.customer_phone || ''}
                  onChange={(e) => setEditForm({ ...editForm, customer_phone: e.target.value })}
                  data-testid="edit-customer-phone"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="edit-email">Email</Label>
                <Input
                  id="edit-email"
                  type="email"
                  value={editForm.customer_email || ''}
                  onChange={(e) => setEditForm({ ...editForm, customer_email: e.target.value })}
                  data-testid="edit-customer-email"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-plate">Matrícula</Label>
                <Input
                  id="edit-plate"
                  value={editForm.vehicle_plate || ''}
                  onChange={(e) => setEditForm({ ...editForm, vehicle_plate: e.target.value.toUpperCase() })}
                  data-testid="edit-vehicle-plate"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo</Label>
                <Select 
                  value={editForm.type || 'INFORMACAO'} 
                  onValueChange={(value) => setEditForm({ ...editForm, type: value })}
                >
                  <SelectTrigger data-testid="edit-type-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ORCAMENTO_PNEUS">Orçamento Pneus</SelectItem>
                    <SelectItem value="ORCAMENTO_MECANICA">Orçamento Mecânica</SelectItem>
                    <SelectItem value="MARCACAO">Marcação</SelectItem>
                    <SelectItem value="INFORMACAO">Informação</SelectItem>
                    <SelectItem value="INTERNO">Interno</SelectItem>
                    <SelectItem value="RECLAMACAO">Reclamação</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Prioridade</Label>
                <Select 
                  value={editForm.priority || 'NORMAL'} 
                  onValueChange={(value) => setEditForm({ ...editForm, priority: value })}
                >
                  <SelectTrigger data-testid="edit-priority-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="NORMAL">Normal</SelectItem>
                    <SelectItem value="URGENTE">Urgente</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-description">Descrição</Label>
              <Textarea
                id="edit-description"
                value={editForm.description || ''}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                className="min-h-[100px]"
                data-testid="edit-description"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={saveTicketEdit} 
              disabled={savingEdit || !editForm.customer_name || !editForm.customer_phone}
              className="bg-orange-600 hover:bg-orange-700"
              data-testid="save-edit-btn"
            >
              {savingEdit ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
              ) : null}
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ============== Problem Images Section ==============
const ProblemImagesSection = ({ ticketId, getAuthHeaders, canEdit }) => {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [enlarged, setEnlarged] = useState(null);

  useEffect(() => {
    const fetch = async () => {
      try {
        const resp = await axios.get(`${API_URL}/api/telegram-alerts/tickets/${ticketId}/problem-images`, {
          headers: getAuthHeaders()
        });
        setImages(resp.data.problem_images || []);
      } catch (err) { console.error('Failed to load problem images:', err); }
      finally { setLoading(false); }
    };
    fetch();
  }, [ticketId, getAuthHeaders]);

  const toggleVisibility = async (imageId, currentVisible) => {
    try {
      await axios.put(
        `${API_URL}/api/telegram-alerts/tickets/${ticketId}/problem-images/${imageId}/visibility`,
        { visible_to_customer: !currentVisible },
        { headers: getAuthHeaders() }
      );
      setImages(prev => prev.map(img =>
        img.id === imageId ? { ...img, visible_to_customer: !currentVisible } : img
      ));
    } catch (err) { console.error('Failed to toggle image visibility:', err); }
  };

  const removeImage = async (imageId) => {
    if (!window.confirm('Remover esta foto do ticket?')) return;
    try {
      await axios.delete(
        `${API_URL}/api/telegram-alerts/tickets/${ticketId}/problem-images/${imageId}`,
        { headers: getAuthHeaders() }
      );
      setImages(prev => prev.filter(img => img.id !== imageId));
    } catch (err) { console.error('Failed to remove image:', err); }
  };

  if (loading || images.length === 0) return null;

  return (
    <Card>
      <CardHeader className="border-b pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <Camera className="h-5 w-5 text-orange-600" />
          Fotos do problema
          <Badge variant="secondary" className="ml-1">{images.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {images.map((img) => (
            <ProblemImageCard
              key={img.id}
              ticketId={ticketId}
              image={img}
              getAuthHeaders={getAuthHeaders}
              canEdit={canEdit}
              onToggleVisibility={() => toggleVisibility(img.id, img.visible_to_customer)}
              onRemove={() => removeImage(img.id)}
              onEnlarge={(src) => setEnlarged(src)}
            />
          ))}
        </div>
        <p className="text-xs text-zinc-400 mt-3">
          Apenas fotos marcadas como "Mostrar ao cliente" ficam visíveis no link público do orçamento.
        </p>
      </CardContent>
      {enlarged && (
        <div className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-4" onClick={() => setEnlarged(null)}>
          <img src={enlarged} alt="Foto do problema" className="max-w-full max-h-full object-contain rounded-lg" />
        </div>
      )}
    </Card>
  );
};

const ProblemImageCard = ({ ticketId, image, getAuthHeaders, canEdit, onToggleVisibility, onRemove, onEnlarge }) => {
  const [src, setSrc] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const resp = await axios.get(
          `${API_URL}/api/telegram-alerts/tickets/${ticketId}/problem-images/${image.id}/data`,
          { headers: getAuthHeaders() }
        );
        if (cancelled) return;
        if (resp.data.base64) setSrc(`data:${resp.data.file_type || 'image/jpeg'};base64,${resp.data.base64}`);
      } catch { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    };
    load();
    return () => { cancelled = true; };
  }, [ticketId, image.id, getAuthHeaders]);

  return (
    <div className="relative group rounded-lg overflow-hidden border-2 border-zinc-200 bg-zinc-100" data-testid={`problem-img-${image.id}`}>
      <div className="aspect-square">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="w-5 h-5 border-2 border-orange-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : src ? (
          <img src={src} alt="Foto do problema" className="w-full h-full object-cover cursor-pointer" onClick={() => onEnlarge(src)} />
        ) : (
          <div className="flex items-center justify-center h-full text-zinc-300">
            <Camera className="h-6 w-6" />
          </div>
        )}
      </div>
      {/* Visibility badge */}
      <div className="absolute top-1.5 right-1.5">
        {image.visible_to_customer ? (
          <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Visível</span>
        ) : (
          <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full bg-zinc-200 text-zinc-500">Oculta</span>
        )}
      </div>
      {/* Actions */}
      {canEdit && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent p-2 opacity-0 group-hover:opacity-100 transition-opacity flex justify-between items-center">
          <button
            onClick={onToggleVisibility}
            className={`text-[10px] font-semibold px-2 py-1 rounded ${image.visible_to_customer ? 'bg-white/90 text-zinc-700' : 'bg-emerald-500 text-white'}`}
            data-testid={`toggle-visibility-${image.id}`}
          >
            {image.visible_to_customer ? 'Ocultar' : 'Mostrar ao cliente'}
          </button>
          <button onClick={onRemove} className="text-white/80 hover:text-red-400 p-1" data-testid={`remove-img-${image.id}`}>
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
};

// Mechanic Comment Section (text or audio + transcription) — internal only
const MechanicCommentSection = ({ ticketId, getAuthHeaders, canEdit }) => {
  const [mc, setMc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [audioSrc, setAudioSrc] = useState(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const [retranscribing, setRetranscribing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const resp = await axios.get(
          `${API_URL}/api/telegram-alerts/tickets/${ticketId}/mechanic-comment`,
          { headers: getAuthHeaders() }
        );
        if (!cancelled) setMc(resp.data.mechanic_comment);
      } catch (err) { console.error('Failed to load mechanic comment:', err); }
      finally { if (!cancelled) setLoading(false); }
    };
    load();
    return () => { cancelled = true; };
  }, [ticketId, getAuthHeaders]);

  useEffect(() => {
    if (!mc || mc.type !== 'audio' || !mc.has_audio || audioSrc) return;
    let cancelled = false;
    const load = async () => {
      setAudioLoading(true);
      try {
        const resp = await axios.get(
          `${API_URL}/api/telegram-alerts/tickets/${ticketId}/audio`,
          { headers: getAuthHeaders() }
        );
        if (!cancelled && resp.data.base64) {
          setAudioSrc(`data:${resp.data.file_type || 'audio/ogg'};base64,${resp.data.base64}`);
        }
      } catch (err) { console.error('Failed to load mechanic audio:', err); }
      finally { if (!cancelled) setAudioLoading(false); }
    };
    load();
    return () => { cancelled = true; };
  }, [ticketId, mc, audioSrc, getAuthHeaders]);

  const handleRetranscribe = async () => {
    setRetranscribing(true);
    try {
      const resp = await axios.post(
        `${API_URL}/api/telegram-alerts/tickets/${ticketId}/retranscribe-audio`,
        {},
        { headers: getAuthHeaders() }
      );
      toast.success(resp.data.status === 'success' ? 'Transcrição atualizada' : 'Transcrição falhou');
      setMc((prev) => prev ? { ...prev, text: resp.data.text || prev.text, transcription_status: resp.data.status } : prev);
    } catch (e) {
      toast.error('Erro ao re-transcrever');
    } finally {
      setRetranscribing(false);
    }
  };

  if (loading) return null;
  if (!mc) return null;

  return (
    <Card data-testid="ticket-mechanic-comment">
      <CardHeader className="border-b">
        <CardTitle className="text-lg flex items-center gap-2">
          {mc.type === 'audio' ? '🎤' : '📝'} Comentário do mecânico
          <span className="text-xs font-normal text-zinc-500 ml-1">(interno)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pt-4">
        {mc.type === 'text' && (
          <p className="text-sm text-zinc-700 whitespace-pre-wrap" data-testid="mc-text-body">
            {mc.text || '(vazio)'}
          </p>
        )}
        {mc.type === 'audio' && (
          <>
            {audioLoading ? (
              <p className="text-xs text-zinc-500">A carregar áudio...</p>
            ) : audioSrc ? (
              <audio controls src={audioSrc} className="w-full" data-testid="mc-audio-player" />
            ) : (
              <p className="text-xs text-zinc-500">Áudio indisponível</p>
            )}
            <div className="border-t pt-3">
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[10px] uppercase tracking-wide text-zinc-400">Transcrição</p>
                {canEdit && (
                  <button
                    type="button"
                    onClick={handleRetranscribe}
                    disabled={retranscribing}
                    className="text-xs text-orange-600 hover:underline disabled:opacity-50"
                    data-testid="mc-retranscribe-btn"
                  >
                    {retranscribing ? 'A transcrever...' : 'Re-transcrever'}
                  </button>
                )}
              </div>
              {mc.transcription_status === 'success' && mc.text ? (
                <p className="text-sm text-zinc-700 whitespace-pre-wrap">{mc.text}</p>
              ) : (
                <p className="text-xs text-amber-600">
                  {mc.transcription_status === 'failed'
                    ? 'Transcrição falhou — pode tentar novamente.'
                    : 'Sem transcrição disponível.'}
                </p>
              )}
            </div>
          </>
        )}
        {mc.created_by?.name && (
          <p className="text-xs text-zinc-400 pt-2 border-t">
            Enviado por: {mc.created_by.name}
          </p>
        )}
      </CardContent>
    </Card>
  );
};

export default TicketDetail;
