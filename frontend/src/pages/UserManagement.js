import { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogClose } from '../components/ui/dialog';
import { toast } from 'sonner';
import { Plus, Pencil, Trash2, Users, Download, RefreshCw } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const UserManagement = () => {
  const { getAuthHeaders } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [exporting, setExporting] = useState(false);

  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    role: 'AGENT'
  });

  const fetchUsers = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/users`, { headers: getAuthHeaders() });
      setUsers(response.data);
    } catch (error) {
      toast.error('Erro ao carregar utilizadores');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleOpenDialog = (user = null) => {
    if (user) {
      setEditingUser(user);
      setFormData({
        name: user.name,
        email: user.email,
        password: '',
        role: user.role
      });
    } else {
      setEditingUser(null);
      setFormData({
        name: '',
        email: '',
        password: '',
        role: 'AGENT'
      });
    }
    setShowDialog(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    try {
      if (editingUser) {
        // Update
        const updateData = { name: formData.name, role: formData.role };
        if (formData.password) {
          updateData.password = formData.password;
        }
        await axios.put(
          `${API_URL}/api/users/${editingUser.id}`,
          updateData,
          { headers: getAuthHeaders() }
        );
        toast.success('Utilizador atualizado');
      } else {
        // Create
        if (!formData.password) {
          toast.error('Palavra-passe obrigatória');
          return;
        }
        await axios.post(
          `${API_URL}/api/users`,
          formData,
          { headers: getAuthHeaders() }
        );
        toast.success('Utilizador criado');
      }
      setShowDialog(false);
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao guardar utilizador');
    }
  };

  const handleDelete = async (userId) => {
    if (!window.confirm('Tem a certeza que deseja eliminar este utilizador?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/users/${userId}`, { headers: getAuthHeaders() });
      toast.success('Utilizador eliminado');
      fetchUsers();
    } catch (error) {
      toast.error('Erro ao eliminar utilizador');
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const response = await axios.get(`${API_URL}/api/export/tickets`, {
        headers: getAuthHeaders(),
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'tickets_export.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Exportação concluída');
    } catch (error) {
      toast.error('Erro ao exportar tickets');
    } finally {
      setExporting(false);
    }
  };

  const roleOptions = [
    { value: 'ADMIN', label: 'Administrador' },
    { value: 'SUPERVISOR', label: 'Supervisor (Telefonista)' },
    { value: 'AGENT', label: 'Agente (Rececionista)' },
    { value: 'FINANCEIRO', label: 'Financeiro' },
    { value: 'INTERNAL_CREATOR', label: 'Criador Interno' }
  ];

  const roleLabels = Object.fromEntries(roleOptions.map(r => [r.value, r.label]));

  const getRoleBadgeClass = (role) => {
    const classes = {
      ADMIN: 'bg-purple-100 text-purple-800',
      SUPERVISOR: 'bg-blue-100 text-blue-800',
      AGENT: 'bg-emerald-100 text-emerald-800',
      FINANCEIRO: 'bg-amber-100 text-amber-800',
      INTERNAL_CREATOR: 'bg-zinc-100 text-zinc-800'
    };
    return classes[role] || 'bg-zinc-100 text-zinc-800';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">
            Gestão de Utilizadores
          </h1>
          <p className="text-zinc-500">
            {users.length} utilizador{users.length !== 1 ? 'es' : ''}
          </p>
        </div>
        <div className="flex gap-3">
          <Button 
            variant="outline" 
            onClick={handleExport}
            disabled={exporting}
            className="border-2"
            data-testid="export-btn"
          >
            {exporting ? (
              <div className="w-4 h-4 border-2 border-zinc-500 border-t-transparent rounded-full animate-spin mr-2" />
            ) : (
              <Download className="h-4 w-4 mr-2" />
            )}
            Exportar Tickets (CSV)
          </Button>
          <Button 
            className="h-12 px-6 font-bold bg-orange-600 hover:bg-orange-700"
            onClick={() => handleOpenDialog()}
            data-testid="add-user-btn"
          >
            <Plus className="h-5 w-5 mr-2" />
            Novo Utilizador
          </Button>
        </div>
      </div>

      {/* Users Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-zinc-50/80">
                  <TableHead className="font-bold">Nome</TableHead>
                  <TableHead className="font-bold">Email</TableHead>
                  <TableHead className="font-bold">Função</TableHead>
                  <TableHead className="font-bold">Criado</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.id} className="hover:bg-zinc-50/50" data-testid={`user-row-${user.id}`}>
                    <TableCell className="font-semibold">{user.name}</TableCell>
                    <TableCell className="text-zinc-600">{user.email}</TableCell>
                    <TableCell>
                      <Badge className={`${getRoleBadgeClass(user.role)}`}>
                        {roleLabels[user.role]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-zinc-500">
                      {new Date(user.created_at).toLocaleDateString('pt-PT')}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleOpenDialog(user)}
                          data-testid={`edit-user-${user.id}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                          onClick={() => handleDelete(user.id)}
                          data-testid={`delete-user-${user.id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* User Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">
              {editingUser ? 'Editar Utilizador' : 'Novo Utilizador'}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name" className="font-semibold">Nome *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                className="h-11 border-2"
                required
                data-testid="user-name-input"
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="email" className="font-semibold">Email *</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
                className="h-11 border-2"
                required
                disabled={!!editingUser}
                data-testid="user-email-input"
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="password" className="font-semibold">
                Palavra-passe {editingUser ? '(deixe vazio para manter)' : '*'}
              </Label>
              <Input
                id="password"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))}
                className="h-11 border-2"
                required={!editingUser}
                data-testid="user-password-input"
              />
            </div>
            
            <div className="space-y-2">
              <Label className="font-semibold">Função *</Label>
              <Select 
                value={formData.role} 
                onValueChange={(value) => setFormData(prev => ({ ...prev, role: value }))}
              >
                <SelectTrigger className="h-11 border-2" data-testid="user-role-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {roleOptions.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
                data-testid="save-user-btn"
              >
                {editingUser ? 'Guardar' : 'Criar'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default UserManagement;
