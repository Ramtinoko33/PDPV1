import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { toast } from 'sonner';
import { 
  Search, 
  Archive,
  ChevronRight, 
  Phone, 
  Car,
  RefreshCw,
  RotateCcw,
  ArrowLeft
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ArchivedTickets = () => {
  const { getAuthHeaders } = useAuth();
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [restoring, setRestoring] = useState(null);

  const fetchArchivedTickets = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);

      const response = await axios.get(
        `${API_URL}/api/tickets/archived?${params.toString()}`,
        { headers: getAuthHeaders() }
      );
      setTickets(response.data);
    } catch (error) {
      toast.error('Erro ao carregar tickets arquivados');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArchivedTickets();
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchArchivedTickets();
  };

  const handleRestore = async (ticketId) => {
    setRestoring(ticketId);
    try {
      await axios.post(
        `${API_URL}/api/tickets/${ticketId}/restore`,
        {},
        { headers: getAuthHeaders() }
      );
      toast.success('Ticket restaurado com sucesso');
      fetchArchivedTickets();
    } catch (error) {
      toast.error('Erro ao restaurar ticket');
    } finally {
      setRestoring(null);
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

  const typeLabels = {
    ORCAMENTO_PNEUS: 'Orçamento Pneus',
    ORCAMENTO_MECANICA: 'Orçamento Mecânica',
    MARCACAO: 'Marcação',
    INFORMACAO: 'Informação',
    INTERNO: 'Interno',
    RECLAMACAO: 'Reclamação'
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

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString('pt-PT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <Link to="/tickets">
            <Button variant="ghost" className="mb-2" data-testid="back-to-tickets-btn">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Voltar aos Tickets
            </Button>
          </Link>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight flex items-center gap-3">
            <Archive className="h-8 w-8 text-zinc-500" />
            Tickets Arquivados
          </h1>
          <p className="text-zinc-500">
            {tickets.length} ticket{tickets.length !== 1 ? 's' : ''} arquivado{tickets.length !== 1 ? 's' : ''}
          </p>
        </div>
        <Button 
          variant="outline" 
          onClick={fetchArchivedTickets}
          className="border-2"
          data-testid="refresh-archived-btn"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
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
                data-testid="archived-search-input"
              />
            </div>
            <Button 
              type="submit" 
              className="h-12 px-6 font-bold bg-slate-900 hover:bg-slate-800"
              data-testid="search-archived-btn"
            >
              Pesquisar
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Archived Tickets Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : tickets.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <div className="w-16 h-16 bg-zinc-100 rounded-full flex items-center justify-center mb-4">
                <Archive className="h-8 w-8 text-zinc-400" />
              </div>
              <p className="text-lg font-medium text-zinc-600">Nenhum ticket arquivado</p>
              <p className="text-sm text-zinc-400 mt-1">Os tickets arquivados aparecerão aqui</p>
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
                    <TableHead className="font-bold">Arquivado em</TableHead>
                    <TableHead className="font-bold">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tickets.map((ticket) => (
                    <TableRow 
                      key={ticket.id} 
                      className="hover:bg-zinc-50/50"
                      data-testid={`archived-ticket-row-${ticket.id}`}
                    >
                      <TableCell>
                        <span className="font-mono text-sm font-semibold text-zinc-600">
                          {ticket.ticket_number}
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
                        <Badge className={`text-xs ${getStatusClass(ticket.status)}`}>
                          {statusLabels[ticket.status] || ticket.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-zinc-500">
                          {formatDate(ticket.archived_at)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleRestore(ticket.id)}
                            disabled={restoring === ticket.id}
                            className="border-emerald-400 text-emerald-700 hover:bg-emerald-50"
                            data-testid={`restore-ticket-${ticket.id}`}
                          >
                            {restoring === ticket.id ? (
                              <div className="w-4 h-4 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
                            ) : (
                              <>
                                <RotateCcw className="h-4 w-4 mr-1" />
                                Restaurar
                              </>
                            )}
                          </Button>
                          <Link to={`/tickets/${ticket.id}`}>
                            <Button variant="ghost" size="sm" data-testid={`view-archived-ticket-${ticket.id}`}>
                              <ChevronRight className="h-4 w-4" />
                            </Button>
                          </Link>
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
    </div>
  );
};

export default ArchivedTickets;
