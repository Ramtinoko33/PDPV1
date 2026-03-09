import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
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
  MessageSquare
} from 'lucide-react';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const IntakePage = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [moduleEnabled, setModuleEnabled] = useState(false);
  const [checkingModule, setCheckingModule] = useState(true);
  
  // Create dialog
  const [createDialog, setCreateDialog] = useState(false);
  const [newRequest, setNewRequest] = useState({
    source: 'manual',
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
  
  // Convert dialog
  const [convertDialog, setConvertDialog] = useState(false);
  const [convertingRequest, setConvertingRequest] = useState(null);
  const [convertData, setConvertData] = useState({
    customer_name: '',
    customer_phone: '',
    customer_email: '',
    vehicle_plate: '',
    ticket_type: 'INFORMACAO',
    description: ''
  });
  const [converting, setConverting] = useState(false);

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

  // Fetch requests
  const fetchRequests = useCallback(async () => {
    if (!moduleEnabled) return;
    
    setLoading(true);
    try {
      const response = await axios.get(`${API_URL}/api/intake`, {
        headers: getAuthHeaders()
      });
      setRequests(response.data);
    } catch (error) {
      console.error('Error fetching intake requests:', error);
      toast.error('Erro ao carregar pedidos');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders, moduleEnabled]);

  useEffect(() => {
    if (moduleEnabled) {
      fetchRequests();
    }
  }, [moduleEnabled, fetchRequests]);

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
      manual: { label: 'Manual', className: 'bg-orange-100 text-orange-800' }
    };
    const { label, className } = config[source] || { label: source, className: 'bg-gray-100 text-gray-800' };
    return (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${className}`}>
        {label}
      </span>
    );
  };

  // Create handlers
  const handleOpenCreate = () => {
    setNewRequest({
      source: 'manual',
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
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao eliminar');
    }
  };

  // Convert handlers
  const handleConvert = (request) => {
    setConvertingRequest(request);
    setConvertData({
      customer_name: request.sender_name,
      customer_phone: request.sender_contact,
      customer_email: '',
      vehicle_plate: request.license_plate || '',
      ticket_type: 'INFORMACAO',
      description: request.raw_text
    });
    setConvertDialog(true);
  };

  const handleConvertSubmit = async () => {
    if (!convertData.customer_name.trim() || !convertData.customer_phone.trim()) {
      toast.error('Nome e telefone são obrigatórios');
      return;
    }

    setConverting(true);
    try {
      const response = await axios.post(
        `${API_URL}/api/intake/${convertingRequest.id}/convert_to_ticket`,
        convertData,
        { headers: getAuthHeaders() }
      );
      toast.success(`Ticket ${response.data.ticket_number} criado!`);
      setConvertDialog(false);
      fetchRequests();
      
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

  // Stats
  const stats = {
    pending: requests.filter(r => r.status === 'PENDING').length,
    processing: requests.filter(r => r.status === 'PROCESSING').length,
    converted: requests.filter(r => r.status === 'CONVERTED').length,
    rejected: requests.filter(r => r.status === 'REJECTED').length
  };

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
          <Button onClick={fetchRequests} variant="outline" className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </Button>
          <Button onClick={handleOpenCreate} className="gap-2 bg-orange-500 hover:bg-orange-600">
            <Plus className="h-4 w-4" />
            Novo Pré-Ticket
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-amber-400">
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
        <Card className="border-l-4 border-l-blue-400">
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
        <Card className="border-l-4 border-l-green-400">
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
        <Card className="border-l-4 border-l-red-400">
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

      {/* Table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <FileText className="h-5 w-5 text-zinc-500" />
            Lista de Pré-Tickets
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <RefreshCw className="h-6 w-6 animate-spin text-zinc-400" />
            </div>
          ) : requests.length === 0 ? (
            <div className="text-center py-12 text-zinc-500">
              <Inbox className="h-16 w-16 mx-auto mb-3 text-zinc-300" />
              <p className="text-lg font-medium">Nenhum pré-ticket</p>
              <p className="text-sm mt-1">Clique em "Novo Pré-Ticket" para criar um</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">Origem</TableHead>
                  <TableHead>Nome</TableHead>
                  <TableHead>Contacto</TableHead>
                  <TableHead>Matrícula</TableHead>
                  <TableHead>Medida Pneu</TableHead>
                  <TableHead>Mensagem</TableHead>
                  <TableHead className="w-28">Estado</TableHead>
                  <TableHead className="w-28">Data</TableHead>
                  <TableHead className="text-right w-32">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {requests.map(request => (
                  <TableRow key={request.id} data-testid={`intake-row-${request.id}`}>
                    <TableCell>{getSourceBadge(request.source)}</TableCell>
                    <TableCell className="font-medium">{request.sender_name}</TableCell>
                    <TableCell className="font-mono text-sm">{request.sender_contact}</TableCell>
                    <TableCell className="font-mono text-sm">{request.license_plate || '-'}</TableCell>
                    <TableCell className="text-sm">{request.tire_size || '-'}</TableCell>
                    <TableCell className="max-w-[200px]">
                      <span className="truncate block text-sm text-zinc-600" title={request.raw_text}>
                        {request.raw_text || '-'}
                      </span>
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
                          className="text-green-600"
                          onClick={() => navigate(`/tickets/${request.converted_ticket_id}`)}
                        >
                          Ver Ticket
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
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Nome do Cliente *</Label>
                <Input
                  value={convertData.customer_name}
                  onChange={(e) => setConvertData({...convertData, customer_name: e.target.value})}
                />
              </div>
              <div>
                <Label>Telefone *</Label>
                <Input
                  value={convertData.customer_phone}
                  onChange={(e) => setConvertData({...convertData, customer_phone: e.target.value})}
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
              <div>
                <Label>Matrícula</Label>
                <Input
                  value={convertData.vehicle_plate}
                  onChange={(e) => setConvertData({...convertData, vehicle_plate: e.target.value.toUpperCase()})}
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
