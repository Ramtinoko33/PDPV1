import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { 
  Plus, 
  Search, 
  Ticket, 
  AlertTriangle, 
  Clock, 
  FileText,
  ChevronRight,
  Phone,
  Car,
  RefreshCw,
  Bell,
  Calendar,
  CheckCircle
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const Dashboard = () => {
  const { user, getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [recentTickets, setRecentTickets] = useState([]);
  const [overdueTickets, setOverdueTickets] = useState([]);
  const [myReminders, setMyReminders] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const [statsRes, ticketsRes, remindersRes] = await Promise.all([
        axios.get(`${API_URL}/api/dashboard/stats`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/tickets?limit=10`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/reminders/my-today`, { headers: getAuthHeaders() }).catch(() => ({ data: [] }))
      ]);
      
      setStats(statsRes.data);
      setRecentTickets(ticketsRes.data.slice(0, 5));
      setOverdueTickets(ticketsRes.data.filter(t => t.is_overdue).slice(0, 5));
      setMyReminders(remindersRes.data || []);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  const completeReminder = async (reminderId) => {
    try {
      await axios.put(`${API_URL}/api/reminders/${reminderId}/complete`, {}, { headers: getAuthHeaders() });
      toast.success('Lembrete concluído');
      fetchData();
    } catch (error) {
      toast.error('Erro ao concluir lembrete');
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/tickets?search=${encodeURIComponent(searchQuery)}`);
    }
  };

  const statusLabels = {
    ABERTO: 'Aberto',
    EM_TRATAMENTO: 'Em Tratamento',
    AGUARDA_CLIENTE: 'Aguarda Cliente',
    ACEITE_LINK: 'Aceite (Link)',
    REJEITADO_LINK: 'Rejeitado (Link)',
    AGENDADO: 'Agendado',
    FECHADO: 'Fechado'
  };

  const getStatusClass = (status) => {
    const classes = {
      ABERTO: 'status-aberto',
      EM_TRATAMENTO: 'status-em-tratamento',
      AGUARDA_CLIENTE: 'status-aguarda-cliente',
      ACEITE_LINK: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      REJEITADO_LINK: 'bg-red-100 text-red-800 border-red-300',
      AGENDADO: 'bg-purple-100 text-purple-800 border-purple-300',
      FECHADO: 'status-fechado'
    };
    return classes[status] || 'bg-zinc-100 text-zinc-700';
  };

  // For INTERNAL_CREATOR, show simplified view
  if (user?.role === 'INTERNAL_CREATOR') {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="mb-8 text-center">
          <h1 className="text-4xl font-black text-slate-900 tracking-tight mb-2">
            Criar Ticket Interno
          </h1>
          <p className="text-zinc-500">
            Crie tickets internos para comunicação entre equipas
          </p>
        </div>

        <Card className="card-hover">
          <CardContent className="p-8 text-center">
            <div className="w-20 h-20 bg-orange-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
              <Plus className="h-10 w-10 text-orange-600" />
            </div>
            <h2 className="text-2xl font-bold mb-2">Novo Ticket Interno</h2>
            <p className="text-zinc-500 mb-6">
              Clique no botão abaixo para criar um novo ticket interno
            </p>
            <Button 
              size="lg"
              className="h-14 px-8 text-lg font-bold bg-orange-600 hover:bg-orange-700"
              onClick={() => navigate('/tickets/new')}
              data-testid="create-internal-ticket-btn"
            >
              <Plus className="h-5 w-5 mr-2" />
              Criar Ticket
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-12 h-12 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-4xl font-black text-slate-900 tracking-tight mb-1">
            Painel
          </h1>
          <p className="text-zinc-500">
            Bem-vindo, {user?.name}
          </p>
        </div>
        <div className="flex gap-3">
          <Button 
            variant="outline" 
            onClick={fetchData}
            className="border-2"
            data-testid="refresh-dashboard-btn"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Atualizar
          </Button>
          {['ADMIN', 'SUPERVISOR', 'AGENT'].includes(user?.role) && (
            <Button 
              className="h-12 px-6 font-bold bg-orange-600 hover:bg-orange-700"
              onClick={() => navigate('/tickets/new')}
              data-testid="create-ticket-btn"
            >
              <Plus className="h-5 w-5 mr-2" />
              Novo Ticket
            </Button>
          )}
        </div>
      </div>

      {/* Search */}
      <Card>
        <CardContent className="p-4">
          <form onSubmit={handleSearch} className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-zinc-400" />
              <Input
                placeholder="Pesquisar por telefone, matrícula ou nº ticket..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-12 pl-12 border-2"
                data-testid="dashboard-search-input"
              />
            </div>
            <Button 
              type="submit" 
              className="h-12 px-6 font-bold bg-slate-900 hover:bg-slate-800"
              data-testid="dashboard-search-btn"
            >
              Pesquisar
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Link to="/tickets?status=ABERTO" data-testid="stat-novos">
          <Card className="card-hover cursor-pointer border-l-4 border-l-blue-500">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-zinc-500 uppercase tracking-wide">Abertos</p>
                  <p className="text-4xl font-black text-slate-900 mt-1">{stats?.novos || 0}</p>
                </div>
                <div className="w-14 h-14 bg-blue-100 rounded-xl flex items-center justify-center">
                  <Ticket className="h-7 w-7 text-blue-600" />
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>

        <Link to="/tickets?overdue=true" data-testid="stat-atrasados">
          <Card className="card-hover cursor-pointer border-l-4 border-l-red-500">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-zinc-500 uppercase tracking-wide">Atrasados SLA</p>
                  <p className="text-4xl font-black text-slate-900 mt-1">{stats?.atrasados_sla || 0}</p>
                </div>
                <div className="w-14 h-14 bg-red-100 rounded-xl flex items-center justify-center">
                  <AlertTriangle className="h-7 w-7 text-red-600" />
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>

        <Link to="/tickets?status=AGUARDA_CLIENTE" data-testid="stat-aguarda-cliente">
          <Card className="card-hover cursor-pointer border-l-4 border-l-orange-500">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-zinc-500 uppercase tracking-wide">Aguarda Cliente</p>
                  <p className="text-4xl font-black text-slate-900 mt-1">{stats?.aguarda_cliente || 0}</p>
                </div>
                <div className="w-14 h-14 bg-orange-100 rounded-xl flex items-center justify-center">
                  <Clock className="h-7 w-7 text-orange-600" />
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>

        <Link to="/tickets?status=EM_TRATAMENTO" data-testid="stat-em-tratamento">
          <Card className="card-hover cursor-pointer border-l-4 border-l-amber-500">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-zinc-500 uppercase tracking-wide">Em Tratamento</p>
                  <p className="text-4xl font-black text-slate-900 mt-1">{stats?.em_tratamento || 0}</p>
                </div>
                <div className="w-14 h-14 bg-amber-100 rounded-xl flex items-center justify-center">
                  <FileText className="h-7 w-7 text-amber-600" />
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Two columns: Recent and Overdue */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Tickets */}
        <Card>
          <CardHeader className="border-b bg-zinc-50/50 pb-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg font-bold">Tickets Recentes</CardTitle>
              <Link to="/tickets">
                <Button variant="ghost" size="sm" className="text-orange-600 hover:text-orange-700">
                  Ver todos
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {recentTickets.length === 0 ? (
              <div className="p-8 text-center text-zinc-500">
                Nenhum ticket encontrado
              </div>
            ) : (
              <div className="divide-y">
                {recentTickets.map((ticket) => (
                  <Link 
                    key={ticket.id} 
                    to={`/tickets/${ticket.id}`}
                    className={`flex items-center gap-4 p-4 hover:bg-zinc-50 transition-colors ${ticket.priority === 'URGENTE' ? 'bg-red-50/50 border-l-4 border-l-red-500' : ''}`}
                    data-testid={`recent-ticket-${ticket.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`font-mono text-sm font-medium ${ticket.priority === 'URGENTE' ? 'text-red-600 underline decoration-red-400 decoration-2' : 'text-orange-600'}`}>
                          {ticket.ticket_number}
                        </span>
                        {ticket.priority === 'URGENTE' && (
                          <Badge className="priority-urgente text-xs">URGENTE</Badge>
                        )}
                        <Badge className={`text-xs ${getStatusClass(ticket.status)}`}>
                          {statusLabels[ticket.status]}
                        </Badge>
                        {ticket.is_overdue && (
                          <Badge className="sla-overdue text-xs">SLA</Badge>
                        )}
                      </div>
                      <p className={`font-semibold truncate ${ticket.priority === 'URGENTE' ? 'text-red-900' : 'text-slate-900'}`}>
                        {ticket.customer_name}
                      </p>
                      <div className="flex items-center gap-3 text-sm text-zinc-500 mt-1">
                        <span className="flex items-center gap-1">
                          <Phone className="h-3.5 w-3.5" />
                          {ticket.customer_phone}
                        </span>
                        {ticket.vehicle_plate && (
                          <span className="flex items-center gap-1">
                            <Car className="h-3.5 w-3.5" />
                            {ticket.vehicle_plate}
                          </span>
                        )}
                      </div>
                    </div>
                    <ChevronRight className="h-5 w-5 text-zinc-400" />
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Overdue Tickets */}
        <Card className="border-red-200">
          <CardHeader className="border-b bg-red-50/50 pb-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg font-bold text-red-800">
                <AlertTriangle className="h-5 w-5 inline mr-2" />
                Tickets Atrasados
              </CardTitle>
              <Link to="/tickets?overdue=true">
                <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700">
                  Ver todos
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {overdueTickets.length === 0 ? (
              <div className="p-8 text-center text-zinc-500">
                <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-3">
                  <span className="text-3xl">✓</span>
                </div>
                Sem tickets atrasados
              </div>
            ) : (
              <div className="divide-y">
                {overdueTickets.map((ticket) => (
                  <Link 
                    key={ticket.id} 
                    to={`/tickets/${ticket.id}`}
                    className="flex items-center gap-4 p-4 hover:bg-red-50/50 transition-colors"
                    data-testid={`overdue-ticket-${ticket.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-sm font-medium text-red-600">
                          {ticket.ticket_number}
                        </span>
                        <Badge className="sla-overdue text-xs">ATRASADO</Badge>
                      </div>
                      <p className="font-semibold text-slate-900 truncate">
                        {ticket.customer_name}
                      </p>
                      <p className="text-sm text-zinc-500 mt-1">
                        {ticket.customer_phone}
                      </p>
                    </div>
                    <ChevronRight className="h-5 w-5 text-red-400" />
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Dashboard;
