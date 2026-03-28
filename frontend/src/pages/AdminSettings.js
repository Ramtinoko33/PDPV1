import { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Textarea } from '../components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '../components/ui/dialog';
import { toast } from 'sonner';
import { 
  Tag, 
  AlertCircle,
  Clock,
  Plus,
  Pencil,
  Trash2,
  Save,
  GripVertical,
  Mail,
  Send,
  CheckCircle,
  XCircle,
  Eye,
  EyeOff,
  Server,
  Bell,
  Palette,
  Building,
  FileText,
  Database,
  Calendar,
  ToggleLeft,
  ToggleRight
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const AdminSettings = () => {
  const { getAuthHeaders } = useAuth();
  
  // Ticket Types State
  const [ticketTypes, setTicketTypes] = useState([]);
  const [loadingTypes, setLoadingTypes] = useState(true);
  const [typeDialogOpen, setTypeDialogOpen] = useState(false);
  const [editingType, setEditingType] = useState(null);
  const [typeForm, setTypeForm] = useState({ code: '', label: '', color: '#f97316' });
  const [savingType, setSavingType] = useState(false);
  
  // Ticket Statuses State
  const [ticketStatuses, setTicketStatuses] = useState([]);
  const [loadingStatuses, setLoadingStatuses] = useState(true);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [editingStatus, setEditingStatus] = useState(null);
  const [statusForm, setStatusForm] = useState({ code: '', label: '', color: '#3b82f6', is_final: false, is_auto: false });
  const [savingStatus, setSavingStatus] = useState(false);
  
  // SLA Config State - Updated with business hours and per-type SLAs
  const [slaConfig, setSlaConfig] = useState({
    // Business Hours
    monday: { start: '08:30', end: '18:30', closed: false },
    tuesday: { start: '08:30', end: '18:30', closed: false },
    wednesday: { start: '08:30', end: '18:30', closed: false },
    thursday: { start: '08:30', end: '18:30', closed: false },
    friday: { start: '08:30', end: '18:30', closed: false },
    saturday: { start: '08:30', end: '13:00', closed: false },
    sunday: { start: '08:30', end: '13:00', closed: true },
    // SLA per ticket type (hours)
    sla_orcamento_mecanica: 8,
    sla_orcamento_pneus: 8,
    sla_informacao: 2,
    sla_reclamacao: 2,
    sla_marcacao: 3,
    sla_interno: 8,
    sla_default: 2,
    // Toggles
    use_business_hours: true,
    pause_on_aguarda_cliente: true,
    // Legacy
    first_response_hours: 2,
    quote_response_hours: 24,
    enabled: true
  });
  const [loadingSla, setLoadingSla] = useState(true);
  const [savingSla, setSavingSla] = useState(false);

  // Push Config State
  const [pushConfig, setPushConfig] = useState({
    vapid_configured: false,
    vapid_public_key: '',
    subscriptions_count: 0
  });
  const [loadingPush, setLoadingPush] = useState(true);
  const [generatingKeys, setGeneratingKeys] = useState(false);

  // Branding Config State
  const [brandingConfig, setBrandingConfig] = useState({
    company_name: 'PDPV',
    company_subtitle: 'Pneus de Pedro V.',
    company_logo_url: '',
    primary_color: '#f97316',
    secondary_color: '#1f2937',
    company_phone: '',
    company_email: '',
    company_address: '',
    company_website: '',
    email_templates: {}
  });
  const [loadingBranding, setLoadingBranding] = useState(true);
  const [savingBranding, setSavingBranding] = useState(false);
  
  // Email Config State
  const [emailConfig, setEmailConfig] = useState({
    smtp_configured: false,
    smtp_host: '',
    smtp_port: 587,
    smtp_username: '',
    smtp_password: '',
    smtp_use_ssl: false,
    smtp_use_tls: true,
    email_from: '',
    email_from_name: 'PDPV Tickets',
    frontend_url: '',
    resend_configured: false
  });
  const [loadingEmail, setLoadingEmail] = useState(true);
  const [savingEmail, setSavingEmail] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [sendingTest, setSendingTest] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Holidays State
  const [holidays, setHolidays] = useState([]);
  const [loadingHolidays, setLoadingHolidays] = useState(true);
  const [holidayDialogOpen, setHolidayDialogOpen] = useState(false);
  const [editingHoliday, setEditingHoliday] = useState(null);
  const [holidayForm, setHolidayForm] = useState({ 
    date: '', 
    name: '', 
    is_recurring_annual: false, 
    scope: 'nacional', 
    active: true 
  });
  const [savingHoliday, setSavingHoliday] = useState(false);

  // Fetch all settings on mount
  useEffect(() => {
    fetchTicketTypes();
    fetchTicketStatuses();
    fetchSlaConfig();
    fetchEmailConfig();
    fetchPushConfig();
    fetchBrandingConfig();
    fetchHolidays();
  }, []);

  // ============== TICKET TYPES ==============
  const fetchTicketTypes = async () => {
    setLoadingTypes(true);
    try {
      const response = await axios.get(`${API_URL}/api/admin/ticket-types`, { headers: getAuthHeaders() });
      setTicketTypes(response.data);
    } catch (error) {
      console.error('Error fetching ticket types:', error);
      setTicketTypes([
        { id: '1', code: 'ORCAMENTO_PNEUS', label: 'Orçamento Pneus', color: '#f97316' },
        { id: '2', code: 'ORCAMENTO_MECANICA', label: 'Orçamento Mecânica', color: '#3b82f6' },
        { id: '3', code: 'MARCACAO', label: 'Marcação', color: '#10b981' },
        { id: '4', code: 'INFORMACAO', label: 'Informação', color: '#8b5cf6' },
        { id: '5', code: 'INTERNO', label: 'Interno', color: '#6b7280' },
        { id: '6', code: 'RECLAMACAO', label: 'Reclamação', color: '#ef4444' }
      ]);
    } finally {
      setLoadingTypes(false);
    }
  };

  const openTypeDialog = (type = null) => {
    if (type) {
      setEditingType(type);
      setTypeForm({ code: type.code, label: type.label, color: type.color || '#f97316' });
    } else {
      setEditingType(null);
      setTypeForm({ code: '', label: '', color: '#f97316' });
    }
    setTypeDialogOpen(true);
  };

  const saveTicketType = async () => {
    if (!typeForm.code || !typeForm.label) {
      toast.error('Preencha todos os campos');
      return;
    }
    
    setSavingType(true);
    try {
      if (editingType) {
        await axios.put(
          `${API_URL}/api/admin/ticket-types/${editingType.id}`,
          typeForm,
          { headers: getAuthHeaders() }
        );
        toast.success('Tipo atualizado');
      } else {
        await axios.post(
          `${API_URL}/api/admin/ticket-types`,
          typeForm,
          { headers: getAuthHeaders() }
        );
        toast.success('Tipo criado');
      }
      setTypeDialogOpen(false);
      fetchTicketTypes();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao guardar tipo');
    } finally {
      setSavingType(false);
    }
  };

  const deleteTicketType = async (typeId) => {
    if (!window.confirm('Tem a certeza que deseja eliminar este tipo?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/admin/ticket-types/${typeId}`, { headers: getAuthHeaders() });
      toast.success('Tipo eliminado');
      fetchTicketTypes();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao eliminar tipo');
    }
  };

  // ============== TICKET STATUSES ==============
  const fetchTicketStatuses = async () => {
    setLoadingStatuses(true);
    try {
      const response = await axios.get(`${API_URL}/api/admin/ticket-statuses`, { headers: getAuthHeaders() });
      setTicketStatuses(response.data);
    } catch (error) {
      console.error('Error fetching ticket statuses:', error);
      setTicketStatuses([
        { id: '1', code: 'ABERTO', label: 'Aberto', color: '#22c55e', is_final: false },
        { id: '2', code: 'EM_TRATAMENTO', label: 'Em Tratamento', color: '#3b82f6', is_final: false },
        { id: '3', code: 'AGUARDA_CLIENTE', label: 'Aguarda Cliente', color: '#f59e0b', is_final: false },
        { id: '4', code: 'FECHADO', label: 'Fechado', color: '#6b7280', is_final: true }
      ]);
    } finally {
      setLoadingStatuses(false);
    }
  };

  const openStatusDialog = (status = null) => {
    if (status) {
      setEditingStatus(status);
      setStatusForm({ 
        code: status.code, 
        label: status.label, 
        color: status.color || '#3b82f6',
        is_final: status.is_final || false,
        is_auto: status.is_auto || false
      });
    } else {
      setEditingStatus(null);
      setStatusForm({ code: '', label: '', color: '#3b82f6', is_final: false, is_auto: false });
    }
    setStatusDialogOpen(true);
  };

  const saveTicketStatus = async () => {
    if (!statusForm.code || !statusForm.label) {
      toast.error('Preencha todos os campos');
      return;
    }
    
    setSavingStatus(true);
    try {
      if (editingStatus) {
        await axios.put(
          `${API_URL}/api/admin/ticket-statuses/${editingStatus.id}`,
          statusForm,
          { headers: getAuthHeaders() }
        );
        toast.success('Estado atualizado');
      } else {
        await axios.post(
          `${API_URL}/api/admin/ticket-statuses`,
          statusForm,
          { headers: getAuthHeaders() }
        );
        toast.success('Estado criado');
      }
      setStatusDialogOpen(false);
      fetchTicketStatuses();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao guardar estado');
    } finally {
      setSavingStatus(false);
    }
  };

  const deleteTicketStatus = async (statusId) => {
    if (!window.confirm('Tem a certeza que deseja eliminar este estado?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/admin/ticket-statuses/${statusId}`, { headers: getAuthHeaders() });
      toast.success('Estado eliminado');
      fetchTicketStatuses();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao eliminar estado');
    }
  };

  // ============== SLA CONFIG ==============
  const fetchSlaConfig = async () => {
    setLoadingSla(true);
    try {
      const response = await axios.get(`${API_URL}/api/admin/sla-config`, { headers: getAuthHeaders() });
      setSlaConfig(response.data);
    } catch (error) {
      console.error('Error fetching SLA config:', error);
    } finally {
      setLoadingSla(false);
    }
  };

  const saveSlaConfig = async () => {
    setSavingSla(true);
    try {
      await axios.put(
        `${API_URL}/api/admin/sla-config`,
        slaConfig,
        { headers: getAuthHeaders() }
      );
      toast.success('Configuração SLA guardada');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao guardar configuração');
    } finally {
      setSavingSla(false);
    }
  };

  // ============== PUSH CONFIG ==============
  const fetchPushConfig = async () => {
    setLoadingPush(true);
    try {
      const response = await axios.get(`${API_URL}/api/push/vapid-public-key`, { headers: getAuthHeaders() });
      const statsResponse = await axios.get(`${API_URL}/api/admin/push-stats`, { headers: getAuthHeaders() }).catch(() => ({ data: { subscriptions_count: 0 } }));
      setPushConfig({
        vapid_configured: !!response.data.publicKey,
        vapid_public_key: response.data.publicKey || '',
        subscriptions_count: statsResponse.data?.subscriptions_count || 0
      });
    } catch (error) {
      console.error('Error fetching push config:', error);
    } finally {
      setLoadingPush(false);
    }
  };

  const generateVapidKeys = async () => {
    setGeneratingKeys(true);
    try {
      const res = await axios.post(`${API_URL}/api/admin/webpush/generate-keys`, {}, { headers: getAuthHeaders() });
      toast.success('Chaves VAPID geradas com sucesso! Web Push ativado.');
      await fetchPushConfig();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao gerar chaves VAPID');
    } finally {
      setGeneratingKeys(false);
    }
  };

  // ============== BRANDING CONFIG ==============
  const fetchBrandingConfig = async () => {
    setLoadingBranding(true);
    try {
      const response = await axios.get(`${API_URL}/api/admin/branding`, { headers: getAuthHeaders() });
      setBrandingConfig(response.data);
    } catch (error) {
      console.error('Error fetching branding config:', error);
    } finally {
      setLoadingBranding(false);
    }
  };

  const saveBrandingConfig = async () => {
    setSavingBranding(true);
    try {
      await axios.put(`${API_URL}/api/admin/branding`, {
        company_name: brandingConfig.company_name,
        company_subtitle: brandingConfig.company_subtitle,
        company_logo_url: brandingConfig.company_logo_url,
        primary_color: brandingConfig.primary_color,
        secondary_color: brandingConfig.secondary_color,
        company_phone: brandingConfig.company_phone,
        company_email: brandingConfig.company_email,
        company_address: brandingConfig.company_address,
        company_website: brandingConfig.company_website
      }, { headers: getAuthHeaders() });
      
      // Save email templates separately
      await axios.put(`${API_URL}/api/admin/email-templates`, brandingConfig.email_templates, { headers: getAuthHeaders() });
      
      toast.success('Configuração de branding guardada');
      fetchBrandingConfig();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao guardar configuração');
    } finally {
      setSavingBranding(false);
    }
  };

  // ============== EMAIL CONFIG ==============
  const fetchEmailConfig = async () => {
    setLoadingEmail(true);
    try {
      const response = await axios.get(`${API_URL}/api/admin/email-config`, { headers: getAuthHeaders() });
      setEmailConfig(response.data);
    } catch (error) {
      console.error('Error fetching email config:', error);
    } finally {
      setLoadingEmail(false);
    }
  };

  const saveEmailConfig = async () => {
    setSavingEmail(true);
    try {
      await axios.put(
        `${API_URL}/api/admin/email-config`,
        emailConfig,
        { headers: getAuthHeaders() }
      );
      toast.success('Configuração de email guardada');
      fetchEmailConfig();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao guardar configuração');
    } finally {
      setSavingEmail(false);
    }
  };

  const sendTestEmail = async () => {
    if (!testEmail) {
      toast.error('Introduza um email');
      return;
    }
    
    setSendingTest(true);
    try {
      await axios.post(
        `${API_URL}/api/admin/test-email`,
        { recipient_email: testEmail },
        { headers: getAuthHeaders() }
      );
      toast.success(`Email de teste enviado para ${testEmail}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao enviar email de teste');
    } finally {
      setSendingTest(false);
    }
  };

  // ============== HOLIDAYS ==============
  const fetchHolidays = async () => {
    setLoadingHolidays(true);
    try {
      const response = await axios.get(`${API_URL}/api/admin/holidays`, { headers: getAuthHeaders() });
      setHolidays(response.data);
    } catch (error) {
      console.error('Error fetching holidays:', error);
      toast.error('Erro ao carregar feriados');
    } finally {
      setLoadingHolidays(false);
    }
  };

  const openHolidayDialog = (holiday = null) => {
    if (holiday) {
      setEditingHoliday(holiday);
      setHolidayForm({
        date: holiday.date,
        name: holiday.name,
        is_recurring_annual: holiday.is_recurring_annual,
        scope: holiday.scope,
        active: holiday.active
      });
    } else {
      setEditingHoliday(null);
      setHolidayForm({ date: '', name: '', is_recurring_annual: false, scope: 'nacional', active: true });
    }
    setHolidayDialogOpen(true);
  };

  const saveHoliday = async () => {
    if (!holidayForm.date || !holidayForm.name) {
      toast.error('Data e nome são obrigatórios');
      return;
    }
    
    setSavingHoliday(true);
    try {
      if (editingHoliday) {
        await axios.put(
          `${API_URL}/api/admin/holidays/${editingHoliday.id}`,
          holidayForm,
          { headers: getAuthHeaders() }
        );
        toast.success('Feriado actualizado');
      } else {
        await axios.post(
          `${API_URL}/api/admin/holidays`,
          holidayForm,
          { headers: getAuthHeaders() }
        );
        toast.success('Feriado criado');
      }
      setHolidayDialogOpen(false);
      fetchHolidays();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao guardar feriado');
    } finally {
      setSavingHoliday(false);
    }
  };

  const deleteHoliday = async (holidayId) => {
    if (!window.confirm('Tem a certeza que deseja eliminar este feriado?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/admin/holidays/${holidayId}`, { headers: getAuthHeaders() });
      toast.success('Feriado eliminado');
      fetchHolidays();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao eliminar feriado');
    }
  };

  const toggleHoliday = async (holidayId) => {
    try {
      await axios.post(`${API_URL}/api/admin/holidays/${holidayId}/toggle`, {}, { headers: getAuthHeaders() });
      toast.success('Estado do feriado alterado');
      fetchHolidays();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao alterar estado');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight">
          Configurações
        </h1>
        <p className="text-zinc-500 mt-1">
          Gerir tipos de ticket, estados, regras SLA e configurações de email
        </p>
      </div>

      <Tabs defaultValue="types" className="space-y-6">
        <TabsList className="bg-zinc-100 p-1">
          <TabsTrigger value="types" className="data-[state=active]:bg-white" data-testid="tab-types">
            <Tag className="h-4 w-4 mr-2" />
            Tipos de Ticket
          </TabsTrigger>
          <TabsTrigger value="statuses" className="data-[state=active]:bg-white" data-testid="tab-statuses">
            <AlertCircle className="h-4 w-4 mr-2" />
            Estados
          </TabsTrigger>
          <TabsTrigger value="sla" className="data-[state=active]:bg-white" data-testid="tab-sla">
            <Clock className="h-4 w-4 mr-2" />
            Regras SLA
          </TabsTrigger>
          <TabsTrigger value="holidays" className="data-[state=active]:bg-white" data-testid="tab-holidays">
            <Calendar className="h-4 w-4 mr-2" />
            Feriados
          </TabsTrigger>
          <TabsTrigger value="email" className="data-[state=active]:bg-white" data-testid="tab-email">
            <Mail className="h-4 w-4 mr-2" />
            Email
          </TabsTrigger>
          <TabsTrigger value="push" className="data-[state=active]:bg-white" data-testid="tab-push">
            <Bell className="h-4 w-4 mr-2" />
            Push
          </TabsTrigger>
          <TabsTrigger value="branding" className="data-[state=active]:bg-white" data-testid="tab-branding">
            <Palette className="h-4 w-4 mr-2" />
            Branding
          </TabsTrigger>
          <TabsTrigger value="data" className="data-[state=active]:bg-white data-[state=active]:text-red-700" data-testid="tab-data">
            <Database className="h-4 w-4 mr-2" />
            Dados
          </TabsTrigger>
        </TabsList>

        {/* Ticket Types Tab */}
        <TabsContent value="types">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Tipos de Ticket</CardTitle>
                <CardDescription>Configure as categorias de tickets disponíveis</CardDescription>
              </div>
              <Button onClick={() => openTypeDialog()} className="bg-orange-600 hover:bg-orange-700" data-testid="add-type-btn">
                <Plus className="h-4 w-4 mr-2" />
                Novo Tipo
              </Button>
            </CardHeader>
            <CardContent>
              {loadingTypes ? (
                <div className="flex justify-center py-8">
                  <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : (
                <div className="space-y-2">
                  {ticketTypes.map((type) => (
                    <div 
                      key={type.id}
                      className="flex items-center justify-between p-4 bg-zinc-50 rounded-lg hover:bg-zinc-100 transition-colors"
                      data-testid={`type-item-${type.code}`}
                    >
                      <div className="flex items-center gap-3">
                        <div 
                          className="w-4 h-4 rounded-full"
                          style={{ backgroundColor: type.color }}
                        />
                        <div>
                          <p className="font-semibold text-slate-900">{type.label}</p>
                          <p className="text-xs text-zinc-500 font-mono">{type.code}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => openTypeDialog(type)}
                          data-testid={`edit-type-${type.code}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm"
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                          onClick={() => deleteTicketType(type.id)}
                          data-testid={`delete-type-${type.code}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Statuses Tab */}
        <TabsContent value="statuses">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Estados de Ticket</CardTitle>
                <CardDescription>Configure os estados disponíveis para os tickets</CardDescription>
              </div>
              <Button onClick={() => openStatusDialog()} className="bg-orange-600 hover:bg-orange-700" data-testid="add-status-btn">
                <Plus className="h-4 w-4 mr-2" />
                Novo Estado
              </Button>
            </CardHeader>
            <CardContent>
              {loadingStatuses ? (
                <div className="flex justify-center py-8">
                  <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : (
                <div className="space-y-2">
                  {ticketStatuses.map((status) => (
                    <div 
                      key={status.id}
                      className="flex items-center justify-between p-4 bg-zinc-50 rounded-lg hover:bg-zinc-100 transition-colors"
                      data-testid={`status-item-${status.code}`}
                    >
                      <div className="flex items-center gap-3">
                        <GripVertical className="h-4 w-4 text-zinc-400" />
                        <div 
                          className="w-4 h-4 rounded-full"
                          style={{ backgroundColor: status.color }}
                        />
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="font-semibold text-slate-900">{status.label}</p>
                            {status.is_final && (
                              <Badge variant="outline" className="text-xs">Final</Badge>
                            )}
                          </div>
                          <p className="text-xs text-zinc-500 font-mono">{status.code}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => openStatusDialog(status)}
                          data-testid={`edit-status-${status.code}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm"
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                          onClick={() => deleteTicketStatus(status.id)}
                          data-testid={`delete-status-${status.code}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* SLA Tab */}
        <TabsContent value="sla">
          <div className="space-y-4">
            {/* Business Hours Card */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  Horário de Funcionamento
                </CardTitle>
                <CardDescription>Configure o horário útil para cálculo de SLA</CardDescription>
              </CardHeader>
              <CardContent>
                {loadingSla ? (
                  <div className="flex justify-center py-8">
                    <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Days Grid */}
                    <div className="grid gap-3">
                      {[
                        { key: 'monday', label: 'Segunda-feira' },
                        { key: 'tuesday', label: 'Terça-feira' },
                        { key: 'wednesday', label: 'Quarta-feira' },
                        { key: 'thursday', label: 'Quinta-feira' },
                        { key: 'friday', label: 'Sexta-feira' },
                        { key: 'saturday', label: 'Sábado' },
                        { key: 'sunday', label: 'Domingo' }
                      ].map(day => (
                        <div key={day.key} className="flex items-center gap-4 p-3 bg-zinc-50 rounded-lg">
                          <div className="w-32 font-medium text-slate-700">{day.label}</div>
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={!slaConfig[day.key]?.closed}
                              onChange={(e) => setSlaConfig({
                                ...slaConfig,
                                [day.key]: { ...slaConfig[day.key], closed: !e.target.checked }
                              })}
                              className="w-4 h-4 rounded border-zinc-300 text-orange-600 focus:ring-orange-500"
                            />
                            <span className="text-sm text-zinc-500 w-16">
                              {slaConfig[day.key]?.closed ? 'Fechado' : 'Aberto'}
                            </span>
                          </div>
                          {!slaConfig[day.key]?.closed && (
                            <>
                              <Input
                                type="time"
                                value={slaConfig[day.key]?.start || '08:30'}
                                onChange={(e) => setSlaConfig({
                                  ...slaConfig,
                                  [day.key]: { ...slaConfig[day.key], start: e.target.value }
                                })}
                                className="w-28"
                              />
                              <span className="text-zinc-400">—</span>
                              <Input
                                type="time"
                                value={slaConfig[day.key]?.end || '18:30'}
                                onChange={(e) => setSlaConfig({
                                  ...slaConfig,
                                  [day.key]: { ...slaConfig[day.key], end: e.target.value }
                                })}
                                className="w-28"
                              />
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* SLA per Type Card */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Tag className="h-5 w-5" />
                  SLA por Tipo de Ticket
                </CardTitle>
                <CardDescription>Tempo máximo de resposta em horas úteis para cada tipo</CardDescription>
              </CardHeader>
              <CardContent>
                {loadingSla ? (
                  <div className="flex justify-center py-8">
                    <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="sla-orcamento-mecanica">Orçamento Mecânica</Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id="sla-orcamento-mecanica"
                            type="number"
                            min="1"
                            max="168"
                            value={slaConfig.sla_orcamento_mecanica}
                            onChange={(e) => setSlaConfig({ ...slaConfig, sla_orcamento_mecanica: parseInt(e.target.value) || 8 })}
                            className="w-20"
                          />
                          <span className="text-sm text-zinc-500">horas</span>
                        </div>
                      </div>
                      
                      <div className="space-y-2">
                        <Label htmlFor="sla-orcamento-pneus">Orçamento Pneus</Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id="sla-orcamento-pneus"
                            type="number"
                            min="1"
                            max="168"
                            value={slaConfig.sla_orcamento_pneus}
                            onChange={(e) => setSlaConfig({ ...slaConfig, sla_orcamento_pneus: parseInt(e.target.value) || 8 })}
                            className="w-20"
                          />
                          <span className="text-sm text-zinc-500">horas</span>
                        </div>
                      </div>
                      
                      <div className="space-y-2">
                        <Label htmlFor="sla-informacao">Pedido de Informação</Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id="sla-informacao"
                            type="number"
                            min="1"
                            max="168"
                            value={slaConfig.sla_informacao}
                            onChange={(e) => setSlaConfig({ ...slaConfig, sla_informacao: parseInt(e.target.value) || 2 })}
                            className="w-20"
                          />
                          <span className="text-sm text-zinc-500">horas</span>
                        </div>
                      </div>
                      
                      <div className="space-y-2">
                        <Label htmlFor="sla-reclamacao">Reclamação</Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id="sla-reclamacao"
                            type="number"
                            min="1"
                            max="168"
                            value={slaConfig.sla_reclamacao}
                            onChange={(e) => setSlaConfig({ ...slaConfig, sla_reclamacao: parseInt(e.target.value) || 2 })}
                            className="w-20"
                          />
                          <span className="text-sm text-zinc-500">horas</span>
                        </div>
                      </div>
                      
                      <div className="space-y-2">
                        <Label htmlFor="sla-marcacao">Marcação</Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id="sla-marcacao"
                            type="number"
                            min="1"
                            max="168"
                            value={slaConfig.sla_marcacao}
                            onChange={(e) => setSlaConfig({ ...slaConfig, sla_marcacao: parseInt(e.target.value) || 3 })}
                            className="w-20"
                          />
                          <span className="text-sm text-zinc-500">horas</span>
                        </div>
                      </div>
                      
                      <div className="space-y-2">
                        <Label htmlFor="sla-interno">Interno</Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id="sla-interno"
                            type="number"
                            min="1"
                            max="168"
                            value={slaConfig.sla_interno}
                            onChange={(e) => setSlaConfig({ ...slaConfig, sla_interno: parseInt(e.target.value) || 8 })}
                            className="w-20"
                          />
                          <span className="text-sm text-zinc-500">horas</span>
                        </div>
                      </div>
                    </div>

                    {/* Default SLA */}
                    <div className="pt-4 border-t">
                      <div className="space-y-2">
                        <Label htmlFor="sla-default" className="text-amber-700 font-medium">SLA Default (Fallback)</Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id="sla-default"
                            type="number"
                            min="1"
                            max="168"
                            value={slaConfig.sla_default}
                            onChange={(e) => setSlaConfig({ ...slaConfig, sla_default: parseInt(e.target.value) || 2 })}
                            className="w-20"
                          />
                          <span className="text-sm text-zinc-500">horas</span>
                        </div>
                        <p className="text-xs text-zinc-500">
                          Usado quando o tipo de ticket não tem SLA específico definido
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Options Card */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertCircle className="h-5 w-5" />
                  Opções de Cálculo
                </CardTitle>
                <CardDescription>Configure como o SLA é calculado</CardDescription>
              </CardHeader>
              <CardContent>
                {loadingSla ? (
                  <div className="flex justify-center py-8">
                    <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Main Toggle */}
                    <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                      <input
                        type="checkbox"
                        id="sla-enabled"
                        checked={slaConfig.enabled}
                        onChange={(e) => setSlaConfig({ ...slaConfig, enabled: e.target.checked })}
                        className="w-4 h-4 rounded border-amber-400 text-orange-600 focus:ring-orange-500"
                      />
                      <Label htmlFor="sla-enabled" className="font-medium text-amber-800">
                        Ativar verificação automática de SLA
                      </Label>
                    </div>

                    {/* Option Toggles */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="flex items-center gap-3 p-4 bg-zinc-50 rounded-lg">
                        <input
                          type="checkbox"
                          id="use-business-hours"
                          checked={slaConfig.use_business_hours}
                          onChange={(e) => setSlaConfig({ ...slaConfig, use_business_hours: e.target.checked })}
                          className="w-4 h-4 rounded border-zinc-300 text-orange-600 focus:ring-orange-500"
                        />
                        <div>
                          <Label htmlFor="use-business-hours" className="font-medium text-slate-700">
                            Contar apenas em horário útil
                          </Label>
                          <p className="text-xs text-zinc-500 mt-1">
                            O tempo fora do horário de funcionamento não conta para o SLA
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 p-4 bg-zinc-50 rounded-lg">
                        <input
                          type="checkbox"
                          id="pause-aguarda-cliente"
                          checked={slaConfig.pause_on_aguarda_cliente}
                          onChange={(e) => setSlaConfig({ ...slaConfig, pause_on_aguarda_cliente: e.target.checked })}
                          className="w-4 h-4 rounded border-zinc-300 text-orange-600 focus:ring-orange-500"
                        />
                        <div>
                          <Label htmlFor="pause-aguarda-cliente" className="font-medium text-slate-700">
                            Pausar SLA em "Aguarda Cliente"
                          </Label>
                          <p className="text-xs text-zinc-500 mt-1">
                            O cronómetro pausa quando o ticket está à espera do cliente
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Save Button */}
                    <div className="flex justify-end pt-4 border-t">
                      <Button 
                        onClick={saveSlaConfig} 
                        disabled={savingSla}
                        className="bg-orange-600 hover:bg-orange-700"
                        data-testid="save-sla-btn"
                      >
                        {savingSla ? (
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                        ) : (
                          <Save className="h-4 w-4 mr-2" />
                        )}
                        Guardar Configuração
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Holidays Tab */}
        <TabsContent value="holidays">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5" />
                  Feriados
                </CardTitle>
                <CardDescription>
                  Configure os feriados que serão excluídos do cálculo de SLA
                </CardDescription>
              </div>
              <Button onClick={() => openHolidayDialog()} className="bg-orange-600 hover:bg-orange-700" data-testid="add-holiday-btn">
                <Plus className="h-4 w-4 mr-2" />
                Adicionar Feriado
              </Button>
            </CardHeader>
            <CardContent>
              {loadingHolidays ? (
                <div className="flex justify-center py-8">
                  <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : holidays.length === 0 ? (
                <div className="text-center py-8 text-zinc-500">
                  <Calendar className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>Nenhum feriado configurado</p>
                  <p className="text-sm">Adicione feriados para excluí-los do cálculo de SLA</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {holidays.map((holiday) => (
                    <div 
                      key={holiday.id} 
                      className={`flex items-center justify-between p-3 rounded-lg border ${holiday.active ? 'bg-white' : 'bg-zinc-50 opacity-60'}`}
                      data-testid={`holiday-${holiday.id}`}
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-24 text-sm font-mono text-zinc-600">
                          {holiday.date}
                        </div>
                        <div>
                          <span className="font-medium">{holiday.name}</span>
                          <div className="flex items-center gap-2 mt-1">
                            {holiday.is_recurring_annual && (
                              <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-200">
                                Anual
                              </Badge>
                            )}
                            <Badge variant="outline" className="text-xs">
                              {holiday.scope}
                            </Badge>
                            {!holiday.active && (
                              <Badge variant="outline" className="text-xs bg-zinc-100 text-zinc-500">
                                Inactivo
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          onClick={() => toggleHoliday(holiday.id)}
                          title={holiday.active ? 'Desactivar' : 'Activar'}
                          data-testid={`toggle-holiday-${holiday.id}`}
                        >
                          {holiday.active ? (
                            <ToggleRight className="h-5 w-5 text-green-600" />
                          ) : (
                            <ToggleLeft className="h-5 w-5 text-zinc-400" />
                          )}
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          onClick={() => openHolidayDialog(holiday)}
                          data-testid={`edit-holiday-${holiday.id}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          onClick={() => deleteHoliday(holiday.id)}
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                          data-testid={`delete-holiday-${holiday.id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Info box */}
              <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-100">
                <h4 className="font-medium text-blue-900 mb-2">Como funcionam os feriados?</h4>
                <ul className="text-sm text-blue-800 space-y-1">
                  <li>• Os feriados activos são excluídos do cálculo de tempo útil do SLA</li>
                  <li>• Feriados marcados como "Anual" repetem-se automaticamente todos os anos</li>
                  <li>• Pode desactivar temporariamente um feriado sem o eliminar</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Email Tab */}
        <TabsContent value="email">
          <div className="space-y-4">
            {/* SMTP Configuration */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Server className="h-5 w-5" />
                  Configuração SMTP
                </CardTitle>
                <CardDescription>Configure o servidor de email para envio de mensagens</CardDescription>
              </CardHeader>
              <CardContent>
                {loadingEmail ? (
                  <div className="flex justify-center py-8">
                    <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  <div className="space-y-6">
                    {/* Status */}
                    <div className={`flex items-center gap-3 p-4 rounded-lg ${
                      emailConfig.smtp_configured 
                        ? 'bg-emerald-50 border border-emerald-200' 
                        : 'bg-amber-50 border border-amber-200'
                    }`}>
                      {emailConfig.smtp_configured ? (
                        <>
                          <CheckCircle className="h-5 w-5 text-emerald-600" />
                          <div>
                            <p className="font-medium text-emerald-800">SMTP Configurado</p>
                            <p className="text-sm text-emerald-600">Servidor: {emailConfig.smtp_host}:{emailConfig.smtp_port}</p>
                          </div>
                        </>
                      ) : (
                        <>
                          <AlertCircle className="h-5 w-5 text-amber-600" />
                          <div>
                            <p className="font-medium text-amber-800">SMTP Não Configurado</p>
                            <p className="text-sm text-amber-600">Configure as definições abaixo para enviar emails</p>
                          </div>
                        </>
                      )}
                    </div>

                    {/* SMTP Server Settings */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="smtp-host">Servidor SMTP *</Label>
                        <Input
                          id="smtp-host"
                          type="text"
                          placeholder="smtp.gmail.com"
                          value={emailConfig.smtp_host || ''}
                          onChange={(e) => setEmailConfig({ ...emailConfig, smtp_host: e.target.value })}
                          className="w-full"
                          data-testid="smtp-host-input"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="smtp-port">Porta *</Label>
                        <Input
                          id="smtp-port"
                          type="number"
                          placeholder="587"
                          value={emailConfig.smtp_port || ''}
                          onChange={(e) => setEmailConfig({ ...emailConfig, smtp_port: parseInt(e.target.value) || 587 })}
                          className="w-full"
                          data-testid="smtp-port-input"
                        />
                        <p className="text-xs text-zinc-500">
                          Comum: 587 (TLS) ou 465 (SSL) ou 25
                        </p>
                      </div>
                    </div>

                    {/* SMTP Credentials */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="smtp-username">Username/Email *</Label>
                        <Input
                          id="smtp-username"
                          type="text"
                          placeholder="seu@email.com"
                          value={emailConfig.smtp_username || ''}
                          onChange={(e) => setEmailConfig({ ...emailConfig, smtp_username: e.target.value })}
                          className="w-full"
                          data-testid="smtp-username-input"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="smtp-password">Senha</Label>
                        <div className="relative">
                          <Input
                            id="smtp-password"
                            type={showPassword ? 'text' : 'password'}
                            placeholder="••••••••"
                            value={emailConfig.smtp_password || ''}
                            onChange={(e) => setEmailConfig({ ...emailConfig, smtp_password: e.target.value })}
                            className="w-full pr-10"
                            data-testid="smtp-password-input"
                          />
                          <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-700"
                          >
                            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                        <p className="text-xs text-zinc-500">
                          Para Gmail, use uma App Password
                        </p>
                      </div>
                    </div>

                    {/* SSL/TLS Options */}
                    <div className="flex flex-wrap gap-6 p-4 bg-zinc-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          id="smtp-use-tls"
                          checked={emailConfig.smtp_use_tls || false}
                          onChange={(e) => setEmailConfig({ ...emailConfig, smtp_use_tls: e.target.checked, smtp_use_ssl: e.target.checked ? false : emailConfig.smtp_use_ssl })}
                          className="w-4 h-4 rounded border-zinc-300 text-orange-600 focus:ring-orange-500"
                        />
                        <Label htmlFor="smtp-use-tls" className="text-sm">
                          Usar STARTTLS (Porta 587)
                        </Label>
                      </div>
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          id="smtp-use-ssl"
                          checked={emailConfig.smtp_use_ssl || false}
                          onChange={(e) => setEmailConfig({ ...emailConfig, smtp_use_ssl: e.target.checked, smtp_use_tls: e.target.checked ? false : emailConfig.smtp_use_tls })}
                          className="w-4 h-4 rounded border-zinc-300 text-orange-600 focus:ring-orange-500"
                        />
                        <Label htmlFor="smtp-use-ssl" className="text-sm">
                          Usar SSL/TLS (Porta 465)
                        </Label>
                      </div>
                    </div>

                    {/* Email Identity */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t">
                      <div className="space-y-2">
                        <Label htmlFor="email-from">Email Remetente</Label>
                        <Input
                          id="email-from"
                          type="email"
                          placeholder="rececao@empresa.com"
                          value={emailConfig.email_from || ''}
                          onChange={(e) => setEmailConfig({ ...emailConfig, email_from: e.target.value })}
                          className="w-full"
                          data-testid="email-from-input"
                        />
                        <p className="text-xs text-zinc-500">
                          Endereço que aparece como remetente
                        </p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="email-from-name">Nome do Remetente</Label>
                        <Input
                          id="email-from-name"
                          type="text"
                          placeholder="PDPV Tickets"
                          value={emailConfig.email_from_name || ''}
                          onChange={(e) => setEmailConfig({ ...emailConfig, email_from_name: e.target.value })}
                          className="w-full"
                          data-testid="email-from-name-input"
                        />
                      </div>
                    </div>

                    {/* Frontend URL */}
                    <div className="space-y-2">
                      <Label htmlFor="frontend-url">URL do Frontend</Label>
                      <Input
                        id="frontend-url"
                        type="url"
                        placeholder="https://seu-dominio.com"
                        value={emailConfig.frontend_url || ''}
                        onChange={(e) => setEmailConfig({ ...emailConfig, frontend_url: e.target.value })}
                        className="w-full"
                        data-testid="frontend-url-input"
                      />
                      <p className="text-xs text-zinc-500">
                        URL usado nos links enviados por email
                      </p>
                    </div>

                    <div className="flex justify-end pt-4 border-t">
                      <Button 
                        onClick={saveEmailConfig} 
                        disabled={savingEmail}
                        className="bg-orange-600 hover:bg-orange-700"
                        data-testid="save-email-btn"
                      >
                        {savingEmail ? (
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                        ) : (
                          <Save className="h-4 w-4 mr-2" />
                        )}
                        Guardar Configuração
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Test Email */}
            <Card>
              <CardHeader>
                <CardTitle>Testar Envio de Email</CardTitle>
                <CardDescription>Envie um email de teste para verificar a configuração</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-end gap-4">
                  <div className="flex-1 space-y-2">
                    <Label htmlFor="test-email">Email de Destino</Label>
                    <Input
                      id="test-email"
                      type="email"
                      placeholder="seu@email.com"
                      value={testEmail}
                      onChange={(e) => setTestEmail(e.target.value)}
                      className="w-full"
                      data-testid="test-email-input"
                    />
                  </div>
                  <Button 
                    onClick={sendTestEmail} 
                    disabled={sendingTest || (!emailConfig.smtp_configured && !emailConfig.resend_configured)}
                    className="bg-emerald-600 hover:bg-emerald-700"
                    data-testid="send-test-email-btn"
                  >
                    {sendingTest ? (
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                    ) : (
                      <Send className="h-4 w-4 mr-2" />
                    )}
                    Enviar Teste
                  </Button>
                  {!emailConfig.smtp_configured && !emailConfig.resend_configured && (
                    <p className="text-xs text-amber-600 mt-2">
                      Configure SMTP acima ou RESEND_API_KEY no servidor para enviar emails
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Push Tab */}
        <TabsContent value="push">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Notificações Push (Web Push)
              </CardTitle>
              <CardDescription>Configuração de notificações push para browsers</CardDescription>
            </CardHeader>
            <CardContent>
              {loadingPush ? (
                <div className="flex justify-center py-8">
                  <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Status */}
                  <div className={`flex items-center gap-3 p-4 rounded-lg ${
                    pushConfig.vapid_configured 
                      ? 'bg-emerald-50 border border-emerald-200' 
                      : 'bg-amber-50 border border-amber-200'
                  }`}>
                    {pushConfig.vapid_configured ? (
                      <>
                        <CheckCircle className="h-5 w-5 text-emerald-600" />
                        <div>
                          <p className="font-medium text-emerald-800">VAPID Configurado</p>
                          <p className="text-sm text-emerald-600">Notificações push estão ativas</p>
                        </div>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="h-5 w-5 text-amber-600" />
                        <div className="flex-1">
                          <p className="font-medium text-amber-800">VAPID Não Configurado</p>
                          <p className="text-sm text-amber-600">Web Push desativado. Gere as chaves abaixo para ativar.</p>
                        </div>
                        <Button
                          size="sm"
                          onClick={generateVapidKeys}
                          disabled={generatingKeys}
                          className="bg-amber-600 hover:bg-amber-700 text-white shrink-0"
                          data-testid="generate-vapid-keys-btn"
                        >
                          {generatingKeys ? (
                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                          ) : null}
                          {generatingKeys ? 'A gerar...' : 'Gerar Chaves'}
                        </Button>
                      </>
                    )}
                  </div>

                  {/* Stats */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 bg-zinc-50 rounded-lg">
                      <p className="text-sm text-zinc-500">Dispositivos Registados</p>
                      <p className="text-2xl font-bold text-zinc-900">{pushConfig.subscriptions_count}</p>
                    </div>
                    <div className="p-4 bg-zinc-50 rounded-lg">
                      <p className="text-sm text-zinc-500">Estado</p>
                      <p className="text-lg font-semibold text-zinc-900">
                        {pushConfig.vapid_configured ? 'Ativo' : 'Inativo'}
                      </p>
                    </div>
                  </div>

                  {/* VAPID Public Key */}
                  {pushConfig.vapid_configured && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label>Chave Pública VAPID</Label>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={generateVapidKeys}
                          disabled={generatingKeys}
                          className="text-xs border-zinc-300"
                          data-testid="regenerate-vapid-keys-btn"
                        >
                          {generatingKeys ? 'A gerar...' : 'Regenerar Chaves'}
                        </Button>
                      </div>
                      <div className="p-3 bg-zinc-100 rounded-lg font-mono text-xs break-all">
                        {pushConfig.vapid_public_key}
                      </div>
                      <p className="text-xs text-zinc-500">
                        Esta chave é usada pelo browser para subscrever notificações push. Ao regenerar, os utilizadores terão de reativar as notificações.
                      </p>
                    </div>
                  )}

                  {/* Instructions */}
                  <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                    <h4 className="font-medium text-blue-800 mb-2">Como funciona?</h4>
                    <ul className="text-sm text-blue-700 space-y-1">
                      <li>1. Os utilizadores ativam notificações no sino do menu</li>
                      <li>2. O browser regista o dispositivo no servidor</li>
                      <li>3. Quando há novos tickets ou atualizações, recebem notificação</li>
                    </ul>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Branding Tab */}
        <TabsContent value="branding">
          <div className="space-y-4">
            {/* Company Info */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Building className="h-5 w-5" />
                  Informação da Empresa
                </CardTitle>
                <CardDescription>Configure o nome, logo e contactos da empresa</CardDescription>
              </CardHeader>
              <CardContent>
                {loadingBranding ? (
                  <div className="flex justify-center py-8">
                    <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  <div className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="company-name">Nome da Empresa</Label>
                        <Input
                          id="company-name"
                          value={brandingConfig.company_name || ''}
                          onChange={(e) => setBrandingConfig({ ...brandingConfig, company_name: e.target.value })}
                          placeholder="PDPV"
                          data-testid="company-name-input"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="company-subtitle">Subtítulo / Slogan</Label>
                        <Input
                          id="company-subtitle"
                          value={brandingConfig.company_subtitle || ''}
                          onChange={(e) => setBrandingConfig({ ...brandingConfig, company_subtitle: e.target.value })}
                          placeholder="Pneus de Pedro V."
                          data-testid="company-subtitle-input"
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="company-logo">URL do Logo</Label>
                      <Input
                        id="company-logo"
                        value={brandingConfig.company_logo_url || ''}
                        onChange={(e) => setBrandingConfig({ ...brandingConfig, company_logo_url: e.target.value })}
                        placeholder="https://exemplo.com/logo.png"
                        data-testid="company-logo-input"
                      />
                      <p className="text-xs text-zinc-500">URL de uma imagem para usar como logo nos emails e página de orçamento</p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="primary-color">Cor Principal</Label>
                        <div className="flex gap-2">
                          <Input
                            id="primary-color"
                            type="color"
                            value={brandingConfig.primary_color || '#f97316'}
                            onChange={(e) => setBrandingConfig({ ...brandingConfig, primary_color: e.target.value })}
                            className="w-16 h-10 p-1 cursor-pointer"
                          />
                          <Input
                            value={brandingConfig.primary_color || '#f97316'}
                            onChange={(e) => setBrandingConfig({ ...brandingConfig, primary_color: e.target.value })}
                            placeholder="#f97316"
                            className="flex-1"
                          />
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="secondary-color">Cor Secundária</Label>
                        <div className="flex gap-2">
                          <Input
                            id="secondary-color"
                            type="color"
                            value={brandingConfig.secondary_color || '#1f2937'}
                            onChange={(e) => setBrandingConfig({ ...brandingConfig, secondary_color: e.target.value })}
                            className="w-16 h-10 p-1 cursor-pointer"
                          />
                          <Input
                            value={brandingConfig.secondary_color || '#1f2937'}
                            onChange={(e) => setBrandingConfig({ ...brandingConfig, secondary_color: e.target.value })}
                            placeholder="#1f2937"
                            className="flex-1"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t">
                      <div className="space-y-2">
                        <Label htmlFor="company-phone">Telefone</Label>
                        <Input
                          id="company-phone"
                          value={brandingConfig.company_phone || ''}
                          onChange={(e) => setBrandingConfig({ ...brandingConfig, company_phone: e.target.value })}
                          placeholder="+351 912 345 678"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="company-email">Email de Contacto</Label>
                        <Input
                          id="company-email"
                          type="email"
                          value={brandingConfig.company_email || ''}
                          onChange={(e) => setBrandingConfig({ ...brandingConfig, company_email: e.target.value })}
                          placeholder="geral@empresa.pt"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="company-address">Morada</Label>
                        <Input
                          id="company-address"
                          value={brandingConfig.company_address || ''}
                          onChange={(e) => setBrandingConfig({ ...brandingConfig, company_address: e.target.value })}
                          placeholder="Rua Exemplo, 123, Lisboa"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="company-website">Website</Label>
                        <Input
                          id="company-website"
                          value={brandingConfig.company_website || ''}
                          onChange={(e) => setBrandingConfig({ ...brandingConfig, company_website: e.target.value })}
                          placeholder="https://www.empresa.pt"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Email Templates */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  Templates de Email
                </CardTitle>
                <CardDescription>Personalize os textos dos emails de orçamento</CardDescription>
              </CardHeader>
              <CardContent>
                {loadingBranding ? (
                  <div className="flex justify-center py-8">
                    <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  <div className="space-y-6">
                    <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm">
                      <p className="font-medium text-blue-800 mb-2">Variáveis disponíveis:</p>
                      <code className="text-blue-700">
                        {'{customer_name}'} {'{ticket_number}'} {'{quote_value}'} {'{expiry_date}'}
                      </code>
                    </div>

                    <div className="space-y-2">
                      <Label>Assunto do Email</Label>
                      <Input
                        value={brandingConfig.email_templates?.quote_email_subject || '[Ticket #{ticket_number}] Orçamento - {quote_value}€'}
                        onChange={(e) => setBrandingConfig({ 
                          ...brandingConfig, 
                          email_templates: { ...brandingConfig.email_templates, quote_email_subject: e.target.value }
                        })}
                        placeholder="[Ticket #{ticket_number}] Orçamento - {quote_value}€"
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>Saudação</Label>
                      <Input
                        value={brandingConfig.email_templates?.quote_email_greeting || 'Olá {customer_name},'}
                        onChange={(e) => setBrandingConfig({ 
                          ...brandingConfig, 
                          email_templates: { ...brandingConfig.email_templates, quote_email_greeting: e.target.value }
                        })}
                        placeholder="Olá {customer_name},"
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>Texto de Introdução</Label>
                      <Textarea
                        value={brandingConfig.email_templates?.quote_email_intro || 'Preparámos um orçamento para si referente ao seu pedido.'}
                        onChange={(e) => setBrandingConfig({ 
                          ...brandingConfig, 
                          email_templates: { ...brandingConfig.email_templates, quote_email_intro: e.target.value }
                        })}
                        placeholder="Preparámos um orçamento para si referente ao seu pedido."
                        className="min-h-[80px]"
                      />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label>Texto do Botão</Label>
                        <Input
                          value={brandingConfig.email_templates?.quote_email_button_text || 'Ver Orçamento'}
                          onChange={(e) => setBrandingConfig({ 
                            ...brandingConfig, 
                            email_templates: { ...brandingConfig.email_templates, quote_email_button_text: e.target.value }
                          })}
                          placeholder="Ver Orçamento"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Texto de Validade</Label>
                        <Input
                          value={brandingConfig.email_templates?.quote_email_footer || 'Este link é válido até {expiry_date}.'}
                          onChange={(e) => setBrandingConfig({ 
                            ...brandingConfig, 
                            email_templates: { ...brandingConfig.email_templates, quote_email_footer: e.target.value }
                          })}
                          placeholder="Este link é válido até {expiry_date}."
                        />
                      </div>
                    </div>

                    <div className="pt-4 border-t">
                      <h4 className="font-medium mb-4">Página de Resposta ao Orçamento</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="space-y-4 p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
                          <p className="text-sm font-medium text-emerald-800">Quando Aceite:</p>
                          <div className="space-y-2">
                            <Label className="text-emerald-700">Título</Label>
                            <Input
                              value={brandingConfig.email_templates?.quote_page_accepted_title || 'Orçamento Aceite!'}
                              onChange={(e) => setBrandingConfig({ 
                                ...brandingConfig, 
                                email_templates: { ...brandingConfig.email_templates, quote_page_accepted_title: e.target.value }
                              })}
                              className="bg-white"
                            />
                          </div>
                          <div className="space-y-2">
                            <Label className="text-emerald-700">Mensagem</Label>
                            <Textarea
                              value={brandingConfig.email_templates?.quote_page_accepted_message || 'Obrigado pela sua resposta. Entraremos em contacto em breve para agendar o serviço.'}
                              onChange={(e) => setBrandingConfig({ 
                                ...brandingConfig, 
                                email_templates: { ...brandingConfig.email_templates, quote_page_accepted_message: e.target.value }
                              })}
                              className="bg-white min-h-[80px]"
                            />
                          </div>
                        </div>

                        <div className="space-y-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                          <p className="text-sm font-medium text-red-800">Quando Recusado:</p>
                          <div className="space-y-2">
                            <Label className="text-red-700">Título</Label>
                            <Input
                              value={brandingConfig.email_templates?.quote_page_rejected_title || 'Orçamento Recusado'}
                              onChange={(e) => setBrandingConfig({ 
                                ...brandingConfig, 
                                email_templates: { ...brandingConfig.email_templates, quote_page_rejected_title: e.target.value }
                              })}
                              className="bg-white"
                            />
                          </div>
                          <div className="space-y-2">
                            <Label className="text-red-700">Mensagem</Label>
                            <Textarea
                              value={brandingConfig.email_templates?.quote_page_rejected_message || 'Obrigado pela sua resposta. Se precisar de ajuda, não hesite em contactar-nos.'}
                              onChange={(e) => setBrandingConfig({ 
                                ...brandingConfig, 
                                email_templates: { ...brandingConfig.email_templates, quote_page_rejected_message: e.target.value }
                              })}
                              className="bg-white min-h-[80px]"
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex justify-end pt-4 border-t">
                      <Button 
                        onClick={saveBrandingConfig} 
                        disabled={savingBranding}
                        className="bg-orange-600 hover:bg-orange-700"
                        data-testid="save-branding-btn"
                      >
                        {savingBranding ? (
                          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                        ) : (
                          <Save className="h-4 w-4 mr-2" />
                        )}
                        Guardar Branding e Templates
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Data Management Tab */}
        <TabsContent value="data">
          <Card className="border-red-200">
            <CardHeader>
              <CardTitle className="text-red-700 flex items-center gap-2">
                <Database className="h-5 w-5" />
                Gestão de Dados
              </CardTitle>
              <CardDescription>
                Ações de manutenção da base de dados. Use com cuidado!
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg space-y-4">
                <div>
                  <h4 className="font-semibold text-red-800">Limpar Todos os Tickets</h4>
                  <p className="text-sm text-red-600 mt-1">
                    Esta ação irá apagar permanentemente todos os tickets, mensagens, notas, anexos, lembretes e notificações.
                    Os utilizadores, configurações, clientes e veículos serão mantidos.
                  </p>
                </div>
                <Button
                  variant="destructive"
                  onClick={async () => {
                    if (!window.confirm('⚠️ TEM A CERTEZA?\n\nEsta ação irá apagar TODOS os tickets e dados relacionados.\n\nEsta ação é IRREVERSÍVEL!')) return;
                    if (!window.confirm('🔴 ÚLTIMA CONFIRMAÇÃO\n\nDigite "CONFIRMO" na próxima janela para continuar.')) return;
                    const confirmation = window.prompt('Digite CONFIRMO para apagar todos os tickets:');
                    if (confirmation !== 'CONFIRMO') {
                      toast.error('Operação cancelada');
                      return;
                    }
                    try {
                      const response = await axios.delete(`${API_URL}/api/admin/clear-all-tickets`, { headers: getAuthHeaders() });
                      toast.success(`✅ ${response.data.total_deleted} registos apagados com sucesso!`);
                    } catch (error) {
                      toast.error(error.response?.data?.detail || 'Erro ao limpar dados');
                    }
                  }}
                  className="bg-red-600 hover:bg-red-700"
                  data-testid="clear-all-tickets-btn"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Limpar Todos os Tickets
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Type Dialog */}
      <Dialog open={typeDialogOpen} onOpenChange={setTypeDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingType ? 'Editar Tipo' : 'Novo Tipo de Ticket'}</DialogTitle>
            <DialogDescription>
              Configure as propriedades do tipo de ticket
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="type-code">Código</Label>
              <Input
                id="type-code"
                placeholder="ex: ORCAMENTO_PNEUS"
                value={typeForm.code}
                onChange={(e) => setTypeForm({ ...typeForm, code: e.target.value.toUpperCase().replace(/\s+/g, '_') })}
                disabled={!!editingType}
                data-testid="type-code-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="type-label">Nome</Label>
              <Input
                id="type-label"
                placeholder="ex: Orçamento Pneus"
                value={typeForm.label}
                onChange={(e) => setTypeForm({ ...typeForm, label: e.target.value })}
                data-testid="type-label-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="type-color">Cor</Label>
              <div className="flex items-center gap-3">
                <input
                  id="type-color"
                  type="color"
                  value={typeForm.color}
                  onChange={(e) => setTypeForm({ ...typeForm, color: e.target.value })}
                  className="w-12 h-10 rounded cursor-pointer"
                />
                <Input
                  value={typeForm.color}
                  onChange={(e) => setTypeForm({ ...typeForm, color: e.target.value })}
                  className="w-28 font-mono"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTypeDialogOpen(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={saveTicketType} 
              disabled={savingType}
              className="bg-orange-600 hover:bg-orange-700"
              data-testid="save-type-btn"
            >
              {savingType ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                'Guardar'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Status Dialog */}
      <Dialog open={statusDialogOpen} onOpenChange={setStatusDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingStatus ? 'Editar Estado' : 'Novo Estado de Ticket'}</DialogTitle>
            <DialogDescription>
              Configure as propriedades do estado de ticket
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="status-code">Código</Label>
              <Input
                id="status-code"
                placeholder="ex: EM_TRATAMENTO"
                value={statusForm.code}
                onChange={(e) => setStatusForm({ ...statusForm, code: e.target.value.toUpperCase().replace(/\s+/g, '_') })}
                disabled={!!editingStatus}
                data-testid="status-code-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="status-label">Nome</Label>
              <Input
                id="status-label"
                placeholder="ex: Em Tratamento"
                value={statusForm.label}
                onChange={(e) => setStatusForm({ ...statusForm, label: e.target.value })}
                data-testid="status-label-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="status-color">Cor</Label>
              <div className="flex items-center gap-3">
                <input
                  id="status-color"
                  type="color"
                  value={statusForm.color}
                  onChange={(e) => setStatusForm({ ...statusForm, color: e.target.value })}
                  className="w-12 h-10 rounded cursor-pointer"
                />
                <Input
                  value={statusForm.color}
                  onChange={(e) => setStatusForm({ ...statusForm, color: e.target.value })}
                  className="w-28 font-mono"
                />
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 bg-zinc-50 rounded-lg">
              <input
                type="checkbox"
                id="status-final"
                checked={statusForm.is_final}
                onChange={(e) => setStatusForm({ ...statusForm, is_final: e.target.checked })}
                className="w-4 h-4 rounded border-zinc-300 text-orange-600 focus:ring-orange-500"
              />
              <Label htmlFor="status-final" className="text-sm">
                Estado final (fecha o ticket)
              </Label>
            </div>
            <div className="flex items-center gap-3 p-3 bg-amber-50 rounded-lg border border-amber-200">
              <input
                type="checkbox"
                id="status-auto"
                checked={statusForm.is_auto || false}
                onChange={(e) => setStatusForm({ ...statusForm, is_auto: e.target.checked })}
                className="w-4 h-4 rounded border-zinc-300 text-amber-600 focus:ring-amber-500"
              />
              <div>
                <Label htmlFor="status-auto" className="text-sm font-medium">
                  Estado automático
                </Label>
                <p className="text-xs text-amber-700">
                  Não aparece no dropdown manual (ex: resposta do cliente)
                </p>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStatusDialogOpen(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={saveTicketStatus} 
              disabled={savingStatus}
              className="bg-orange-600 hover:bg-orange-700"
              data-testid="save-status-btn"
            >
              {savingStatus ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                'Guardar'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Holiday Dialog */}
      <Dialog open={holidayDialogOpen} onOpenChange={setHolidayDialogOpen}>
        <DialogContent data-testid="holiday-dialog">
          <DialogHeader>
            <DialogTitle>{editingHoliday ? 'Editar Feriado' : 'Novo Feriado'}</DialogTitle>
            <DialogDescription>
              {editingHoliday ? 'Edite os dados do feriado' : 'Configure um novo feriado para excluir do SLA'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="holiday-date">Data *</Label>
              <Input
                id="holiday-date"
                type="date"
                value={holidayForm.date}
                onChange={(e) => setHolidayForm({ ...holidayForm, date: e.target.value })}
                data-testid="holiday-date-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="holiday-name">Nome *</Label>
              <Input
                id="holiday-name"
                value={holidayForm.name}
                onChange={(e) => setHolidayForm({ ...holidayForm, name: e.target.value })}
                placeholder="Ex: Natal, 25 de Abril..."
                data-testid="holiday-name-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="holiday-scope">Âmbito</Label>
              <select
                id="holiday-scope"
                value={holidayForm.scope}
                onChange={(e) => setHolidayForm({ ...holidayForm, scope: e.target.value })}
                className="w-full px-3 py-2 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500"
                data-testid="holiday-scope-select"
              >
                <option value="nacional">Nacional</option>
                <option value="local">Local</option>
              </select>
            </div>
            <div className="flex items-center gap-3 p-3 bg-blue-50 rounded-lg border border-blue-100">
              <input
                type="checkbox"
                id="holiday-recurring"
                checked={holidayForm.is_recurring_annual}
                onChange={(e) => setHolidayForm({ ...holidayForm, is_recurring_annual: e.target.checked })}
                className="w-4 h-4 rounded border-zinc-300 text-orange-600 focus:ring-orange-500"
                data-testid="holiday-recurring-checkbox"
              />
              <div>
                <Label htmlFor="holiday-recurring" className="text-sm font-medium">
                  Feriado anual recorrente
                </Label>
                <p className="text-xs text-blue-700">
                  Repete-se automaticamente todos os anos na mesma data
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 bg-zinc-50 rounded-lg border">
              <input
                type="checkbox"
                id="holiday-active"
                checked={holidayForm.active}
                onChange={(e) => setHolidayForm({ ...holidayForm, active: e.target.checked })}
                className="w-4 h-4 rounded border-zinc-300 text-green-600 focus:ring-green-500"
                data-testid="holiday-active-checkbox"
              />
              <div>
                <Label htmlFor="holiday-active" className="text-sm font-medium">
                  Feriado activo
                </Label>
                <p className="text-xs text-zinc-500">
                  Apenas feriados activos são excluídos do cálculo de SLA
                </p>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setHolidayDialogOpen(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={saveHoliday} 
              disabled={savingHoliday}
              className="bg-orange-600 hover:bg-orange-700"
              data-testid="save-holiday-btn"
            >
              {savingHoliday ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                'Guardar'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminSettings;
