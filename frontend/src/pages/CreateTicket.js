import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { ArrowLeft, Save, Phone, User, Car, FileText, AlertCircle, Search, History } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const CreateTicket = () => {
  const { user, getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const phoneRef = useRef(null);
  const searchTimeoutRef = useRef(null);
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  
  const [formData, setFormData] = useState({
    customer_phone: '',
    customer_name: '',
    customer_email: '',
    vehicle_plate: '',
    type: user?.role === 'INTERNAL_CREATOR' ? 'INTERNO' : 'INFORMACAO',
    channel: 'TELEFONE',
    priority: 'NORMAL',
    description: ''
  });

  useEffect(() => {
    // Auto-focus phone input
    if (phoneRef.current) {
      phoneRef.current.focus();
    }
  }, []);

  // Search customers as user types
  const searchCustomers = useCallback(async (query) => {
    if (query.length < 2) {
      setSearchResults([]);
      setShowSuggestions(false);
      return;
    }

    try {
      const response = await axios.get(
        `${API_URL}/api/customers/search?q=${encodeURIComponent(query)}`,
        { headers: getAuthHeaders() }
      );
      setSearchResults(response.data);
      setShowSuggestions(response.data.length > 0);
    } catch (error) {
      console.error('Error searching customers:', error);
    }
  }, [getAuthHeaders]);

  const handlePhoneChange = (value) => {
    setFormData(prev => ({ ...prev, customer_phone: value }));
    setSelectedCustomer(null);
    
    // Debounce search
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      searchCustomers(value);
    }, 300);
  };

  const handlePlateChange = (value) => {
    const upperValue = value.toUpperCase();
    setFormData(prev => ({ ...prev, vehicle_plate: upperValue }));
    setSelectedCustomer(null);
    
    // Debounce search
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      searchCustomers(upperValue);
    }, 300);
  };

  const selectCustomer = (customer) => {
    setSelectedCustomer(customer);
    setFormData(prev => ({
      ...prev,
      customer_name: customer.name,
      customer_phone: customer.phones?.[0] || prev.customer_phone,
      customer_email: customer.emails?.[0] || '',
      vehicle_plate: customer.vehicle_plate || prev.vehicle_plate
    }));
    setShowSuggestions(false);
    setSearchResults([]);
  };

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.customer_phone || !formData.customer_name) {
      toast.error('Telefone e nome são obrigatórios');
      return;
    }
    
    setLoading(true);
    try {
      const response = await axios.post(
        `${API_URL}/api/tickets`,
        formData,
        { headers: getAuthHeaders() }
      );
      toast.success('Ticket criado com sucesso!');
      navigate(`/tickets/${response.data.id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar ticket');
    } finally {
      setLoading(false);
    }
  };

  const typeOptions = user?.role === 'INTERNAL_CREATOR' 
    ? [{ value: 'INTERNO', label: 'Interno' }]
    : [
        { value: 'ORCAMENTO_PNEUS', label: 'Orçamento Pneus' },
        { value: 'ORCAMENTO_MECANICA', label: 'Orçamento Mecânica' },
        { value: 'MARCACAO', label: 'Marcação' },
        { value: 'INFORMACAO', label: 'Informação' },
        { value: 'FINANCEIRO', label: 'Financeiro' },
        { value: 'INTERNO', label: 'Interno' },
        { value: 'RECLAMACAO', label: 'Reclamação' }
      ];

  const channelOptions = [
    { value: 'TELEFONE', label: 'Telefone' },
    { value: 'BALCAO', label: 'Balcão' },
    { value: 'FORMULARIO', label: 'Formulário' },
    { value: 'EMAIL', label: 'Email' },
    { value: 'WHATSAPP', label: 'WhatsApp' },
    { value: 'TELEGRAM', label: 'Telegram' }
  ];

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <Button 
          variant="ghost" 
          onClick={() => navigate(-1)}
          className="mb-4"
          data-testid="back-btn"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Voltar
        </Button>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight">
          Novo Ticket
        </h1>
        <p className="text-zinc-500 mt-1">
          Preencha os dados para criar um novo pedido
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader className="border-b bg-zinc-50/50">
            <CardTitle className="text-lg flex items-center gap-2">
              <User className="h-5 w-5 text-orange-600" />
              Dados do Cliente
            </CardTitle>
            <CardDescription>Informação obrigatória marcada com * | Digite telefone ou matrícula para pesquisar cliente</CardDescription>
          </CardHeader>
          <CardContent className="p-6 space-y-5">
            {/* Customer selected banner */}
            {selectedCustomer && (
              <div className="flex items-center gap-3 p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
                <History className="h-5 w-5 text-emerald-600" />
                <div className="flex-1">
                  <p className="font-semibold text-emerald-800">Cliente existente selecionado</p>
                  <p className="text-sm text-emerald-600">{selectedCustomer.name}</p>
                </div>
                <Button 
                  type="button"
                  variant="ghost" 
                  size="sm"
                  onClick={() => setSelectedCustomer(null)}
                  className="text-emerald-600"
                >
                  Limpar
                </Button>
              </div>
            )}

            {/* Phone and Name - Required */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2 relative">
                <Label htmlFor="phone" className="text-sm font-semibold">
                  Telefone *
                </Label>
                <div className="relative">
                  <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-zinc-400" />
                  <Input
                    ref={phoneRef}
                    id="phone"
                    placeholder="912 345 678"
                    value={formData.customer_phone}
                    onChange={(e) => handlePhoneChange(e.target.value)}
                    onFocus={() => searchResults.length > 0 && setShowSuggestions(true)}
                    className="h-12 pl-11 border-2 focus:border-orange-500"
                    required
                    autoComplete="off"
                    data-testid="ticket-phone-input"
                  />
                  {/* Suggestions dropdown */}
                  {showSuggestions && searchResults.length > 0 && (
                    <div className="absolute top-full left-0 right-0 mt-1 bg-white border-2 border-orange-200 rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto">
                      <div className="p-2 bg-orange-50 border-b text-xs font-semibold text-orange-700">
                        <Search className="h-3 w-3 inline mr-1" />
                        Clientes encontrados
                      </div>
                      {searchResults.map((customer) => (
                        <div
                          key={customer.id}
                          className="p-3 hover:bg-zinc-50 cursor-pointer border-b last:border-0"
                          onClick={() => selectCustomer(customer)}
                        >
                          <p className="font-semibold text-slate-900">{customer.name}</p>
                          <div className="flex items-center gap-3 text-sm text-zinc-500 mt-1">
                            {customer.phones?.[0] && (
                              <span className="flex items-center gap-1">
                                <Phone className="h-3 w-3" />
                                {customer.phones[0]}
                              </span>
                            )}
                            {customer.vehicle_plate && (
                              <span className="flex items-center gap-1">
                                <Car className="h-3 w-3" />
                                {customer.vehicle_plate}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="name" className="text-sm font-semibold">
                  Nome *
                </Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-zinc-400" />
                  <Input
                    id="name"
                    placeholder="Nome do cliente"
                    value={formData.customer_name}
                    onChange={(e) => handleChange('customer_name', e.target.value)}
                    className="h-12 pl-11 border-2 focus:border-orange-500"
                    required
                    data-testid="ticket-name-input"
                  />
                </div>
              </div>
            </div>

            {/* Email and Plate - Optional */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="email" className="text-sm font-semibold">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="email@exemplo.pt"
                  value={formData.customer_email}
                  onChange={(e) => handleChange('customer_email', e.target.value)}
                  className="h-12 border-2 focus:border-orange-500"
                  data-testid="ticket-email-input"
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="plate" className="text-sm font-semibold">
                  Matrícula
                </Label>
                <div className="relative">
                  <Car className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-zinc-400" />
                  <Input
                    id="plate"
                    placeholder="AA-00-AA"
                    value={formData.vehicle_plate}
                    onChange={(e) => handleChange('vehicle_plate', e.target.value.toUpperCase())}
                    className="h-12 pl-11 border-2 focus:border-orange-500 uppercase"
                    data-testid="ticket-plate-input"
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="mt-6">
          <CardHeader className="border-b bg-zinc-50/50">
            <CardTitle className="text-lg flex items-center gap-2">
              <FileText className="h-5 w-5 text-orange-600" />
              Detalhes do Pedido
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6 space-y-5">
            {/* Type, Channel, Priority */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label className="text-sm font-semibold">Tipo</Label>
                <Select 
                  value={formData.type} 
                  onValueChange={(value) => handleChange('type', value)}
                  disabled={user?.role === 'INTERNAL_CREATOR'}
                >
                  <SelectTrigger className="h-12 border-2" data-testid="ticket-type-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {typeOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-sm font-semibold">Canal</Label>
                <Select 
                  value={formData.channel} 
                  onValueChange={(value) => handleChange('channel', value)}
                >
                  <SelectTrigger className="h-12 border-2" data-testid="ticket-channel-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {channelOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-sm font-semibold">Prioridade</Label>
                <Select 
                  value={formData.priority} 
                  onValueChange={(value) => handleChange('priority', value)}
                >
                  <SelectTrigger className="h-12 border-2" data-testid="ticket-priority-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="NORMAL">Normal</SelectItem>
                    <SelectItem value="URGENTE">Urgente</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="description" className="text-sm font-semibold">
                Descrição
              </Label>
              <Textarea
                id="description"
                placeholder="Descreva o pedido do cliente..."
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                className="min-h-[120px] border-2 focus:border-orange-500"
                data-testid="ticket-description-input"
              />
            </div>

            {/* Priority warning */}
            {formData.priority === 'URGENTE' && (
              <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
                <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
                <div>
                  <p className="font-semibold text-red-800">Ticket Urgente</p>
                  <p className="text-sm text-red-600">
                    Este ticket será marcado como prioridade alta e terá SLAs reduzidos.
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Submit */}
        <div className="mt-6 flex justify-end gap-3">
          <Button 
            type="button" 
            variant="outline" 
            onClick={() => navigate(-1)}
            className="h-12 px-6 border-2"
            data-testid="cancel-btn"
          >
            Cancelar
          </Button>
          <Button 
            type="submit" 
            className="h-14 px-8 text-lg font-bold bg-orange-600 hover:bg-orange-700 active:scale-95 transition-all"
            disabled={loading}
            data-testid="submit-ticket-btn"
          >
            {loading ? (
              <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <Save className="h-5 w-5 mr-2" />
                Criar Ticket
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
};

export default CreateTicket;
