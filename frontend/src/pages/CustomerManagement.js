import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogClose } from '../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { ScrollArea } from '../components/ui/scroll-area';
import { toast } from 'sonner';
import { 
  Search, 
  Plus, 
  Upload, 
  Users, 
  Car, 
  Phone, 
  Mail, 
  MapPin,
  Building2,
  FileSpreadsheet,
  ChevronRight,
  Trash2,
  History,
  Ticket,
  RefreshCw,
  X
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const CustomerManagement = () => {
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [customerHistory, setCustomerHistory] = useState(null);
  const [importing, setImporting] = useState(false);

  const [formData, setFormData] = useState({
    name: '',
    nif: '',
    customer_type: '',
    address: '',
    phones: [''],
    emails: [''],
    vehicles: [{ plate: '', model: '' }]
  });

  const fetchCustomers = async () => {
    setLoading(true);
    try {
      const params = searchQuery ? `?search=${encodeURIComponent(searchQuery)}` : '';
      const response = await axios.get(`${API_URL}/api/customers${params}`, {
        headers: getAuthHeaders()
      });
      setCustomers(response.data);
    } catch (error) {
      toast.error('Erro ao carregar clientes');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCustomers();
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchCustomers();
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImporting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await axios.post(
        `${API_URL}/api/customers/import`,
        formData,
        { headers: { ...getAuthHeaders(), 'Content-Type': 'multipart/form-data' } }
      );
      
      toast.success(`Importados: ${response.data.imported_customers} clientes, ${response.data.imported_vehicles} veículos`);
      if (response.data.errors?.length > 0) {
        toast.warning(`${response.data.errors.length} erros durante importação`);
      }
      fetchCustomers();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao importar ficheiro');
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleCreateCustomer = async (e) => {
    e.preventDefault();
    
    if (!formData.name) {
      toast.error('Nome é obrigatório');
      return;
    }

    try {
      const data = {
        ...formData,
        phones: formData.phones.filter(p => p.trim()),
        emails: formData.emails.filter(e => e.trim()),
        vehicles: formData.vehicles.filter(v => v.plate.trim()).map(v => ({
          plate: v.plate.toUpperCase(),
          model: v.model
        }))
      };
      
      await axios.post(`${API_URL}/api/customers`, data, { headers: getAuthHeaders() });
      toast.success('Cliente criado com sucesso');
      setShowCreateDialog(false);
      setFormData({
        name: '',
        nif: '',
        customer_type: '',
        address: '',
        phones: [''],
        emails: [''],
        vehicles: [{ plate: '', model: '' }]
      });
      fetchCustomers();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar cliente');
    }
  };

  const handleViewHistory = async (customer) => {
    setSelectedCustomer(customer);
    setShowHistoryDialog(true);
    
    try {
      const response = await axios.get(
        `${API_URL}/api/customers/${customer.id}/history`,
        { headers: getAuthHeaders() }
      );
      setCustomerHistory(response.data);
    } catch (error) {
      toast.error('Erro ao carregar histórico');
    }
  };

  const handleDeleteCustomer = async (customerId) => {
    if (!window.confirm('Tem a certeza que deseja eliminar este cliente?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/customers/${customerId}`, { headers: getAuthHeaders() });
      toast.success('Cliente eliminado');
      fetchCustomers();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao eliminar cliente');
    }
  };

  const addPhoneField = () => {
    setFormData(prev => ({ ...prev, phones: [...prev.phones, ''] }));
  };

  const addEmailField = () => {
    setFormData(prev => ({ ...prev, emails: [...prev.emails, ''] }));
  };

  const addVehicleField = () => {
    setFormData(prev => ({ ...prev, vehicles: [...prev.vehicles, { plate: '', model: '' }] }));
  };

  const updatePhone = (index, value) => {
    const newPhones = [...formData.phones];
    newPhones[index] = value;
    setFormData(prev => ({ ...prev, phones: newPhones }));
  };

  const updateEmail = (index, value) => {
    const newEmails = [...formData.emails];
    newEmails[index] = value;
    setFormData(prev => ({ ...prev, emails: newEmails }));
  };

  const updateVehicle = (index, field, value) => {
    const newVehicles = [...formData.vehicles];
    newVehicles[index][field] = value;
    setFormData(prev => ({ ...prev, vehicles: newVehicles }));
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString('pt-PT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    });
  };

  const statusLabels = {
    NOVO: 'Novo',
    TRIAGEM: 'Triagem',
    EM_ORCAMENTO: 'Em Orçamento',
    AGUARDA_CLIENTE: 'Aguarda Cliente',
    AGENDADO: 'Agendado',
    CONCLUIDO: 'Concluído',
    CANCELADO: 'Cancelado'
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">
            Clientes
          </h1>
          <p className="text-zinc-500">
            {customers.length} cliente{customers.length !== 1 ? 's' : ''} registado{customers.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleImport}
          />
          <Button 
            variant="outline" 
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="border-2"
            data-testid="import-customers-btn"
          >
            {importing ? (
              <div className="w-4 h-4 border-2 border-zinc-500 border-t-transparent rounded-full animate-spin mr-2" />
            ) : (
              <Upload className="h-4 w-4 mr-2" />
            )}
            Importar Excel
          </Button>
          <Button 
            className="h-12 px-6 font-bold bg-orange-600 hover:bg-orange-700"
            onClick={() => setShowCreateDialog(true)}
            data-testid="add-customer-btn"
          >
            <Plus className="h-5 w-5 mr-2" />
            Novo Cliente
          </Button>
        </div>
      </div>

      {/* Search */}
      <Card>
        <CardContent className="p-4">
          <form onSubmit={handleSearch} className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-zinc-400" />
              <Input
                placeholder="Pesquisar por nome, NIF, telefone ou email..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-12 pl-12 border-2"
                data-testid="customer-search-input"
              />
            </div>
            <Button 
              type="submit" 
              className="h-12 px-6 font-bold bg-slate-900 hover:bg-slate-800"
              data-testid="search-customers-btn"
            >
              Pesquisar
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Customers Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : customers.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <div className="w-16 h-16 bg-zinc-100 rounded-full flex items-center justify-center mb-4">
                <Users className="h-8 w-8 text-zinc-400" />
              </div>
              <p className="text-lg font-medium text-zinc-600">Nenhum cliente encontrado</p>
              <p className="text-sm text-zinc-400 mt-1">Importe um ficheiro Excel ou adicione manualmente</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-zinc-50/80">
                    <TableHead className="font-bold">Cliente</TableHead>
                    <TableHead className="font-bold">Contactos</TableHead>
                    <TableHead className="font-bold">Veículos</TableHead>
                    <TableHead className="font-bold">Tickets</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {customers.map((customer) => (
                    <TableRow key={customer.id} className="hover:bg-zinc-50/50" data-testid={`customer-row-${customer.id}`}>
                      <TableCell>
                        <div>
                          <p className="font-semibold text-slate-900">{customer.name}</p>
                          {customer.nif && (
                            <p className="text-sm text-zinc-500">NIF: {customer.nif}</p>
                          )}
                          {customer.customer_type && (
                            <Badge variant="outline" className="text-xs mt-1">{customer.customer_type}</Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          {customer.phones?.slice(0, 2).map((phone, i) => (
                            <div key={i} className="flex items-center gap-1 text-sm text-zinc-600">
                              <Phone className="h-3 w-3" />
                              {phone}
                            </div>
                          ))}
                          {customer.emails?.slice(0, 1).map((email, i) => (
                            <div key={i} className="flex items-center gap-1 text-sm text-zinc-600">
                              <Mail className="h-3 w-3" />
                              {email}
                            </div>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          {customer.vehicles?.slice(0, 2).map((v, i) => (
                            <div key={i} className="flex items-center gap-1">
                              <Car className="h-3 w-3 text-zinc-400" />
                              <span className="font-mono text-sm">{v.plate}</span>
                              {v.model && (
                                <span className="text-xs text-zinc-500 truncate max-w-[100px]">{v.model}</span>
                              )}
                            </div>
                          ))}
                          {customer.vehicles?.length > 2 && (
                            <span className="text-xs text-zinc-400">+{customer.vehicles.length - 2} mais</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="font-mono">
                          <Ticket className="h-3 w-3 mr-1" />
                          {customer.ticket_count || 0}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleViewHistory(customer)}
                            data-testid={`view-history-${customer.id}`}
                          >
                            <History className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-600 hover:text-red-700 hover:bg-red-50"
                            onClick={() => handleDeleteCustomer(customer.id)}
                            data-testid={`delete-customer-${customer.id}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Customer Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">Novo Cliente</DialogTitle>
            <CardDescription>Preencha os dados do cliente</CardDescription>
          </DialogHeader>
          <form onSubmit={handleCreateCustomer} className="space-y-6">
            {/* Basic Info */}
            <div className="space-y-4">
              <h3 className="font-semibold text-slate-700 flex items-center gap-2">
                <Building2 className="h-4 w-4" />
                Dados Básicos
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Nome *</Label>
                  <Input
                    value={formData.name}
                    onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    className="border-2"
                    required
                    data-testid="customer-name-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label>NIF</Label>
                  <Input
                    value={formData.nif}
                    onChange={(e) => setFormData(prev => ({ ...prev, nif: e.target.value }))}
                    className="border-2"
                    data-testid="customer-nif-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Tipo de Cliente</Label>
                  <Input
                    value={formData.customer_type}
                    onChange={(e) => setFormData(prev => ({ ...prev, customer_type: e.target.value }))}
                    placeholder="Ex: Particular, Empresa, Frota"
                    className="border-2"
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>Morada</Label>
                  <Input
                    value={formData.address}
                    onChange={(e) => setFormData(prev => ({ ...prev, address: e.target.value }))}
                    className="border-2"
                  />
                </div>
              </div>
            </div>

            {/* Phones */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-slate-700 flex items-center gap-2">
                  <Phone className="h-4 w-4" />
                  Telefones
                </h3>
                <Button type="button" variant="ghost" size="sm" onClick={addPhoneField}>
                  <Plus className="h-4 w-4 mr-1" />
                  Adicionar
                </Button>
              </div>
              <div className="space-y-2">
                {formData.phones.map((phone, index) => (
                  <Input
                    key={index}
                    value={phone}
                    onChange={(e) => updatePhone(index, e.target.value)}
                    placeholder="912 345 678"
                    className="border-2"
                    data-testid={`customer-phone-${index}`}
                  />
                ))}
              </div>
            </div>

            {/* Emails */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-slate-700 flex items-center gap-2">
                  <Mail className="h-4 w-4" />
                  Emails
                </h3>
                <Button type="button" variant="ghost" size="sm" onClick={addEmailField}>
                  <Plus className="h-4 w-4 mr-1" />
                  Adicionar
                </Button>
              </div>
              <div className="space-y-2">
                {formData.emails.map((email, index) => (
                  <Input
                    key={index}
                    type="email"
                    value={email}
                    onChange={(e) => updateEmail(index, e.target.value)}
                    placeholder="email@exemplo.pt"
                    className="border-2"
                    data-testid={`customer-email-${index}`}
                  />
                ))}
              </div>
            </div>

            {/* Vehicles */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-slate-700 flex items-center gap-2">
                  <Car className="h-4 w-4" />
                  Veículos
                </h3>
                <Button type="button" variant="ghost" size="sm" onClick={addVehicleField}>
                  <Plus className="h-4 w-4 mr-1" />
                  Adicionar
                </Button>
              </div>
              <div className="space-y-3">
                {formData.vehicles.map((vehicle, index) => (
                  <div key={index} className="grid grid-cols-2 gap-2">
                    <Input
                      value={vehicle.plate}
                      onChange={(e) => updateVehicle(index, 'plate', e.target.value.toUpperCase())}
                      placeholder="AA-00-AA"
                      className="border-2 uppercase"
                      data-testid={`customer-vehicle-plate-${index}`}
                    />
                    <Input
                      value={vehicle.model}
                      onChange={(e) => updateVehicle(index, 'model', e.target.value)}
                      placeholder="Marca / Modelo"
                      className="border-2"
                      data-testid={`customer-vehicle-model-${index}`}
                    />
                  </div>
                ))}
              </div>
            </div>

            <DialogFooter className="gap-2 pt-4">
              <DialogClose asChild>
                <Button type="button" variant="outline" className="border-2">
                  Cancelar
                </Button>
              </DialogClose>
              <Button 
                type="submit" 
                className="bg-orange-600 hover:bg-orange-700 font-bold"
                data-testid="save-customer-btn"
              >
                Criar Cliente
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Customer History Dialog */}
      <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
        <DialogContent className="sm:max-w-3xl max-h-[90vh]">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <History className="h-5 w-5 text-orange-600" />
              Histórico do Cliente
            </DialogTitle>
            {selectedCustomer && (
              <CardDescription>{selectedCustomer.name}</CardDescription>
            )}
          </DialogHeader>
          
          {customerHistory ? (
            <Tabs defaultValue="tickets" className="w-full">
              <TabsList className="w-full">
                <TabsTrigger value="tickets" className="flex-1">
                  <Ticket className="h-4 w-4 mr-2" />
                  Tickets ({customerHistory.total_tickets})
                </TabsTrigger>
                <TabsTrigger value="vehicles" className="flex-1">
                  <Car className="h-4 w-4 mr-2" />
                  Veículos ({customerHistory.vehicles?.length || 0})
                </TabsTrigger>
                <TabsTrigger value="info" className="flex-1">
                  <Building2 className="h-4 w-4 mr-2" />
                  Dados
                </TabsTrigger>
              </TabsList>

              <TabsContent value="tickets">
                <ScrollArea className="h-[400px]">
                  {customerHistory.tickets?.length === 0 ? (
                    <div className="p-8 text-center text-zinc-500">
                      Nenhum ticket encontrado
                    </div>
                  ) : (
                    <div className="divide-y">
                      {customerHistory.tickets?.map((ticket) => (
                        <div 
                          key={ticket.id}
                          className="p-4 hover:bg-zinc-50 cursor-pointer"
                          onClick={() => {
                            setShowHistoryDialog(false);
                            navigate(`/tickets/${ticket.id}`);
                          }}
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <span className="font-mono text-sm text-orange-600 font-semibold">
                                {ticket.ticket_number}
                              </span>
                              <Badge className="ml-2 text-xs" variant="outline">
                                {statusLabels[ticket.status] || ticket.status}
                              </Badge>
                            </div>
                            <span className="text-sm text-zinc-500">
                              {formatDate(ticket.created_at)}
                            </span>
                          </div>
                          <p className="text-sm text-zinc-600 mt-1 truncate">
                            {ticket.description || 'Sem descrição'}
                          </p>
                          {ticket.vehicle_plate && (
                            <div className="flex items-center gap-1 mt-1 text-xs text-zinc-400">
                              <Car className="h-3 w-3" />
                              {ticket.vehicle_plate}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </TabsContent>

              <TabsContent value="vehicles">
                <ScrollArea className="h-[400px]">
                  {customerHistory.vehicles?.length === 0 ? (
                    <div className="p-8 text-center text-zinc-500">
                      Nenhum veículo registado
                    </div>
                  ) : (
                    <div className="divide-y">
                      {customerHistory.vehicles?.map((vehicle) => (
                        <div key={vehicle.id} className="p-4">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-zinc-100 rounded-lg flex items-center justify-center">
                              <Car className="h-5 w-5 text-zinc-600" />
                            </div>
                            <div>
                              <p className="font-mono font-semibold text-slate-900">{vehicle.plate}</p>
                              {vehicle.model && (
                                <p className="text-sm text-zinc-500">{vehicle.model}</p>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </TabsContent>

              <TabsContent value="info">
                <div className="p-4 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-zinc-500">NIF</p>
                      <p className="font-semibold">{customerHistory.customer?.nif || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-zinc-500">Tipo</p>
                      <p className="font-semibold">{customerHistory.customer?.customer_type || '-'}</p>
                    </div>
                    <div className="col-span-2">
                      <p className="text-sm text-zinc-500">Morada</p>
                      <p className="font-semibold">{customerHistory.customer?.address || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-zinc-500">Telefones</p>
                      {customerHistory.customer?.phones?.map((p, i) => (
                        <p key={i} className="font-semibold">{p}</p>
                      )) || '-'}
                    </div>
                    <div>
                      <p className="text-sm text-zinc-500">Emails</p>
                      {customerHistory.customer?.emails?.map((e, i) => (
                        <p key={i} className="font-semibold">{e}</p>
                      )) || '-'}
                    </div>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          ) : (
            <div className="flex items-center justify-center h-64">
              <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default CustomerManagement;
