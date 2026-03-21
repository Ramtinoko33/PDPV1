import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Checkbox } from '../components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../components/ui/dialog';
import { toast } from 'sonner';
import { 
  Bell, 
  Plus, 
  Calendar, 
  Trash2, 
  CheckCircle,
  Clock,
  AlertTriangle,
  Ticket,
  Search
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const Reminders = () => {
  const { user, getAuthHeaders } = useAuth();
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [users, setUsers] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [ticketSearch, setTicketSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [newReminder, setNewReminder] = useState({
    description: '',
    due_at: '',
    assigned_to_user_id: '',
    ticket_id: ''
  });

  useEffect(() => {
    fetchReminders();
    fetchUsers();
  }, [filter]);

  const fetchReminders = async () => {
    setLoading(true);
    try {
      const response = await axios.get(
        `${API_URL}/api/reminders?filter=${filter}`,
        { headers: getAuthHeaders() }
      );
      setReminders(response.data);
    } catch (error) {
      console.error('Error fetching reminders:', error);
      toast.error('Erro ao carregar lembretes');
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/users`, { headers: getAuthHeaders() });
      setUsers(response.data.filter(u => u.is_active));
    } catch (error) {
      console.error('Error fetching users:', error);
    }
  };

  const searchTickets = async (query) => {
    if (!query || query.length < 2) {
      setTickets([]);
      return;
    }
    try {
      const response = await axios.get(
        `${API_URL}/api/tickets?search=${encodeURIComponent(query)}&limit=10`,
        { headers: getAuthHeaders() }
      );
      setTickets(response.data.slice(0, 10));
    } catch (error) {
      console.error('Error searching tickets:', error);
    }
  };

  const createReminder = async (e) => {
    e.preventDefault();
    if (!newReminder.description || !newReminder.due_at) {
      toast.error('Preencha descrição e data/hora');
      return;
    }
    setCreating(true);
    try {
      await axios.post(
        `${API_URL}/api/reminders`,
        {
          description: newReminder.description,
          due_at: new Date(newReminder.due_at).toISOString(),
          assigned_to_user_id: newReminder.assigned_to_user_id || null,
          ticket_id: newReminder.ticket_id || null
        },
        { headers: getAuthHeaders() }
      );
      toast.success('Lembrete criado');
      setNewReminder({ description: '', due_at: '', assigned_to_user_id: '', ticket_id: '' });
      setDialogOpen(false);
      fetchReminders();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar lembrete');
    } finally {
      setCreating(false);
    }
  };

  const toggleComplete = async (reminder) => {
    try {
      if (reminder.is_done) {
        await axios.put(`${API_URL}/api/reminders/${reminder.id}/reopen`, {}, { headers: getAuthHeaders() });
        toast.success('Lembrete reaberto');
      } else {
        await axios.put(`${API_URL}/api/reminders/${reminder.id}/complete`, {}, { headers: getAuthHeaders() });
        toast.success('Lembrete concluído');
      }
      fetchReminders();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro');
    }
  };

  const deleteReminder = async (reminderId) => {
    if (!window.confirm('Eliminar este lembrete?')) return;
    try {
      await axios.delete(`${API_URL}/api/reminders/${reminderId}`, { headers: getAuthHeaders() });
      toast.success('Lembrete eliminado');
      fetchReminders();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro');
    }
  };

  const formatDateTime = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleString('pt-PT', { 
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  };

  const formatDateShort = (dateStr) => {
    const date = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    if (date.toDateString() === today.toDateString()) {
      return `Hoje, ${date.toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })}`;
    } else if (date.toDateString() === tomorrow.toDateString()) {
      return `Amanhã, ${date.toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })}`;
    }
    return formatDateTime(dateStr);
  };

  const getDefaultDateTime = () => {
    const now = new Date();
    now.setHours(now.getHours() + 1);
    now.setMinutes(0);
    return now.toISOString().slice(0, 16);
  };

  const pendingCount = reminders.filter(r => !r.is_done).length;
  const overdueCount = reminders.filter(r => r.is_overdue).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 flex items-center gap-3">
            <Bell className="h-8 w-8 text-purple-600" />
            Lembretes
          </h1>
          <p className="text-zinc-600 mt-1">
            Gerencie os seus lembretes e tarefas
          </p>
        </div>
        
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="bg-purple-600 hover:bg-purple-700" data-testid="create-reminder-btn">
              <Plus className="h-4 w-4 mr-2" />
              Novo Lembrete
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[500px]">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-purple-600" />
                Criar Lembrete
              </DialogTitle>
            </DialogHeader>
            <form onSubmit={createReminder} className="space-y-4 pt-4">
              <div>
                <Label>Descrição *</Label>
                <Input
                  value={newReminder.description}
                  onChange={(e) => setNewReminder({ ...newReminder, description: e.target.value })}
                  placeholder="Ex: Encomendar pneus para stock"
                  data-testid="reminder-description-input"
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Data/Hora *</Label>
                  <Input
                    type="datetime-local"
                    value={newReminder.due_at || getDefaultDateTime()}
                    onChange={(e) => setNewReminder({ ...newReminder, due_at: e.target.value })}
                    data-testid="reminder-datetime-input"
                  />
                </div>
                <div>
                  <Label>Atribuir a</Label>
                  {['ADMIN', 'SUPERVISOR'].includes(user?.role) ? (
                    <Select
                      value={newReminder.assigned_to_user_id || "self"}
                      onValueChange={(v) => setNewReminder({ ...newReminder, assigned_to_user_id: v === "self" ? "" : v })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Eu próprio" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="self">Eu próprio</SelectItem>
                        {users.map(u => (
                          <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input value="Eu próprio" disabled className="bg-zinc-100" />
                  )}
                </div>
              </div>
              
              <div>
                <Label>Associar a Ticket (opcional)</Label>
                <div className="space-y-2">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-zinc-400" />
                    <Input
                      value={ticketSearch}
                      onChange={(e) => {
                        setTicketSearch(e.target.value);
                        searchTickets(e.target.value);
                      }}
                      placeholder="Pesquisar ticket..."
                      className="pl-10"
                    />
                  </div>
                  {tickets.length > 0 && (
                    <div className="border rounded-lg max-h-40 overflow-y-auto">
                      {tickets.map(t => (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => {
                            setNewReminder({ ...newReminder, ticket_id: t.id });
                            setTicketSearch(`${t.ticket_number} - ${t.customer_name}`);
                            setTickets([]);
                          }}
                          className="w-full text-left px-3 py-2 hover:bg-zinc-50 border-b last:border-b-0"
                        >
                          <span className="font-mono text-purple-600 text-sm">{t.ticket_number}</span>
                          <span className="text-zinc-600 ml-2">{t.customer_name}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {newReminder.ticket_id && (
                    <div className="flex items-center gap-2 p-2 bg-purple-50 rounded">
                      <Ticket className="h-4 w-4 text-purple-600" />
                      <span className="text-sm text-purple-700 flex-1">{ticketSearch}</span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setNewReminder({ ...newReminder, ticket_id: '' });
                          setTicketSearch('');
                        }}
                        className="h-6 w-6 p-0"
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="flex justify-end gap-2 pt-4">
                <Button type="button" variant="ghost" onClick={() => setDialogOpen(false)}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={creating} className="bg-purple-600 hover:bg-purple-700">
                  {creating ? 'A criar...' : 'Criar Lembrete'}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="border-l-4 border-l-purple-500">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Pendentes</p>
                <p className="text-2xl font-bold">{pendingCount}</p>
              </div>
              <Clock className="h-8 w-8 text-purple-500" />
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-red-500">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Atrasados</p>
                <p className="text-2xl font-bold">{overdueCount}</p>
              </div>
              <AlertTriangle className="h-8 w-8 text-red-500" />
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-green-500">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Concluídos</p>
                <p className="text-2xl font-bold">{reminders.filter(r => r.is_done).length}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Reminders List */}
      <Card>
        <CardHeader className="border-b">
          <Tabs value={filter} onValueChange={setFilter}>
            <TabsList>
              <TabsTrigger value="pending">Pendentes</TabsTrigger>
              <TabsTrigger value="today">Hoje</TabsTrigger>
              <TabsTrigger value="week">Esta Semana</TabsTrigger>
              <TabsTrigger value="overdue">Atrasados</TabsTrigger>
              <TabsTrigger value="all">Todos</TabsTrigger>
            </TabsList>
          </Tabs>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center text-zinc-500">A carregar...</div>
          ) : reminders.length === 0 ? (
            <div className="p-8 text-center">
              <Bell className="h-12 w-12 text-zinc-300 mx-auto mb-4" />
              <p className="text-zinc-500">Sem lembretes nesta categoria</p>
              <Button 
                variant="outline" 
                className="mt-4"
                onClick={() => setDialogOpen(true)}
              >
                <Plus className="h-4 w-4 mr-2" />
                Criar Lembrete
              </Button>
            </div>
          ) : (
            <div className="divide-y">
              {reminders.map((reminder) => (
                <div
                  key={reminder.id}
                  className={`flex items-center gap-4 p-4 hover:bg-zinc-50 ${
                    reminder.is_done 
                      ? 'bg-zinc-50' 
                      : reminder.is_overdue 
                        ? 'bg-red-50' 
                        : ''
                  }`}
                >
                  <Checkbox
                    checked={reminder.is_done}
                    onCheckedChange={() => toggleComplete(reminder)}
                    className={`h-5 w-5 ${reminder.is_overdue && !reminder.is_done ? 'border-red-500' : ''}`}
                  />
                  
                  <div className="flex-1 min-w-0">
                    <p className={`font-medium ${reminder.is_done ? 'line-through text-zinc-500' : 'text-slate-900'}`}>
                      {reminder.description}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-zinc-500">
                      <div className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        <span className={reminder.is_overdue && !reminder.is_done ? 'text-red-600 font-semibold' : ''}>
                          {formatDateShort(reminder.due_at)}
                        </span>
                      </div>
                      {reminder.is_overdue && !reminder.is_done && (
                        <Badge className="bg-red-100 text-red-700 text-xs">ATRASADO</Badge>
                      )}
                      {reminder.is_done && (
                        <Badge className="bg-green-100 text-green-700 text-xs">CONCLUÍDO</Badge>
                      )}
                      {reminder.ticket_number ? (
                        <Link 
                          to={`/tickets/${reminder.ticket_id}`}
                          className="flex items-center gap-1 text-purple-600 hover:text-purple-800"
                        >
                          <Ticket className="h-3 w-3" />
                          {reminder.ticket_number}
                        </Link>
                      ) : (
                        <span className="text-zinc-400 italic">Sem ticket</span>
                      )}
                      {reminder.assigned_to_name && (
                        <span>• {reminder.assigned_to_name}</span>
                      )}
                    </div>
                  </div>
                  
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteReminder(reminder.id)}
                    className="h-8 w-8 p-0 text-zinc-400 hover:text-red-600"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Reminders;
