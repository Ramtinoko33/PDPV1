import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import { toast } from 'sonner';
import {
  AlertTriangle, Bell, CheckCircle2, Clock, XCircle, Image,
  ArrowRight, RefreshCw, Search, Trash2, Eye, ChevronLeft,
  ChevronRight, Zap, Settings, User, Car, FileText,
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// SLA color helper: Verde <1h, Amarelo 1-2h, Vermelho >2h
const getSlaInfo = (createdAt) => {
  if (!createdAt) return { color: 'bg-zinc-100 text-zinc-600', label: '--', minutes: 0 };
  const now = new Date();
  const created = new Date(createdAt);
  const diffMs = now - created;
  const diffMin = Math.floor(diffMs / 60000);
  const hours = Math.floor(diffMin / 60);
  const mins = diffMin % 60;

  let label = '';
  if (hours > 0) label = `${hours}h ${mins}m`;
  else label = `${mins}m`;

  if (diffMin < 60) {
    return { color: 'bg-emerald-100 text-emerald-800 border-emerald-300', label, minutes: diffMin };
  } else if (diffMin < 120) {
    return { color: 'bg-amber-100 text-amber-800 border-amber-300', label, minutes: diffMin };
  } else {
    return { color: 'bg-red-100 text-red-800 border-red-300', label, minutes: diffMin };
  }
};

const statusConfig = {
  pending: { label: 'Pendente', color: 'bg-amber-100 text-amber-800', icon: Clock },
  converted: { label: 'Convertido', color: 'bg-emerald-100 text-emerald-800', icon: CheckCircle2 },
  dismissed: { label: 'Descartado', color: 'bg-zinc-100 text-zinc-600', icon: XCircle },
};

const AlertsPage = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();

  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState({ pending: 0, converted: 0, dismissed: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [moduleEnabled, setModuleEnabled] = useState(false);
  const [checkingModule, setCheckingModule] = useState(true);

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [total, setTotal] = useState(0);

  // Filters
  const [filterStatus, setFilterStatus] = useState('pending');
  const [searchTerm, setSearchTerm] = useState('');

  // Detail modal
  const [detailAlert, setDetailAlert] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [photoUrl, setPhotoUrl] = useState(null);
  const [loadingPhoto, setLoadingPhoto] = useState(false);

  // Edit fields
  const [editPlate, setEditPlate] = useState('');
  const [editName, setEditName] = useState('');
  const [editItems, setEditItems] = useState('');
  const [saving, setSaving] = useState(false);

  // Convert modal (intake-style)
  const [convertOpen, setConvertOpen] = useState(false);
  const [convertData, setConvertData] = useState({
    customer_name: '', customer_phone: '', customer_email: '',
    vehicle_plate: '', ticket_type: 'ORCAMENTO_MECANICA',
    description: '', assigned_to: ''
  });
  const [converting, setConverting] = useState(false);
  const [customerSearchResults, setCustomerSearchResults] = useState([]);
  const [searchingCustomer, setSearchingCustomer] = useState(false);
  const [showCustomerDropdown, setShowCustomerDropdown] = useState(false);
  const searchTimeoutRef = { current: null };

  // Users for assignment
  const [users, setUsers] = useState([]);
  // Ticket types
  const [ticketTypes, setTicketTypes] = useState([]);

  // Webhook setup
  const [settingUpWebhook, setSettingUpWebhook] = useState(false);

  // Check module
  useEffect(() => {
    const checkModule = async () => {
      try {
        const response = await axios.get(`${API_URL}/api/modules/status`, {
          headers: getAuthHeaders()
        });
        setModuleEnabled(response.data.modules?.telegram_alerts === true);
      } catch (error) {
        setModuleEnabled(false);
      } finally {
        setCheckingModule(false);
      }
    };
    checkModule();
  }, [getAuthHeaders]);

  // Fetch alerts
  const fetchAlerts = useCallback(async () => {
    if (!moduleEnabled) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('page', page);
      params.append('page_size', pageSize);
      if (filterStatus !== 'all') params.append('status', filterStatus);

      const response = await axios.get(`${API_URL}/api/telegram-alerts/alerts?${params.toString()}`, {
        headers: getAuthHeaders()
      });
      let items = response.data.alerts || [];
      // Client-side search
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        items = items.filter(a =>
          (a.license_plate || '').toLowerCase().includes(term) ||
          (a.client_name || '').toLowerCase().includes(term) ||
          (a.raw_text || '').toLowerCase().includes(term) ||
          (a.created_by?.name || '').toLowerCase().includes(term)
        );
      }
      setAlerts(items);
      setTotal(response.data.total || 0);
    } catch (error) {
      if (error.response?.status !== 403) {
        toast.error('Erro ao carregar alertas');
      }
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders, moduleEnabled, page, pageSize, filterStatus, searchTerm]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    if (!moduleEnabled) return;
    try {
      const response = await axios.get(`${API_URL}/api/telegram-alerts/alerts/stats`, {
        headers: getAuthHeaders()
      });
      setStats(response.data);
    } catch (error) {
      // silent
    }
  }, [getAuthHeaders, moduleEnabled]);

  // Fetch users and ticket types
  useEffect(() => {
    if (!moduleEnabled) return;
    const fetchMeta = async () => {
      try {
        const [usersRes, typesRes] = await Promise.all([
          axios.get(`${API_URL}/api/users`, { headers: getAuthHeaders() }),
          axios.get(`${API_URL}/api/ticket-types`, { headers: getAuthHeaders() }),
        ]);
        setUsers(usersRes.data || []);
        setTicketTypes(typesRes.data || []);
      } catch (e) {
        // silent
      }
    };
    fetchMeta();
  }, [getAuthHeaders, moduleEnabled]);

  useEffect(() => {
    if (moduleEnabled) {
      fetchAlerts();
      fetchStats();
    }
  }, [moduleEnabled, fetchAlerts, fetchStats]);

  // Auto-refresh every 30s
  useEffect(() => {
    if (!moduleEnabled) return;
    const interval = setInterval(() => {
      fetchAlerts();
      fetchStats();
    }, 30000);
    return () => clearInterval(interval);
  }, [moduleEnabled, fetchAlerts, fetchStats]);

  // Open detail
  const openDetail = async (alert) => {
    setDetailAlert(alert);
    setEditPlate(alert.license_plate || '');
    setEditName(alert.client_name || '');
    setEditItems((alert.items || []).join(', '));
    setPhotoUrl(null);
    setDetailOpen(true);

    // Load photo
    if (alert.attachments?.length > 0) {
      setLoadingPhoto(true);
      try {
        const att = alert.attachments[0];
        const resp = await axios.get(
          `${API_URL}/api/telegram-alerts/alerts/${alert.id}/photo/${att.id}`,
          { headers: getAuthHeaders() }
        );
        if (resp.data.url) {
          setPhotoUrl(resp.data.url);
        } else if (resp.data.base64) {
          setPhotoUrl(`data:${resp.data.file_type || 'image/jpeg'};base64,${resp.data.base64}`);
        }
      } catch (e) {
        // photo failed silently
      } finally {
        setLoadingPhoto(false);
      }
    }
  };

  // Save edits
  const handleSave = async () => {
    if (!detailAlert) return;
    setSaving(true);
    try {
      const items = editItems.split(',').map(s => s.trim()).filter(Boolean);
      await axios.put(
        `${API_URL}/api/telegram-alerts/alerts/${detailAlert.id}`,
        { license_plate: editPlate || null, client_name: editName || null, items },
        { headers: getAuthHeaders() }
      );
      toast.success('Alerta atualizado');
      setDetailAlert(prev => ({ ...prev, license_plate: editPlate, client_name: editName, items }));
      fetchAlerts();
      fetchStats();
    } catch (e) {
      toast.error('Erro ao guardar');
    } finally {
      setSaving(false);
    }
  };

  // Customer search (mirrors IntakePage)
  const searchCustomerByField = async (field, value) => {
    if (!value || value.length < 2) {
      setCustomerSearchResults([]);
      setShowCustomerDropdown(false);
      return;
    }
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(async () => {
      setSearchingCustomer(true);
      try {
        const params = new URLSearchParams();
        params.append(field, value);
        const response = await axios.get(`${API_URL}/api/customers/search?${params.toString()}`, {
          headers: getAuthHeaders()
        });
        const results = response.data || [];
        setCustomerSearchResults(results);
        if (results.length === 1) {
          selectCustomer(results[0]);
          setShowCustomerDropdown(false);
        } else if (results.length > 1) {
          setShowCustomerDropdown(true);
        } else {
          setShowCustomerDropdown(false);
        }
      } catch (e) { /* silent */ }
      finally { setSearchingCustomer(false); }
    }, 500);
  };

  const selectCustomer = (customer) => {
    setConvertData(prev => ({
      ...prev,
      customer_name: customer.name || prev.customer_name,
      customer_phone: customer.phone || prev.customer_phone,
      customer_email: customer.email || prev.customer_email,
      vehicle_plate: customer.plates?.[0] || prev.vehicle_plate
    }));
    setShowCustomerDropdown(false);
    setCustomerSearchResults([]);
  };

  const handleConvertFieldChange = (field, value) => {
    setConvertData(prev => ({ ...prev, [field]: value }));
    if (field === 'vehicle_plate') searchCustomerByField('plate', value);
    else if (field === 'customer_phone') searchCustomerByField('phone', value);
    else if (field === 'customer_name') searchCustomerByField('name', value);
  };

  // Open convert modal pre-filled from alert
  const openConvert = () => {
    const items = detailAlert?.items || [];
    const itemsText = items.length > 0 ? items.join(', ') : '';
    const rawText = detailAlert?.raw_text || '';
    let desc = rawText;
    if (itemsText) desc = desc ? `${desc} | Itens: ${itemsText}` : `Itens: ${itemsText}`;

    setConvertData({
      customer_name: detailAlert?.client_name || '',
      customer_phone: '',
      customer_email: '',
      vehicle_plate: detailAlert?.license_plate || '',
      ticket_type: 'ORCAMENTO_MECANICA',
      description: desc,
      assigned_to: detailAlert?.assigned_to || ''
    });
    setCustomerSearchResults([]);
    setShowCustomerDropdown(false);
    setConvertOpen(true);

    // Auto-search by plate if available
    if (detailAlert?.license_plate) {
      searchCustomerByField('plate', detailAlert.license_plate);
    }
  };

  // Convert to ticket
  const handleConvert = async () => {
    if (!detailAlert) return;
    if (!convertData.customer_name.trim()) {
      toast.error('Nome do cliente é obrigatório');
      return;
    }
    setConverting(true);
    try {
      const payload = { ...convertData };
      if (!payload.assigned_to) delete payload.assigned_to;

      const resp = await axios.post(
        `${API_URL}/api/telegram-alerts/alerts/${detailAlert.id}/convert`,
        payload,
        { headers: getAuthHeaders() }
      );
      toast.success(`Ticket ${resp.data.ticket_number} criado!`);
      setConvertOpen(false);
      setDetailOpen(false);
      fetchAlerts();
      fetchStats();
      if (resp.data.ticket_id) {
        navigate(`/tickets/${resp.data.ticket_id}`);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erro ao converter');
    } finally {
      setConverting(false);
    }
  };

  // Dismiss alert
  const handleDismiss = async (alertId) => {
    try {
      await axios.post(
        `${API_URL}/api/telegram-alerts/alerts/${alertId}/dismiss`,
        {},
        { headers: getAuthHeaders() }
      );
      toast.success('Alerta descartado');
      setDetailOpen(false);
      fetchAlerts();
      fetchStats();
    } catch (e) {
      toast.error('Erro ao descartar');
    }
  };

  // Delete alert
  const handleDelete = async (alertId) => {
    if (!window.confirm('Eliminar este alerta permanentemente?')) return;
    try {
      await axios.delete(
        `${API_URL}/api/telegram-alerts/alerts/${alertId}`,
        { headers: getAuthHeaders() }
      );
      toast.success('Alerta eliminado');
      setDetailOpen(false);
      fetchAlerts();
      fetchStats();
    } catch (e) {
      toast.error('Erro ao eliminar');
    }
  };

  // Setup webhook
  const handleSetupWebhook = async () => {
    setSettingUpWebhook(true);
    try {
      const resp = await axios.post(
        `${API_URL}/api/telegram-alerts/setup-webhook`,
        {},
        { headers: getAuthHeaders() }
      );
      toast.success('Webhook configurado com sucesso!');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erro ao configurar webhook');
    } finally {
      setSettingUpWebhook(false);
    }
  };

  // Module not enabled screen
  if (checkingModule) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!moduleEnabled) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-center" data-testid="alerts-module-disabled">
        <Bell className="h-16 w-16 text-zinc-300 mb-4" />
        <h2 className="text-2xl font-bold text-zinc-700 mb-2">Alertas Telegram Desativado</h2>
        <p className="text-zinc-500 max-w-md">
          O módulo de Alertas Telegram está desativado. Ative em <code>modules.json</code> para receber alertas dos mecânicos.
        </p>
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-6" data-testid="alerts-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">
            Alertas Telegram
          </h1>
          <p className="text-zinc-500">
            Fotos e mensagens dos mecânicos via bot Telegram
          </p>
        </div>
        <div className="flex gap-3">
          <Button
            variant="outline"
            className="border-2"
            onClick={() => { fetchAlerts(); fetchStats(); }}
            data-testid="refresh-alerts-btn"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Atualizar
          </Button>
          <Button
            variant="outline"
            className="border-2"
            onClick={handleSetupWebhook}
            disabled={settingUpWebhook}
            data-testid="setup-webhook-btn"
          >
            <Settings className="h-4 w-4 mr-2" />
            {settingUpWebhook ? 'A configurar...' : 'Configurar Webhook'}
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-2 border-amber-200 bg-amber-50/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-100 rounded-lg">
                <Clock className="h-5 w-5 text-amber-700" />
              </div>
              <div>
                <p className="text-2xl font-black text-amber-800" data-testid="stats-pending">{stats.pending}</p>
                <p className="text-xs font-medium text-amber-600">Pendentes</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-2 border-emerald-200 bg-emerald-50/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-emerald-100 rounded-lg">
                <CheckCircle2 className="h-5 w-5 text-emerald-700" />
              </div>
              <div>
                <p className="text-2xl font-black text-emerald-800" data-testid="stats-converted">{stats.converted}</p>
                <p className="text-xs font-medium text-emerald-600">Convertidos</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-2 border-zinc-200 bg-zinc-50/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-zinc-100 rounded-lg">
                <XCircle className="h-5 w-5 text-zinc-600" />
              </div>
              <div>
                <p className="text-2xl font-black text-zinc-700" data-testid="stats-dismissed">{stats.dismissed}</p>
                <p className="text-xs font-medium text-zinc-500">Descartados</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-2 border-blue-200 bg-blue-50/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                <Zap className="h-5 w-5 text-blue-700" />
              </div>
              <div>
                <p className="text-2xl font-black text-blue-800" data-testid="stats-total">{stats.total}</p>
                <p className="text-xs font-medium text-blue-600">Total</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col md:flex-row gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-400" />
              <Input
                placeholder="Pesquisar por matrícula, nome, texto..."
                className="pl-10 h-11 border-2"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                data-testid="alerts-search-input"
              />
            </div>
            <Select value={filterStatus} onValueChange={(v) => { setFilterStatus(v); setPage(1); }}>
              <SelectTrigger className="w-48 h-11 border-2" data-testid="alerts-filter-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="pending">Pendentes</SelectItem>
                <SelectItem value="converted">Convertidos</SelectItem>
                <SelectItem value="dismissed">Descartados</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Alerts Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center" data-testid="alerts-empty">
              <Bell className="h-12 w-12 text-zinc-300 mb-3" />
              <p className="text-zinc-500 font-medium">Nenhum alerta encontrado</p>
              <p className="text-zinc-400 text-sm mt-1">Os alertas dos mecânicos via bot Telegram aparecerão aqui</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50/80">
                  <TableHead className="font-bold w-16">SLA</TableHead>
                  <TableHead className="font-bold">Matrícula</TableHead>
                  <TableHead className="font-bold">Nome</TableHead>
                  <TableHead className="font-bold">Enviado por</TableHead>
                  <TableHead className="font-bold">Atribuído a</TableHead>
                  <TableHead className="font-bold">Estado</TableHead>
                  <TableHead className="font-bold">Data</TableHead>
                  <TableHead className="text-right font-bold">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((alert) => {
                  const sla = getSlaInfo(alert.created_at);
                  const st = statusConfig[alert.status] || statusConfig.pending;
                  const StatusIcon = st.icon;
                  return (
                    <TableRow
                      key={alert.id}
                      className="hover:bg-zinc-50/50 cursor-pointer"
                      onClick={() => openDetail(alert)}
                      data-testid={`alert-row-${alert.id}`}
                    >
                      <TableCell>
                        {alert.status === 'pending' ? (
                          <span className={`inline-flex items-center px-2 py-1 rounded-md text-xs font-bold border ${sla.color}`}>
                            {sla.label}
                          </span>
                        ) : (
                          <span className="text-xs text-zinc-400">--</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {alert.attachments?.length > 0 && (
                            <Image className="h-4 w-4 text-blue-500" />
                          )}
                          <span className="font-mono font-bold text-slate-800">
                            {alert.license_plate || '--'}
                          </span>
                          {alert.extraction_failed && (
                            <AlertTriangle className="h-4 w-4 text-amber-500" title="Extração IA falhou" />
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-zinc-700">{alert.client_name || '--'}</TableCell>
                      <TableCell className="text-zinc-500 text-sm">{alert.created_by?.name || '--'}</TableCell>
                      <TableCell className="text-zinc-600 text-sm">{alert.assigned_to_name || '--'}</TableCell>
                      <TableCell>
                        <Badge className={st.color}>
                          <StatusIcon className="h-3 w-3 mr-1" />
                          {st.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-zinc-500">
                        {new Date(alert.created_at).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => { e.stopPropagation(); openDetail(alert); }}
                          data-testid={`view-alert-${alert.id}`}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-zinc-500">{total} alerta{total !== 1 ? 's' : ''}</p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm font-medium">{page}/{totalPages}</span>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <Bell className="h-5 w-5 text-orange-600" />
              Detalhe do Alerta
              {detailAlert?.extraction_failed && (
                <Badge className="bg-amber-100 text-amber-800 ml-2">
                  <AlertTriangle className="h-3 w-3 mr-1" /> IA falhou
                </Badge>
              )}
            </DialogTitle>
          </DialogHeader>

          {detailAlert && (
            <div className="space-y-5">
              {/* Status & SLA */}
              <div className="flex items-center gap-3">
                {(() => {
                  const st = statusConfig[detailAlert.status] || statusConfig.pending;
                  const StatusIcon = st.icon;
                  return (
                    <Badge className={`${st.color} text-sm`}>
                      <StatusIcon className="h-3.5 w-3.5 mr-1" />
                      {st.label}
                    </Badge>
                  );
                })()}
                {detailAlert.status === 'pending' && (
                  <Badge className={`${getSlaInfo(detailAlert.created_at).color} text-sm border`}>
                    <Clock className="h-3.5 w-3.5 mr-1" />
                    Tempo: {getSlaInfo(detailAlert.created_at).label}
                  </Badge>
                )}
                {detailAlert.ticket_number && (
                  <Badge
                    className="bg-blue-100 text-blue-800 cursor-pointer hover:bg-blue-200"
                    onClick={() => {
                      setDetailOpen(false);
                      navigate(`/tickets/${detailAlert.ticket_id}`);
                    }}
                    data-testid="alert-ticket-link"
                  >
                    <FileText className="h-3.5 w-3.5 mr-1" />
                    {detailAlert.ticket_number}
                  </Badge>
                )}
              </div>

              {/* Extraction failed warning */}
              {detailAlert.extraction_failed && (
                <div className="bg-amber-50 border-2 border-amber-200 rounded-lg p-4 flex items-start gap-3" data-testid="extraction-warning">
                  <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-semibold text-amber-800">Extração automática falhou</p>
                    <p className="text-sm text-amber-700 mt-1">
                      A IA não conseguiu ler os dados da imagem. Preencha manualmente os campos abaixo.
                    </p>
                  </div>
                </div>
              )}

              {/* Photo */}
              {detailAlert.attachments?.length > 0 && (
                <div className="bg-zinc-100 rounded-lg overflow-hidden border-2 border-zinc-200">
                  {loadingPhoto ? (
                    <div className="flex items-center justify-center h-48">
                      <div className="w-8 h-8 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
                    </div>
                  ) : photoUrl ? (
                    <img
                      src={photoUrl}
                      alt="Foto do alerta"
                      className="w-full max-h-80 object-contain"
                      data-testid="alert-photo"
                    />
                  ) : (
                    <div className="flex items-center justify-center h-48 text-zinc-400">
                      <Image className="h-8 w-8 mr-2" />
                      <span>Foto não disponível</span>
                    </div>
                  )}
                </div>
              )}

              {/* Raw text */}
              {detailAlert.raw_text && (
                <div className="bg-zinc-50 rounded-lg p-3 border">
                  <p className="text-xs font-semibold text-zinc-500 mb-1">Texto enviado:</p>
                  <p className="text-sm text-zinc-700">{detailAlert.raw_text}</p>
                </div>
              )}

              {/* Editable fields */}
              {detailAlert.status === 'pending' && (
                <div className="space-y-4 border-t pt-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="font-semibold flex items-center gap-1">
                        <Car className="h-4 w-4" /> Matrícula
                      </Label>
                      <Input
                        value={editPlate}
                        onChange={(e) => setEditPlate(e.target.value.toUpperCase())}
                        placeholder="AA-00-AA"
                        className="h-11 border-2 font-mono"
                        data-testid="edit-plate-input"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="font-semibold flex items-center gap-1">
                        <User className="h-4 w-4" /> Nome do Cliente
                      </Label>
                      <Input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="Nome..."
                        className="h-11 border-2"
                        data-testid="edit-name-input"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label className="font-semibold">Itens / Serviços (separados por vírgula)</Label>
                    <Textarea
                      value={editItems}
                      onChange={(e) => setEditItems(e.target.value)}
                      placeholder="Pneus, travões, óleo..."
                      className="border-2 min-h-[60px]"
                      data-testid="edit-items-input"
                    />
                  </div>
                  <Button
                    onClick={handleSave}
                    disabled={saving}
                    className="bg-slate-800 hover:bg-slate-900 font-bold"
                    data-testid="save-alert-btn"
                  >
                    {saving ? 'A guardar...' : 'Guardar Alterações'}
                  </Button>
                </div>
              )}

              {/* Meta info */}
              <div className="grid grid-cols-2 gap-4 text-sm border-t pt-4">
                <div>
                  <p className="text-zinc-400 text-xs font-semibold">Enviado por</p>
                  <p className="text-zinc-700">{detailAlert.created_by?.name || '--'}</p>
                  {detailAlert.created_by?.username && (
                    <p className="text-zinc-400 text-xs">@{detailAlert.created_by.username}</p>
                  )}
                </div>
                <div>
                  <p className="text-zinc-400 text-xs font-semibold">Atribuído a</p>
                  <p className="text-zinc-700">{detailAlert.assigned_to_name || 'Ninguém'}</p>
                </div>
                <div>
                  <p className="text-zinc-400 text-xs font-semibold">Criado em</p>
                  <p className="text-zinc-700">
                    {new Date(detailAlert.created_at).toLocaleString('pt-PT')}
                  </p>
                </div>
                {detailAlert.converted_at && (
                  <div>
                    <p className="text-zinc-400 text-xs font-semibold">Convertido em</p>
                    <p className="text-zinc-700">
                      {new Date(detailAlert.converted_at).toLocaleString('pt-PT')}
                    </p>
                  </div>
                )}
              </div>

              {/* Action buttons */}
              {detailAlert.status === 'pending' && (
                <DialogFooter className="gap-2 pt-2 border-t">
                  <Button
                    variant="outline"
                    className="border-2 text-zinc-600"
                    onClick={() => handleDismiss(detailAlert.id)}
                    data-testid="dismiss-alert-btn"
                  >
                    <XCircle className="h-4 w-4 mr-2" />
                    Descartar
                  </Button>
                  <Button
                    variant="outline"
                    className="border-2 text-red-600 hover:bg-red-50"
                    onClick={() => handleDelete(detailAlert.id)}
                    data-testid="delete-alert-btn"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Eliminar
                  </Button>
                  <Button
                    onClick={openConvert}
                    className="bg-orange-600 hover:bg-orange-700 font-bold"
                    data-testid="convert-alert-btn"
                  >
                    <ArrowRight className="h-4 w-4 mr-2" />
                    Converter para Ticket
                  </Button>
                </DialogFooter>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Convert Modal (Intake-style) */}
      <Dialog open={convertOpen} onOpenChange={setConvertOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-xl font-bold">
              <ArrowRight className="h-5 w-5 text-green-500" />
              Converter em Ticket
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="p-3 bg-zinc-50 rounded-lg text-sm text-zinc-600">
              A converter alerta de <strong>{detailAlert?.created_by?.name || 'Mecânico'}</strong>
              {detailAlert?.license_plate && (
                <span className="ml-1">- Matrícula: <strong>{detailAlert.license_plate}</strong></span>
              )}
            </div>

            {/* Customer search dropdown */}
            {showCustomerDropdown && customerSearchResults.length > 1 && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <Label className="text-blue-700 text-sm font-medium mb-2 block">
                  {customerSearchResults.length} clientes encontrados - selecione:
                </Label>
                <div className="max-h-40 overflow-y-auto space-y-1">
                  {customerSearchResults.map((c, idx) => (
                    <button
                      key={c.id || idx}
                      onClick={() => selectCustomer(c)}
                      className="w-full text-left p-2 text-sm bg-white hover:bg-blue-100 rounded border border-blue-100 transition-colors"
                    >
                      <span className="font-medium">{c.name}</span>
                      {c.phone && <span className="text-zinc-500"> - {c.phone}</span>}
                      {c.email && <span className="text-zinc-400"> - {c.email}</span>}
                      {c.plates?.length > 0 && (
                        <span className="text-zinc-400"> - {c.plates.join(', ')}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="relative">
                <Label className="font-semibold">Nome do Cliente *</Label>
                <Input
                  value={convertData.customer_name}
                  onChange={(e) => handleConvertFieldChange('customer_name', e.target.value)}
                  className={`h-11 border-2 ${searchingCustomer ? 'pr-8' : ''}`}
                  data-testid="convert-customer-name"
                />
                {searchingCustomer && (
                  <RefreshCw className="absolute right-2 top-9 h-4 w-4 animate-spin text-zinc-400" />
                )}
              </div>
              <div className="relative">
                <Label className="font-semibold">Telefone</Label>
                <Input
                  value={convertData.customer_phone}
                  onChange={(e) => handleConvertFieldChange('customer_phone', e.target.value)}
                  className="h-11 border-2"
                  data-testid="convert-customer-phone"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="font-semibold">Email</Label>
                <Input
                  value={convertData.customer_email}
                  onChange={(e) => setConvertData(prev => ({ ...prev, customer_email: e.target.value }))}
                  className="h-11 border-2"
                  data-testid="convert-customer-email"
                />
              </div>
              <div className="relative">
                <Label className="font-semibold">Matrícula</Label>
                <Input
                  value={convertData.vehicle_plate}
                  onChange={(e) => handleConvertFieldChange('vehicle_plate', e.target.value.toUpperCase())}
                  className="h-11 border-2 font-mono"
                  data-testid="convert-vehicle-plate"
                />
              </div>
            </div>
            <div>
              <Label className="font-semibold">Tipo de Ticket</Label>
              <Select
                value={convertData.ticket_type}
                onValueChange={(v) => setConvertData(prev => ({ ...prev, ticket_type: v }))}
              >
                <SelectTrigger className="h-11 border-2" data-testid="convert-type-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ticketTypes.map(t => (
                    <SelectItem key={t.code} value={t.code}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="font-semibold">Atribuir a (opcional)</Label>
              <Select
                value={convertData.assigned_to || "none"}
                onValueChange={(v) => setConvertData(prev => ({ ...prev, assigned_to: v === "none" ? "" : v }))}
              >
                <SelectTrigger className="h-11 border-2" data-testid="convert-assignee-select">
                  <SelectValue placeholder="Selecionar agente..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Não atribuir</SelectItem>
                  {users.filter(u => ['ADMIN', 'SUPERVISOR', 'AGENT'].includes(u.role)).map(u => (
                    <SelectItem key={u.id} value={u.id}>{u.name} ({u.role})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="font-semibold">Descrição</Label>
              <Textarea
                value={convertData.description}
                onChange={(e) => setConvertData(prev => ({ ...prev, description: e.target.value }))}
                rows={4}
                className="border-2"
                data-testid="convert-description"
              />
            </div>
          </div>
          <DialogFooter className="gap-2 pt-4">
            <Button variant="outline" className="border-2" onClick={() => setConvertOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleConvert}
              disabled={converting}
              className="bg-green-600 hover:bg-green-700 font-bold"
              data-testid="confirm-convert-btn"
            >
              {converting ? (
                <RefreshCw className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <FileText className="h-4 w-4 mr-2" />
              )}
              Criar Ticket
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AlertsPage;
