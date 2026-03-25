import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { 
  Inbox, 
  FileText, 
  Trash2, 
  Edit, 
  ArrowRight,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Clock,
  XCircle,
  Plus,
  Phone,
  User,
  Car,
  MessageSquare,
  Search,
  Filter,
  StickyNote,
  ChevronLeft,
  ChevronRight,
  ExternalLink
} from 'lucide-react';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const IntakePage = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  
  // Data state
  const [requests, setRequests] = useState([]);
  const [stats, setStats] = useState({ pending: 0, processing: 0, converted: 0, rejected: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [moduleEnabled, setModuleEnabled] = useState(false);
  const [checkingModule, setCheckingModule] = useState(true);
  
  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  
  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterSource, setFilterSource] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  
  // Create dialog
  const [createDialog, setCreateDialog] = useState(false);
  const [newRequest, setNewRequest] = useState({
    source: 'manual',
    source_type: 'manual',
    sender_name: '',
    sender_contact: '',
    raw_text: '',
    license_plate: '',
    tire_size: ''
  });
  const [creating, setCreating] = useState(false);
  
  // Edit dialog
  const [editDialog, setEditDialog] = useState(false);
  const [editingRequest, setEditingRequest] = useState(null);
  const [saving, setSaving] = useState(false);
  
  // Notes dialog
  const [notesDialog, setNotesDialog] = useState(false);
  const [notesRequest, setNotesRequest] = useState(null);
  const [newNote, setNewNote] = useState('');
  const [addingNote, setAddingNote] = useState(false);
  
  // Convert dialog
  const [convertDialog, setConvertDialog] = useState(false);
  const [convertingRequest, setConvertingRequest] = useState(null);
  const [convertData, setConvertData] = useState({
    customer_name: '',
    customer_phone: '',
    customer_email: '',
    vehicle_plate: '',
    ticket_type: 'INFORMACAO',
    description: '',
    assigned_to: ''
  });
  const [converting, setConverting] = useState(false);
  
  // Customer search for convert modal
  const [customerSearchResults, setCustomerSearchResults] = useState([]);
  const [searchingCustomer, setSearchingCustomer] = useState(false);
  const [showCustomerDropdown, setShowCustomerDropdown] = useState(false);
  const searchTimeoutRef = React.useRef(null);
  
  // Users for assignment dropdown
  const [users, setUsers] = useState([]);

  // Check if module is enabled
  useEffect(() => {
    const checkModule = async () => {
      try {
        const response = await axios.get(`${API_URL}/api/modules/status`, {
          headers: getAuthHeaders()
        });
        setModuleEnabled(response.data.modules?.intake === true);
      } catch (error) {
        console.error('Error checking modules:', error);
        setModuleEnabled(false);
      } finally {
        setCheckingModule(false);
      }
    };
    checkModule();
  }, [getAuthHeaders]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    if (!moduleEnabled) return;
    try {
      const response = await axios.get(`${API_URL}/api/intake/stats`, {
        headers: getAuthHeaders()
      });
      setStats(response.data);
    } catch (error) {
      console.error('Error fetching stats:', error);
    }
  }, [getAuthHeaders, moduleEnabled]);

  // Fetch requests with filters and pagination
  const fetchRequests = useCallback(async () => {
    if (!moduleEnabled) return;
    
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('page', page);
      params.append('page_size', pageSize);
      
      if (searchTerm) params.append('search', searchTerm);
      if (filterStatus !== 'all') params.append('status', filterStatus);
      if (filterSource !== 'all') params.append('source', filterSource);
      
      const response = await axios.get(`${API_URL}/api/intake?${params.toString()}`, {
        headers: getAuthHeaders()
      });
      
      setRequests(response.data.items || []);
      setTotal(response.data.total || 0);
      setTotalPages(response.data.total_pages || 1);
    } catch (error) {
      console.error('Error fetching intake requests:', error);
      toast.error('Erro ao carregar pedidos');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders, moduleEnabled, page, pageSize, searchTerm, filterStatus, filterSource]);

  useEffect(() => {
    if (moduleEnabled) {
      fetchRequests();
      fetchStats();
    }
  }, [moduleEnabled, fetchRequests, fetchStats]);

  // Fetch users for assignment dropdown
  const fetchUsers = useCallback(async () => {
    try {
      const response = await axios.get(`${API_URL}/api/users`, {
        headers: getAuthHeaders()
      });
      // Filter to only show AGENT, SUPERVISOR, ADMIN
      const assignableUsers = (response.data || []).filter(u => 
        ['AGENT', 'SUPERVISOR', 'ADMIN'].includes(u.role)
      );
      setUsers(assignableUsers);
    } catch (error) {
      console.error('Error fetching users:', error);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [searchTerm, filterStatus, filterSource]);

  // Status badge
  const getStatusBadge = (status) => {
    const config = {
      PENDING: { label: 'Pendente', className: 'bg-amber-100 text-amber-800', icon: Clock },
      PROCESSING: { label: 'Em Processamento', className: 'bg-blue-100 text-blue-800', icon: RefreshCw },
      CONVERTED: { label: 'Convertido', className: 'bg-green-100 text-green-800', icon: CheckCircle2 },
      REJECTED: { label: 'Rejeitado', className: 'bg-red-100 text-red-800', icon: XCircle }
    };
    const { label, className, icon: Icon } = config[status] || config.PENDING;
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${className}`}>
        <Icon className="h-3 w-3" />
        {label}
      </span>
    );
  };

  // Source badge
  const getSourceBadge = (source) => {
    const config = {
      telegram: { label: 'Telegram', className: 'bg-blue-100 text-blue-800' },
      whatsapp: { label: 'WhatsApp', className: 'bg-green-100 text-green-800' },
      email: { label: 'Email', className: 'bg-purple-100 text-purple-800' },
      web_form: { label: 'Formulário', className: 'bg-gray-100 text-gray-800' },
      telefone: { label: 'Telefone', className: 'bg-cyan-100 text-cyan-800' },
      manual: { label: 'Manual', className: 'bg-orange-100 text-orange-800' }
    };
    const { label, className } = config[source] || { label: source, className: 'bg-gray-100 text-gray-800' };
    return (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${className}`}>
        {label}
      </span>
    );
  };

  // Source type badge
  const getSourceTypeBadge = (sourceType) => {
    const config = {
      manual: { label: 'Manual', className: 'bg-zinc-100 text-zinc-600' },
      bot_telegram: { label: 'Bot TG', className: 'bg-blue-50 text-blue-600' },
      bot_whatsapp: { label: 'Bot WA', className: 'bg-green-50 text-green-600' },
      api: { label: 'API', className: 'bg-violet-50 text-violet-600' },
      import: { label: 'Import', className: 'bg-amber-50 text-amber-600' }
    };
    const { label, className } = config[sourceType] || { label: sourceType || 'Manual', className: 'bg-zinc-100 text-zinc-600' };
    return (
      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${className}`}>
        {label}
      </span>
    );
  };

  // Create handlers
  const handleOpenCreate = () => {
    setNewRequest({
      source: 'manual',
      source_type: 'manual',
      sender_name: '',
      sender_contact: '',
      raw_text: '',
      license_plate: '',
      tire_size: ''
    });
    setCreateDialog(true);
  };

  const handleCreate = async () => {
    if (!newRequest.sender_name.trim() || !newRequest.sender_contact.trim()) {
      toast.error('Nome e contacto são obrigatórios');
      return;
    }

    setCreating(true);
    try {
      await axios.post(
        `${API_URL}/api/intake`,
        newRequest,
        { headers: getAuthHeaders() }
      );
      toast.success('Pré-ticket criado com sucesso');
      setCreateDialog(false);
      fetchRequests();
      fetchStats();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar pré-ticket');
    } finally {
      setCreating(false);
    }
  };

  // Edit handlers
  const handleEdit = (request) => {
    setEditingRequest({ ...request });
    setEditDialog(true);
  };

  const handleSaveEdit = async () => {
    if (!editingRequest.sender_name.trim() || !editingRequest.sender_contact.trim()) {
      toast.error('Nome e contacto são obrigatórios');
      return;
    }

    setSaving(true);
    try {
      await axios.put(
        `${API_URL}/api/intake/${editingRequest.id}`,
        {
          sender_name: editingRequest.sender_name,
          sender_contact: editingRequest.sender_contact,
          raw_text: editingRequest.raw_text,
          license_plate: editingRequest.license_plate,
          tire_size: editingRequest.tire_size,
          status: editingRequest.status
        },
        { headers: getAuthHeaders() }
      );
      toast.success('Pré-ticket atualizado');
      setEditDialog(false);
      fetchRequests();
      fetchStats();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao atualizar');
    } finally {
      setSaving(false);
    }
  };

  // Delete handler
  const handleDelete = async (id) => {
    if (!window.confirm('Tem certeza que deseja eliminar este pré-ticket?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/intake/${id}`, {
        headers: getAuthHeaders()
      });
      toast.success('Pré-ticket eliminado');
      fetchRequests();
      fetchStats();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao eliminar');
    }
  };

  // Notes handlers
  const handleOpenNotes = (request) => {
    setNotesRequest(request);
    setNewNote('');
    setNotesDialog(true);
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) {
      toast.error('A nota não pode estar vazia');
      return;
    }

    setAddingNote(true);
    try {
      const response = await axios.post(
        `${API_URL}/api/intake/${notesRequest.id}/notes`,
        { note: newNote.trim() },
        { headers: getAuthHeaders() }
      );
      setNotesRequest(response.data);
      setNewNote('');
      toast.success('Nota adicionada');
      fetchRequests();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao adicionar nota');
    } finally {
      setAddingNote(false);
    }
  };

  // Convert handlers
  const handleConvert = (request) => {
    setConvertingRequest(request);
    setConvertData({
      customer_name: request.sender_name,
      customer_phone: request.sender_contact || '',  // Phone only, not telegram username
      customer_email: request.sender_email || '',    // Pre-fill email from DB lookup
      vehicle_plate: request.license_plate || '',
      ticket_type: 'INFORMACAO',
      description: request.raw_text,
      assigned_to: ''
    });
    setCustomerSearchResults([]);
    setShowCustomerDropdown(false);
    setConvertDialog(true);
    
    // Auto-search by plate if available
    if (request.license_plate) {
      searchCustomerByField('plate', request.license_plate);
    }
  };

  // Search customer by specific field with debounce
  const searchCustomerByField = async (field, value) => {
    if (!value || value.length < 2) {
      setCustomerSearchResults([]);
      setShowCustomerDropdown(false);
      return;
    }
    
    // Clear previous timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    
    // Debounce 500ms
    searchTimeoutRef.current = setTimeout(async () => {
      setSearchingCustomer(true);
      try {
        const params = new URLSearchParams();
        params.append(field, value);
        
        const response = await axios.get(
          `${API_URL}/api/customers/search?${params.toString()}`,
          { headers: getAuthHeaders() }
        );
        
        const results = response.data || [];
        setCustomerSearchResults(results);
        
        if (results.length === 1) {
          // Auto-fill if only one match
          selectCustomer(results[0]);
          setShowCustomerDropdown(false);
        } else if (results.length > 1) {
          // Show dropdown for multiple matches
          setShowCustomerDropdown(true);
        } else {
          setShowCustomerDropdown(false);
        }
      } catch (error) {
        console.error('Error searching customer:', error);
      } finally {
        setSearchingCustomer(false);
      }
    }, 500);
  };

  // Select a customer from search results
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

  // Handle field change with customer search
  const handleConvertFieldChange = (field, value) => {
    setConvertData(prev => ({ ...prev, [field]: value }));
    
    // Trigger search based on field
    if (field === 'vehicle_plate') {
      searchCustomerByField('plate', value);
    } else if (field === 'customer_phone') {
      searchCustomerByField('phone', value);
    } else if (field === 'customer_name') {
      searchCustomerByField('name', value);
    }
  };

  const handleConvertSubmit = async () => {
    if (!convertData.customer_name.trim()) {
      toast.error('Nome é obrigatório');
      return;
    }

    setConverting(true);
    try {
      // Only include assigned_to if it has a value
      const payload = { ...convertData };
      if (!payload.assigned_to) {
        delete payload.assigned_to;
      }
      
      const response = await axios.post(
        `${API_URL}/api/intake/${convertingRequest.id}/convert_to_ticket`,
        payload,
        { headers: getAuthHeaders() }
      );
      toast.success(`Ticket ${response.data.ticket_number} criado!`);
      setConvertDialog(false);
      fetchRequests();
      fetchStats();
      
      // Navigate to the new ticket
      if (response.data.ticket_id) {
        navigate(`/tickets/${response.data.ticket_id}`);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao converter');
    } finally {
      setConverting(false);
    }
  };

  // Search handler with debounce
  const handleSearch = (value) => {
    setSearchTerm(value);
  };

  // Module disabled view
  if (checkingModule) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-zinc-400" />
      </div>
    );
  }

  if (!moduleEnabled) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <AlertCircle className="h-16 w-16 text-zinc-300 mb-4" />
        <h2 className="text-xl font-semibold text-zinc-700 mb-2">Módulo Desativado</h2>
        <p className="text-zinc-500 max-w-md">
          O módulo de Intake não está ativo. Entre em contacto com o administrador para ativar esta funcionalidade.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-zinc-800 flex items-center gap-2">
            <Inbox className="h-7 w-7 text-orange-500" />
            Pré-Tickets
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Pedidos aguardando conversão em tickets
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => { fetchRequests(); fetchStats(); }} variant="outline" className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </Button>
          <Button onClick={handleOpenCreate} className="gap-2 bg-orange-500 hover:bg-orange-600" data-testid="new-intake-btn">
            <Plus className="h-4 w-4" />
            Novo Pré-Ticket
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-amber-400 cursor-pointer hover:shadow-md transition-shadow" onClick={() => setFilterStatus(filterStatus === 'PENDING' ? 'all' : 'PENDING')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Pendentes</p>
                <p className="text-2xl font-bold text-amber-600">{stats.pending}</p>
              </div>
              <Clock className="h-8 w-8 text-amber-400" />
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-blue-400 cursor-pointer hover:shadow-md transition-shadow" onClick={() => setFilterStatus(filterStatus === 'PROCESSING' ? 'all' : 'PROCESSING')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Em Processamento</p>
                <p className="text-2xl font-bold text-blue-600">{stats.processing}</p>
              </div>
              <RefreshCw className="h-8 w-8 text-blue-400" />
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-green-400 cursor-pointer hover:shadow-md transition-shadow" onClick={() => setFilterStatus(filterStatus === 'CONVERTED' ? 'all' : 'CONVERTED')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Convertidos</p>
                <p className="text-2xl font-bold text-green-600">{stats.converted}</p>
              </div>
              <CheckCircle2 className="h-8 w-8 text-green-400" />
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-red-400 cursor-pointer hover:shadow-md transition-shadow" onClick={() => setFilterStatus(filterStatus === 'REJECTED' ? 'all' : 'REJECTED')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Rejeitados</p>
                <p className="text-2xl font-bold text-red-600">{stats.rejected}</p>
              </div>
              <XCircle className="h-8 w-8 text-red-400" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap gap-4 items-center">
            {/* Search */}
            <div className="flex-1 min-w-[250px] relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-400" />
              <Input
                placeholder="Pesquisar por nome, contacto, matrícula, medida..."
                value={searchTerm}
                onChange={(e) => handleSearch(e.target.value)}
                className="pl-10"
                data-testid="intake-search"
              />
            </div>
            
            {/* Quick Filters */}
            <div className="flex gap-2 items-center">
              <Button 
                variant={showFilters ? "secondary" : "outline"} 
                size="sm" 
                onClick={() => setShowFilters(!showFilters)}
                className="gap-1"
              >
                <Filter className="h-4 w-4" />
                Filtros
              </Button>
              
              {(filterStatus !== 'all' || filterSource !== 'all' || searchTerm) && (
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={() => {
                    setFilterStatus('all');
                    setFilterSource('all');
                    setSearchTerm('');
                  }}
                  className="text-zinc-500"
                >
                  Limpar
                </Button>
              )}
            </div>
          </div>

          {/* Expanded Filters */}
          {showFilters && (
            <div className="mt-4 pt-4 border-t flex gap-4 flex-wrap">
              <div className="w-48">
                <Label className="text-xs text-zinc-500 mb-1 block">Estado</Label>
                <Select value={filterStatus} onValueChange={setFilterStatus}>
                  <SelectTrigger>
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="PENDING">Pendente</SelectItem>
                    <SelectItem value="PROCESSING">Em Processamento</SelectItem>
                    <SelectItem value="CONVERTED">Convertido</SelectItem>
                    <SelectItem value="REJECTED">Rejeitado</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="w-48">
                <Label className="text-xs text-zinc-500 mb-1 block">Origem</Label>
                <Select value={filterSource} onValueChange={setFilterSource}>
                  <SelectTrigger>
                    <SelectValue placeholder="Todas" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="manual">Manual</SelectItem>
                    <SelectItem value="telefone">Telefone</SelectItem>
                    <SelectItem value="email">Email</SelectItem>
                    <SelectItem value="whatsapp">WhatsApp</SelectItem>
                    <SelectItem value="telegram">Telegram</SelectItem>
                    <SelectItem value="web_form">Formulário Web</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex justify-between items-center">
            <CardTitle className="text-lg flex items-center gap-2">
              <FileText className="h-5 w-5 text-zinc-500" />
              Lista de Pré-Tickets
            </CardTitle>
            <span className="text-sm text-zinc-500">{total} resultado(s)</span>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <RefreshCw className="h-6 w-6 animate-spin text-zinc-400" />
            </div>
          ) : requests.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <Inbox className="h-16 w-16 mx-auto mb-3 text-zinc-300" />
              <p className="text-lg font-medium">Nenhum pré-ticket encontrado</p>
              <p className="text-sm mt-1">
                {searchTerm || filterStatus !== 'all' || filterSource !== 'all' 
                  ? 'Tente ajustar os filtros de pesquisa'
                  : 'Clique em "Novo Pré-Ticket" para criar um'}
              </p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-24">Origem</TableHead>
                    <TableHead>Nome</TableHead>
                    <TableHead>Contacto</TableHead>
                    <TableHead>Matrícula</TableHead>
                    <TableHead>Medida Pneu</TableHead>
                    <TableHead>Mensagem</TableHead>
                    <TableHead className="w-20">Notas</TableHead>
                    <TableHead className="w-28">Estado</TableHead>
                    <TableHead className="w-28">Data</TableHead>
                    <TableHead className="text-right w-32">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {requests.map(request => (
                    <TableRow key={request.id} data-testid={`intake-row-${request.id}`}>
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          {getSourceBadge(request.source)}
                          {getSourceTypeBadge(request.source_type)}
                        </div>
                      </TableCell>
                      <TableCell className="font-medium">{request.sender_name}</TableCell>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-mono text-sm">{request.sender_contact || '-'}</span>
                          {request.telegram_username && (
                            <span className="text-xs text-blue-500">{request.telegram_username}</span>
                          )}
                          {request.sender_email && (
                            <span className="text-xs text-zinc-400">{request.sender_email}</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-sm">{request.license_plate || '-'}</TableCell>
                      <TableCell className="text-sm">{request.tire_size || '-'}</TableCell>
                      <TableCell className="max-w-[200px]">
                        <span className="truncate block text-sm text-zinc-600" title={request.raw_text}>
                          {request.raw_text || '-'}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleOpenNotes(request)}
                          className={request.review_notes?.length > 0 ? 'text-amber-600' : 'text-zinc-400'}
                          title={`${request.review_notes?.length || 0} nota(s)`}
                        >
                          <StickyNote className="h-4 w-4" />
                          {request.review_notes?.length > 0 && (
                            <span className="ml-1 text-xs">{request.review_notes.length}</span>
                          )}
                        </Button>
                      </TableCell>
                      <TableCell>{getStatusBadge(request.status)}</TableCell>
                      <TableCell className="text-sm text-zinc-500">
                        {new Date(request.created_at).toLocaleDateString('pt-PT', {
                          day: '2-digit',
                          month: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </TableCell>
                      <TableCell className="text-right">
                        {request.status === 'CONVERTED' ? (
                          <Button
                            size="sm"
                            variant="link"
                            className="text-green-600 gap-1"
                            onClick={() => navigate(`/tickets/${request.converted_ticket_id}`)}
                            title={`Ticket ${request.converted_ticket_number}`}
                          >
                            <ExternalLink className="h-3 w-3" />
                            {request.converted_ticket_number || 'Ver Ticket'}
                          </Button>
                        ) : (
                          <div className="flex justify-end gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleEdit(request)}
                              title="Editar"
                              data-testid={`intake-edit-${request.id}`}
                            >
                              <Edit className="h-4 w-4 text-zinc-500" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-green-600 hover:text-green-700 hover:bg-green-50"
                              onClick={() => handleConvert(request)}
                              title="Converter em Ticket"
                              data-testid={`intake-convert-${request.id}`}
                            >
                              <ArrowRight className="h-4 w-4" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-red-600 hover:text-red-700 hover:bg-red-50"
                              onClick={() => handleDelete(request.id)}
                              title="Eliminar"
                              data-testid={`intake-delete-${request.id}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4 pt-4 border-t">
                  <span className="text-sm text-zinc-500">
                    Página {page} de {totalPages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1}
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Create Dialog */}
      <Dialog open={createDialog} onOpenChange={setCreateDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Plus className="h-5 w-5 text-orange-500" />
              Novo Pré-Ticket
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Origem</Label>
                <Select
                  value={newRequest.source}
                  onValueChange={(v) => setNewRequest({...newRequest, source: v})}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual</SelectItem>
                    <SelectItem value="telefone">Telefone</SelectItem>
                    <SelectItem value="email">Email</SelectItem>
                    <SelectItem value="whatsapp">WhatsApp</SelectItem>
                    <SelectItem value="telegram">Telegram</SelectItem>
                    <SelectItem value="web_form">Formulário Web</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Tipo de Origem</Label>
                <Select
                  value={newRequest.source_type}
                  onValueChange={(v) => setNewRequest({...newRequest, source_type: v})}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual</SelectItem>
                    <SelectItem value="bot_telegram">Bot Telegram</SelectItem>
                    <SelectItem value="bot_whatsapp">Bot WhatsApp</SelectItem>
                    <SelectItem value="api">API</SelectItem>
                    <SelectItem value="import">Importação</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="flex items-center gap-1">
                  <User className="h-3 w-3" /> Nome *
                </Label>
                <Input
                  placeholder="Nome do remetente"
                  value={newRequest.sender_name}
                  onChange={(e) => setNewRequest({...newRequest, sender_name: e.target.value})}
                  data-testid="intake-create-name"
                />
              </div>
              <div>
                <Label className="flex items-center gap-1">
                  <Phone className="h-3 w-3" /> Contacto *
                </Label>
                <Input
                  placeholder="Telefone ou email"
                  value={newRequest.sender_contact}
                  onChange={(e) => setNewRequest({...newRequest, sender_contact: e.target.value})}
                  data-testid="intake-create-contact"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="flex items-center gap-1">
                  <Car className="h-3 w-3" /> Matrícula
                </Label>
                <Input
                  placeholder="AA-00-BB"
                  value={newRequest.license_plate}
                  onChange={(e) => setNewRequest({...newRequest, license_plate: e.target.value.toUpperCase()})}
                  data-testid="intake-create-plate"
                />
              </div>
              <div>
                <Label>Medida de Pneu</Label>
                <Input
                  placeholder="205/55 R16"
                  value={newRequest.tire_size}
                  onChange={(e) => setNewRequest({...newRequest, tire_size: e.target.value})}
                  data-testid="intake-create-tire"
                />
              </div>
            </div>
            <div>
              <Label className="flex items-center gap-1">
                <MessageSquare className="h-3 w-3" /> Mensagem / Pedido
              </Label>
              <Textarea
                placeholder="Descrição do pedido ou mensagem recebida..."
                value={newRequest.raw_text}
                onChange={(e) => setNewRequest({...newRequest, raw_text: e.target.value})}
                rows={4}
                data-testid="intake-create-message"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialog(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleCreate} 
              disabled={creating}
              className="bg-orange-500 hover:bg-orange-600"
            >
              {creating ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
              Criar Pré-Ticket
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={editDialog} onOpenChange={setEditDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Edit className="h-5 w-5 text-blue-500" />
              Editar Pré-Ticket
            </DialogTitle>
          </DialogHeader>
          {editingRequest && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Nome *</Label>
                  <Input
                    value={editingRequest.sender_name}
                    onChange={(e) => setEditingRequest({...editingRequest, sender_name: e.target.value})}
                  />
                </div>
                <div>
                  <Label>Contacto *</Label>
                  <Input
                    value={editingRequest.sender_contact}
                    onChange={(e) => setEditingRequest({...editingRequest, sender_contact: e.target.value})}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Matrícula</Label>
                  <Input
                    value={editingRequest.license_plate || ''}
                    onChange={(e) => setEditingRequest({...editingRequest, license_plate: e.target.value.toUpperCase()})}
                  />
                </div>
                <div>
                  <Label>Medida de Pneu</Label>
                  <Input
                    value={editingRequest.tire_size || ''}
                    onChange={(e) => setEditingRequest({...editingRequest, tire_size: e.target.value})}
                  />
                </div>
              </div>
              <div>
                <Label>Mensagem</Label>
                <Textarea
                  value={editingRequest.raw_text || ''}
                  onChange={(e) => setEditingRequest({...editingRequest, raw_text: e.target.value})}
                  rows={4}
                />
              </div>
              <div>
                <Label>Estado</Label>
                <Select
                  value={editingRequest.status}
                  onValueChange={(v) => setEditingRequest({...editingRequest, status: v})}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="PENDING">Pendente</SelectItem>
                    <SelectItem value="PROCESSING">Em Processamento</SelectItem>
                    <SelectItem value="REJECTED">Rejeitado</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleSaveEdit} disabled={saving}>
              {saving ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : null}
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Notes Dialog */}
      <Dialog open={notesDialog} onOpenChange={setNotesDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <StickyNote className="h-5 w-5 text-amber-500" />
              Notas de Revisão
            </DialogTitle>
          </DialogHeader>
          {notesRequest && (
            <div className="space-y-4">
              {/* Info about the request */}
              <div className="p-3 bg-zinc-50 rounded-lg">
                <p className="text-sm text-zinc-600">
                  <strong>{notesRequest.sender_name}</strong> - {notesRequest.sender_contact}
                </p>
                {notesRequest.license_plate && (
                  <p className="text-xs text-zinc-500 mt-1">Matrícula: {notesRequest.license_plate}</p>
                )}
              </div>

              {/* Notes list */}
              <div className="max-h-60 overflow-y-auto space-y-2">
                {notesRequest.review_notes?.length > 0 ? (
                  notesRequest.review_notes.map((note, idx) => (
                    <div key={idx} className="p-3 bg-amber-50 rounded-lg border border-amber-100">
                      <p className="text-sm text-zinc-700">{note.note}</p>
                      <p className="text-xs text-zinc-500 mt-2">
                        {note.author_name} • {new Date(note.created_at).toLocaleDateString('pt-PT', {
                          day: '2-digit',
                          month: '2-digit',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="text-center text-zinc-400 py-4">Nenhuma nota ainda</p>
                )}
              </div>

              {/* Add note */}
              {notesRequest.status !== 'CONVERTED' && (
                <div className="pt-4 border-t">
                  <Label>Nova nota</Label>
                  <Textarea
                    placeholder="Escreva uma nota sobre este pedido..."
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    rows={3}
                    className="mt-1"
                  />
                  <Button 
                    onClick={handleAddNote} 
                    disabled={addingNote || !newNote.trim()}
                    className="mt-2 w-full"
                    size="sm"
                  >
                    {addingNote ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                    Adicionar Nota
                  </Button>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setNotesDialog(false)}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Convert Dialog */}
      <Dialog open={convertDialog} onOpenChange={setConvertDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ArrowRight className="h-5 w-5 text-green-500" />
              Converter em Ticket
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="p-3 bg-zinc-50 rounded-lg text-sm text-zinc-600">
              A converter pré-ticket de <strong>{convertingRequest?.sender_name}</strong>
              {convertingRequest?.review_notes?.length > 0 && (
                <span className="text-amber-600 ml-2">({convertingRequest.review_notes.length} nota(s))</span>
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
                <Label>Nome do Cliente *</Label>
                <Input
                  value={convertData.customer_name}
                  onChange={(e) => handleConvertFieldChange('customer_name', e.target.value)}
                  className={searchingCustomer ? 'pr-8' : ''}
                />
                {searchingCustomer && (
                  <RefreshCw className="absolute right-2 top-8 h-4 w-4 animate-spin text-zinc-400" />
                )}
              </div>
              <div className="relative">
                <Label>Telefone</Label>
                <Input
                  value={convertData.customer_phone}
                  onChange={(e) => handleConvertFieldChange('customer_phone', e.target.value)}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Email</Label>
                <Input
                  value={convertData.customer_email}
                  onChange={(e) => setConvertData({...convertData, customer_email: e.target.value})}
                />
              </div>
              <div className="relative">
                <Label>Matrícula</Label>
                <Input
                  value={convertData.vehicle_plate}
                  onChange={(e) => handleConvertFieldChange('vehicle_plate', e.target.value.toUpperCase())}
                />
              </div>
            </div>
            <div>
              <Label>Tipo de Ticket</Label>
              <Select
                value={convertData.ticket_type}
                onValueChange={(v) => setConvertData({...convertData, ticket_type: v})}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ORCAMENTO_PNEUS">Orçamento Pneus</SelectItem>
                  <SelectItem value="ORCAMENTO_MECANICA">Orçamento Mecânica</SelectItem>
                  <SelectItem value="MARCACAO">Marcação</SelectItem>
                  <SelectItem value="INFORMACAO">Informação</SelectItem>
                  <SelectItem value="RECLAMACAO">Reclamação</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Atribuir a (opcional)</Label>
              <Select
                value={convertData.assigned_to || "none"}
                onValueChange={(v) => setConvertData({...convertData, assigned_to: v === "none" ? "" : v})}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selecionar agente..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Não atribuir</SelectItem>
                  {users.map(user => (
                    <SelectItem key={user.id} value={user.id}>
                      {user.name} ({user.role})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Descrição</Label>
              <Textarea
                value={convertData.description}
                onChange={(e) => setConvertData({...convertData, description: e.target.value})}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConvertDialog(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleConvertSubmit} 
              disabled={converting}
              className="bg-green-600 hover:bg-green-700"
            >
              {converting ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <FileText className="h-4 w-4 mr-2" />}
              Criar Ticket
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default IntakePage;
