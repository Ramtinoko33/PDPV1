import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { toast } from 'sonner';
import { 
  Search, 
  Plus, 
  Filter, 
  ChevronRight, 
  Phone, 
  Car,
  RefreshCw,
  X,
  AlertTriangle,
  Clock
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TicketList = () => {
  const { user, getAuthHeaders } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tickets, setTickets] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(false);

  const [filters, setFilters] = useState({
    search: searchParams.get('search') || '',
    status: searchParams.get('status') || '',
    type: searchParams.get('type') || '',
    assigned_to: searchParams.get('assigned_to') || '',
    channel: searchParams.get('channel') || '',
    overdue: searchParams.get('overdue') || ''
  });

  const fetchTickets = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.search) params.append('search', filters.search);
      if (filters.status) params.append('status', filters.status);
      if (filters.type) params.append('type', filters.type);
      if (filters.assigned_to) params.append('assigned_to', filters.assigned_to);
      if (filters.channel) params.append('channel', filters.channel);
      if (filters.overdue === 'true') params.append('overdue', 'true');

      const response = await axios.get(
        `${API_URL}/api/tickets?${params.toString()}`,
        { headers: getAuthHeaders() }
      );
      setTickets(response.data);
    } catch (error) {
      toast.error('Erro ao carregar tickets');
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
    fetchTickets();
    fetchUsers();
  }, []);

  useEffect(() => {
    // Update URL params
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    setSearchParams(params);
  }, [filters]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchTickets();
  };

  const clearFilters = () => {
    setFilters({
      search: '',
      status: '',
      type: '',
      assigned_to: '',
      channel: '',
      overdue: ''
    });
    setTimeout(fetchTickets, 100);
  };

  const handleAssignChange = async (ticketId, userId) => {
    try {
      await axios.put(
        `${API_URL}/api/tickets/${ticketId}`,
        { assigned_to_user_id: userId || '' },
        { headers: getAuthHeaders() }
      );
      toast.success('Ticket atribuído');
      fetchTickets();
    } catch (error) {
      toast.error('Erro ao atribuir ticket');
    }
  };

  const handleStatusChange = async (ticketId, status) => {
    try {
      await axios.put(
        `${API_URL}/api/tickets/${ticketId}`,
        { status },
        { headers: getAuthHeaders() }
      );
      toast.success('Estado atualizado');
      fetchTickets();
    } catch (error) {
      toast.error('Erro ao atualizar estado');
    }
  };

  const statusOptions = [
    { value: 'NOVO', label: 'Novo' },
    { value: 'TRIAGEM', label: 'Triagem' },
    { value: 'EM_ORCAMENTO', label: 'Em Orçamento' },
    { value: 'AGUARDA_CLIENTE', label: 'Aguarda Cliente' },
    { value: 'AGUARDA_PECA', label: 'Aguarda Peça' },
    { value: 'AGENDADO', label: 'Agendado' },
    { value: 'FINANCEIRO', label: 'Financeiro' },
    { value: 'CONCLUIDO', label: 'Concluído' },
    { value: 'CANCELADO', label: 'Cancelado' }
  ];

  const typeOptions = [
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

  const statusLabels = Object.fromEntries(statusOptions.map(o => [o.value, o.label]));
  const typeLabels = Object.fromEntries(typeOptions.map(o => [o.value, o.label]));

  const getStatusClass = (status) => {
    const classes = {
      NOVO: 'status-novo',
      TRIAGEM: 'status-triagem',
      EM_ORCAMENTO: 'status-em-orcamento',
      AGUARDA_CLIENTE: 'status-aguarda-cliente',
      AGUARDA_PECA: 'status-aguarda-peca',
      AGENDADO: 'status-agendado',
      FINANCEIRO: 'status-financeiro',
      CONCLUIDO: 'status-concluido',
      CANCELADO: 'status-cancelado'
    };
    return classes[status] || 'bg-zinc-100 text-zinc-700';
  };

  const hasActiveFilters = Object.values(filters).some(v => v && v !== '');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">
            Tickets
          </h1>
          <p className="text-zinc-500">
            {tickets.length} ticket{tickets.length !== 1 ? 's' : ''} encontrado{tickets.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-3">
          <Button 
            variant="outline" 
            onClick={fetchTickets}
            className="border-2"
            data-testid="refresh-tickets-btn"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          {['ADMIN', 'SUPERVISOR', 'AGENT'].includes(user?.role) && (
            <Link to="/tickets/new">
              <Button 
                className="h-12 px-6 font-bold bg-orange-600 hover:bg-orange-700"
                data-testid="new-ticket-btn"
              >
                <Plus className="h-5 w-5 mr-2" />
                Novo Ticket
              </Button>
            </Link>
          )}
        </div>
      </div>

      {/* Search & Filters */}
      <Card>
        <CardContent className="p-4">
          <form onSubmit={handleSearch} className="flex gap-3 mb-4">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-zinc-400" />
              <Input
                placeholder="Pesquisar por telefone, matrícula ou nº ticket..."
                value={filters.search}
                onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
                className="h-12 pl-12 border-2"
                data-testid="tickets-search-input"
              />
            </div>
            <Button 
              type="button" 
              variant="outline"
              onClick={() => setShowFilters(!showFilters)}
              className={`h-12 border-2 ${hasActiveFilters ? 'border-orange-500 text-orange-600' : ''}`}
              data-testid="toggle-filters-btn"
            >
              <Filter className="h-4 w-4 mr-2" />
              Filtros
              {hasActiveFilters && (
                <Badge className="ml-2 bg-orange-100 text-orange-700">Ativo</Badge>
              )}
            </Button>
            <Button 
              type="submit" 
              className="h-12 px-6 font-bold bg-slate-900 hover:bg-slate-800"
              data-testid="search-tickets-btn"
            >
              Pesquisar
            </Button>
          </form>

          {/* Filter panel */}
          {showFilters && (
            <div className="pt-4 border-t space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Select 
                  value={filters.status} 
                  onValueChange={(value) => setFilters(prev => ({ ...prev, status: value }))}
                >
                  <SelectTrigger className="h-10" data-testid="filter-status">
                    <SelectValue placeholder="Estado" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os estados</SelectItem>
                    {statusOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select 
                  value={filters.type} 
                  onValueChange={(value) => setFilters(prev => ({ ...prev, type: value }))}
                >
                  <SelectTrigger className="h-10" data-testid="filter-type">
                    <SelectValue placeholder="Tipo" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os tipos</SelectItem>
                    {typeOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select 
                  value={filters.channel} 
                  onValueChange={(value) => setFilters(prev => ({ ...prev, channel: value }))}
                >
                  <SelectTrigger className="h-10" data-testid="filter-channel">
                    <SelectValue placeholder="Canal" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Todos os canais</SelectItem>
                    {channelOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select 
                  value={filters.overdue} 
                  onValueChange={(value) => setFilters(prev => ({ ...prev, overdue: value }))}
                >
                  <SelectTrigger className="h-10" data-testid="filter-overdue">
                    <SelectValue placeholder="SLA" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Todos</SelectItem>
                    <SelectItem value="true">Atrasados</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {['ADMIN', 'SUPERVISOR'].includes(user?.role) && users.length > 0 && (
                <Select 
                  value={filters.assigned_to} 
                  onValueChange={(value) => setFilters(prev => ({ ...prev, assigned_to: value }))}
                >
                  <SelectTrigger className="h-10 max-w-xs" data-testid="filter-assigned">
                    <SelectValue placeholder="Atribuído a" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Todos</SelectItem>
                    {users.map(u => (
                      <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}

              {hasActiveFilters && (
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={clearFilters}
                  className="text-zinc-500"
                  data-testid="clear-filters-btn"
                >
                  <X className="h-4 w-4 mr-1" />
                  Limpar filtros
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tickets Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : tickets.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <div className="w-16 h-16 bg-zinc-100 rounded-full flex items-center justify-center mb-4">
                <Search className="h-8 w-8 text-zinc-400" />
              </div>
              <p className="text-lg font-medium text-zinc-600">Nenhum ticket encontrado</p>
              <p className="text-sm text-zinc-400 mt-1">Tente ajustar os filtros de pesquisa</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-zinc-50/80">
                    <TableHead className="font-bold">Nº Ticket</TableHead>
                    <TableHead className="font-bold">Cliente</TableHead>
                    <TableHead className="font-bold">Tipo</TableHead>
                    <TableHead className="font-bold">Estado</TableHead>
                    {['ADMIN', 'SUPERVISOR'].includes(user?.role) && (
                      <TableHead className="font-bold">Atribuído</TableHead>
                    )}
                    <TableHead className="font-bold">SLA</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tickets.map((ticket) => (
                    <TableRow 
                      key={ticket.id} 
                      className="hover:bg-zinc-50/50 cursor-pointer"
                      data-testid={`ticket-row-${ticket.id}`}
                    >
                      <TableCell>
                        <span className="font-mono text-sm font-semibold text-orange-600">
                          {ticket.ticket_number}
                        </span>
                        <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                          ticket.priority === 'URGENTE' ? 'priority-urgente' : ''
                        }`}>
                          {ticket.priority === 'URGENTE' && 'URGENTE'}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div>
                          <p className="font-semibold text-slate-900">{ticket.customer_name}</p>
                          <div className="flex items-center gap-3 text-sm text-zinc-500 mt-0.5">
                            <span className="flex items-center gap-1">
                              <Phone className="h-3 w-3" />
                              {ticket.customer_phone}
                            </span>
                            {ticket.vehicle_plate && (
                              <span className="flex items-center gap-1">
                                <Car className="h-3 w-3" />
                                {ticket.vehicle_plate}
                              </span>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs font-medium">
                          {typeLabels[ticket.type] || ticket.type}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {['ADMIN', 'SUPERVISOR'].includes(user?.role) ? (
                          <Select
                            value={ticket.status}
                            onValueChange={(value) => handleStatusChange(ticket.id, value)}
                          >
                            <SelectTrigger className={`h-8 w-36 text-xs ${getStatusClass(ticket.status)}`}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {statusOptions.map(opt => (
                                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Badge className={`text-xs ${getStatusClass(ticket.status)}`}>
                            {statusLabels[ticket.status]}
                          </Badge>
                        )}
                      </TableCell>
                      {['ADMIN', 'SUPERVISOR'].includes(user?.role) && (
                        <TableCell>
                          <Select
                            value={ticket.assigned_to_user_id || ''}
                            onValueChange={(value) => handleAssignChange(ticket.id, value)}
                          >
                            <SelectTrigger className="h-8 w-32 text-xs">
                              <SelectValue placeholder="Ninguém" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="">Ninguém</SelectItem>
                              {users.map(u => (
                                <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </TableCell>
                      )}
                      <TableCell>
                        {ticket.is_overdue ? (
                          <Badge className="sla-overdue text-xs">
                            <AlertTriangle className="h-3 w-3 mr-1" />
                            Atrasado
                          </Badge>
                        ) : (
                          <Badge className="sla-ok text-xs">
                            <Clock className="h-3 w-3 mr-1" />
                            OK
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Link to={`/tickets/${ticket.id}`}>
                          <Button variant="ghost" size="sm" data-testid={`view-ticket-${ticket.id}`}>
                            <ChevronRight className="h-4 w-4" />
                          </Button>
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default TicketList;
