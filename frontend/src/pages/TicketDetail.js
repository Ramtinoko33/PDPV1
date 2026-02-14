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
  FileText,
  AlertTriangle,
  Upload,
  Download,
  CheckCircle,
  XCircle,
  History,
  StickyNote,
  Paperclip,
  X
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

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

  const fetchData = async () => {
    try {
      const [ticketRes, messagesRes, notesRes, alertsRes, attachmentsRes] = await Promise.all([
        axios.get(`${API_URL}/api/tickets/${id}`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/messages`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/notes`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/alerts`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets/${id}/attachments`, { headers: getAuthHeaders() })
      ]);
      
      setTicket(ticketRes.data);
      setMessages(messagesRes.data);
      setNotes(notesRes.data);
      setAlerts(alertsRes.data);
      setAttachments(attachmentsRes.data);
      setQuoteValue(ticketRes.data.quote_value || '');
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
        setUsers(response.data.filter(u => ['AGENT', 'SUPERVISOR'].includes(u.role)));
      } catch (error) {
        console.error('Error fetching users:', error);
      }
    }
  };

  useEffect(() => {
    fetchData();
    fetchUsers();
  }, [id]);

  const updateTicket = async (updates) => {
    try {
      await axios.put(`${API_URL}/api/tickets/${id}`, updates, { headers: getAuthHeaders() });
      toast.success('Ticket atualizado');
      fetchData();
    } catch (error) {
      toast.error('Erro ao atualizar ticket');
    }
  };

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

  const statusOptions = [
    { value: 'ABERTO', label: 'Aberto' },
    { value: 'EM_TRATAMENTO', label: 'Em Tratamento' },
    { value: 'AGUARDA_CLIENTE', label: 'Aguarda Cliente' },
    { value: 'FECHADO', label: 'Fechado' }
  ];

  const getStatusClass = (status) => {
    const classes = {
      ABERTO: 'status-aberto',
      EM_TRATAMENTO: 'status-em-tratamento',
      AGUARDA_CLIENTE: 'status-aguarda-cliente',
      FECHADO: 'status-fechado'
    };
    return classes[status] || 'bg-zinc-100 text-zinc-700';
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

  const canEdit = ['ADMIN', 'SUPERVISOR'].includes(user?.role) || 
    (user?.role === 'AGENT' && ticket.assigned_to_user_id === user.id);

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
          </p>
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Status */}
          {canEdit ? (
            <Select
              value={ticket.status}
              onValueChange={(value) => updateTicket({ status: value })}
            >
              <SelectTrigger className={`h-10 w-44 font-semibold ${getStatusClass(ticket.status)}`} data-testid="status-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {statusOptions.map(opt => (
                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Badge className={`text-sm py-2 px-4 ${getStatusClass(ticket.status)}`}>
              {statusOptions.find(s => s.value === ticket.status)?.label}
            </Badge>
          )}

          {/* Assign */}
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
        </div>
      </div>

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
              <div>
                <p className="text-xs text-zinc-500 font-medium uppercase">Telefone</p>
                <p className="font-semibold text-slate-900">{ticket.customer_phone}</p>
              </div>
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
                              <span className="text-xs text-zinc-500">
                                {formatDate(msg.created_at)}
                              </span>
                            </div>
                            <p className="text-slate-700 whitespace-pre-wrap">{msg.body}</p>
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
        </TabsContent>

        {/* Documentos Tab */}
        <TabsContent value="documentos" className="space-y-4">
          {/* Quote Info */}
          <Card>
            <CardHeader className="border-b">
              <CardTitle className="text-lg">Orçamento</CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="quote_sent"
                    checked={ticket.quote_sent}
                    onCheckedChange={(checked) => canEdit && updateTicket({ quote_sent: checked })}
                    disabled={!canEdit}
                    data-testid="quote-sent-checkbox"
                  />
                  <Label htmlFor="quote_sent" className="font-semibold">
                    Orçamento enviado ao cliente
                  </Label>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <Label className="font-semibold w-32">Valor (€)</Label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={quoteValue}
                  onChange={(e) => setQuoteValue(e.target.value)}
                  onBlur={() => canEdit && updateTicket({ quote_value: parseFloat(quoteValue) || null })}
                  className="w-40 border-2"
                  disabled={!canEdit}
                  data-testid="quote-value-input"
                />
              </div>
            </CardContent>
          </Card>

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
                  {attachments.map((att) => (
                    <div key={att.id} className="flex items-center justify-between p-4 hover:bg-zinc-50">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-zinc-100 rounded-lg flex items-center justify-center">
                          <FileText className="h-5 w-5 text-zinc-600" />
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
                  ))}
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
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex items-center gap-3 p-4 bg-zinc-50 rounded-lg">
                  <Clock className={`h-6 w-6 ${ticket.first_response_done ? 'text-emerald-600' : 'text-zinc-400'}`} />
                  <div>
                    <p className="text-sm text-zinc-500">1ª Resposta</p>
                    {ticket.sla_first_response_due ? (
                      <p className={`font-semibold ${ticket.first_response_done ? 'text-emerald-600' : ''}`}>
                        {ticket.first_response_done ? 'Concluído' : formatDate(ticket.sla_first_response_due)}
                      </p>
                    ) : (
                      <p className="text-zinc-400">N/A</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 p-4 bg-zinc-50 rounded-lg">
                  <FileText className={`h-6 w-6 ${ticket.quote_sent ? 'text-emerald-600' : 'text-zinc-400'}`} />
                  <div>
                    <p className="text-sm text-zinc-500">Orçamento</p>
                    {ticket.sla_quote_due ? (
                      <p className={`font-semibold ${ticket.quote_sent ? 'text-emerald-600' : ''}`}>
                        {ticket.quote_sent ? 'Enviado' : formatDate(ticket.sla_quote_due)}
                      </p>
                    ) : (
                      <p className="text-zinc-400">N/A</p>
                    )}
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
    </div>
  );
};

export default TicketDetail;
