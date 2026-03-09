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
  XCircle
} from 'lucide-react';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const IntakePage = () => {
  const { getAuthHeaders, user } = useAuth();
  const navigate = useNavigate();
  
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [moduleEnabled, setModuleEnabled] = useState(false);
  const [checkingModule, setCheckingModule] = useState(true);
  
  // Edit dialog
  const [editDialog, setEditDialog] = useState(false);
  const [editingRequest, setEditingRequest] = useState(null);
  
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
      PENDING: { label: 'Pendente', variant: 'secondary', icon: Clock },
      PROCESSING: { label: 'Em Processamento', variant: 'default', icon: RefreshCw },
      CONVERTED: { label: 'Convertido', variant: 'success', icon: CheckCircle2 },
      REJECTED: { label: 'Rejeitado', variant: 'destructive', icon: XCircle }
    };
    const { label, variant, icon: Icon } = config[status] || config.PENDING;
    return (
      <Badge variant={variant} className="flex items-center gap-1">
        <Icon className="h-3 w-3" />
        {label}
      </Badge>
    );
  };

  // Source badge
  const getSourceBadge = (source) => {
    const colors = {
      telegram: 'bg-blue-100 text-blue-800',
      whatsapp: 'bg-green-100 text-green-800',
      email: 'bg-purple-100 text-purple-800',
      web_form: 'bg-gray-100 text-gray-800'
    };
    return (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[source] || colors.web_form}`}>
        {source}
      </span>
    );
  };

  // Edit handlers
  const handleEdit = (request) => {
    setEditingRequest({ ...request });
    setEditDialog(true);
  };

  const handleSaveEdit = async () => {
    try {
      await axios.put(
        `${API_URL}/api/intake/${editingRequest.id}`,
        {
          sender_name: editingRequest.sender_name,
          sender_contact: editingRequest.sender_contact,
          raw_text: editingRequest.raw_text,
          license_plate: editingRequest.license_plate,
          tire_size: editingRequest.tire_size
        },
        { headers: getAuthHeaders() }
      );
      toast.success('Pedido atualizado');
      setEditDialog(false);
      fetchRequests();
    } catch (error) {
      toast.error('Erro ao atualizar pedido');
    }
  };

  // Delete handler
  const handleDelete = async (id) => {
    if (!window.confirm('Tem certeza que deseja eliminar este pedido?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/intake/${id}`, {
        headers: getAuthHeaders()
      });
      toast.success('Pedido eliminado');
      fetchRequests();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao eliminar pedido');
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
      toast.error(error.response?.data?.detail || 'Erro ao converter pedido');
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-zinc-800 flex items-center gap-2">
            <Inbox className="h-7 w-7 text-orange-500" />
            Pedidos de Entrada
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Pedidos recebidos de canais externos aguardando conversão em tickets
          </p>
        </div>
        <Button onClick={fetchRequests} variant="outline" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {['PENDING', 'PROCESSING', 'CONVERTED', 'REJECTED'].map(status => {
          const count = requests.filter(r => r.status === status).length;
          return (
            <Card key={status}>
              <CardContent className="p-4 flex items-center justify-between">
                {getStatusBadge(status)}
                <span className="text-2xl font-bold">{count}</span>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Lista de Pedidos</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <RefreshCw className="h-6 w-6 animate-spin text-zinc-400" />
            </div>
          ) : requests.length === 0 ? (
            <div className="text-center py-8 text-zinc-500">
              <Inbox className="h-12 w-12 mx-auto mb-2 text-zinc-300" />
              Nenhum pedido de entrada
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Origem</TableHead>
                  <TableHead>Remetente</TableHead>
                  <TableHead>Contacto</TableHead>
                  <TableHead>Mensagem</TableHead>
                  <TableHead>Matrícula</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {requests.map(request => (
                  <TableRow key={request.id} data-testid={`intake-row-${request.id}`}>
                    <TableCell>{getSourceBadge(request.source)}</TableCell>
                    <TableCell className="font-medium">{request.sender_name}</TableCell>
                    <TableCell>{request.sender_contact}</TableCell>
                    <TableCell className="max-w-xs truncate" title={request.raw_text}>
                      {request.raw_text}
                    </TableCell>
                    <TableCell>{request.license_plate || '-'}</TableCell>
                    <TableCell>{getStatusBadge(request.status)}</TableCell>
                    <TableCell className="text-sm text-zinc-500">
                      {new Date(request.created_at).toLocaleDateString('pt-PT')}
                    </TableCell>
                    <TableCell className="text-right">
                      {request.status !== 'CONVERTED' && (
                        <div className="flex justify-end gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleEdit(request)}
                            data-testid={`intake-edit-${request.id}`}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-green-600 hover:text-green-700"
                            onClick={() => handleConvert(request)}
                            data-testid={`intake-convert-${request.id}`}
                          >
                            <ArrowRight className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-red-600 hover:text-red-700"
                            onClick={() => handleDelete(request.id)}
                            data-testid={`intake-delete-${request.id}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      )}
                      {request.status === 'CONVERTED' && request.converted_ticket_id && (
                        <Button
                          size="sm"
                          variant="link"
                          onClick={() => navigate(`/tickets/${request.converted_ticket_id}`)}
                        >
                          Ver Ticket
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      <Dialog open={editDialog} onOpenChange={setEditDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar Pedido</DialogTitle>
          </DialogHeader>
          {editingRequest && (
            <div className="space-y-4">
              <div>
                <Label>Nome do Remetente</Label>
                <Input
                  value={editingRequest.sender_name}
                  onChange={(e) => setEditingRequest({...editingRequest, sender_name: e.target.value})}
                />
              </div>
              <div>
                <Label>Contacto</Label>
                <Input
                  value={editingRequest.sender_contact}
                  onChange={(e) => setEditingRequest({...editingRequest, sender_contact: e.target.value})}
                />
              </div>
              <div>
                <Label>Mensagem</Label>
                <Textarea
                  value={editingRequest.raw_text}
                  onChange={(e) => setEditingRequest({...editingRequest, raw_text: e.target.value})}
                  rows={4}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Matrícula</Label>
                  <Input
                    value={editingRequest.license_plate || ''}
                    onChange={(e) => setEditingRequest({...editingRequest, license_plate: e.target.value})}
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
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialog(false)}>Cancelar</Button>
            <Button onClick={handleSaveEdit}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Convert Dialog */}
      <Dialog open={convertDialog} onOpenChange={setConvertDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Converter em Ticket</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
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
                  onChange={(e) => setConvertData({...convertData, vehicle_plate: e.target.value})}
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
            <Button variant="outline" onClick={() => setConvertDialog(false)}>Cancelar</Button>
            <Button onClick={handleConvertSubmit} className="gap-2">
              <FileText className="h-4 w-4" />
              Criar Ticket
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default IntakePage;
