/**
 * Card de contactos financeiros dedicados + segmento comercial.
 * Editável por qualquer utilizador com finance_role (COLLECTIONS_AGENT+).
 * Alerta visualmente se `finance_email` estiver em falta.
 */
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';
import axios from 'axios';
import { Mail, Phone, User, Tag, Pencil, Save, X, AlertTriangle } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const SEGMENTS = ['PARTICULAR', 'EMPRESA', 'FROTA', 'SEGURADORA', 'LEASING', 'CONTA_CORRENTE', 'OUTRO', 'UNKNOWN'];

const SEGMENT_STYLES = {
  PARTICULAR:      'bg-slate-100 text-slate-700',
  EMPRESA:         'bg-blue-100 text-blue-800',
  FROTA:           'bg-orange-100 text-orange-800',
  SEGURADORA:      'bg-teal-100 text-teal-800',
  LEASING:         'bg-purple-100 text-purple-800',
  CONTA_CORRENTE:  'bg-indigo-100 text-indigo-800',
  OUTRO:           'bg-amber-100 text-amber-800',
  UNKNOWN:         'bg-slate-200 text-slate-500',
};

export default function FinanceContactsCard({ client, getAuthHeaders, onUpdated }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    finance_email: client?.finance_email || '',
    finance_phone: client?.finance_phone || '',
    finance_mobile: client?.finance_mobile || '',
    finance_contact_name: client?.finance_contact_name || '',
    customer_segment: client?.customer_segment || 'UNKNOWN',
    reason: '',
  });

  const missingEmail = !client?.finance_email;

  const startEdit = () => {
    setForm({
      finance_email: client?.finance_email || '',
      finance_phone: client?.finance_phone || '',
      finance_mobile: client?.finance_mobile || '',
      finance_contact_name: client?.finance_contact_name || '',
      customer_segment: client?.customer_segment || 'UNKNOWN',
      reason: '',
    });
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await axios.patch(
        `${API_URL}/api/finance/clients/${client.id}/contacts`,
        form,
        { headers: getAuthHeaders() }
      );
      toast.success('Contactos atualizados');
      setEditing(false);
      onUpdated && onUpdated();
    } catch (err) {
      console.error('Erro a guardar:', err);
      toast.error(err?.response?.data?.detail || 'Erro ao guardar');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card data-testid="finance-contacts-card">
      <CardHeader className="pb-3 flex-row items-center justify-between">
        <CardTitle className="text-lg flex items-center gap-2">
          <User className="h-4 w-4" /> Contactos financeiros
        </CardTitle>
        {!editing && (
          <Button variant="outline" size="sm" onClick={startEdit} data-testid="finance-contacts-edit-btn">
            <Pencil className="h-4 w-4 mr-1" /> Editar
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {editing ? (
          <>
            <div className="space-y-1">
              <Label className="text-xs">Segmento</Label>
              <Select
                value={form.customer_segment}
                onValueChange={(v) => setForm({ ...form, customer_segment: v })}
              >
                <SelectTrigger data-testid="finance-contacts-segment-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SEGMENTS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Email financeiro</Label>
              <Input
                type="email"
                value={form.finance_email}
                onChange={(e) => setForm({ ...form, finance_email: e.target.value })}
                placeholder="contabilidade@cliente.pt"
                data-testid="finance-contacts-email-input"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Telefone</Label>
                <Input
                  value={form.finance_phone}
                  onChange={(e) => setForm({ ...form, finance_phone: e.target.value })}
                  data-testid="finance-contacts-phone-input"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Telemóvel</Label>
                <Input
                  value={form.finance_mobile}
                  onChange={(e) => setForm({ ...form, finance_mobile: e.target.value })}
                  data-testid="finance-contacts-mobile-input"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Nome contacto (D. Ana / Dr. João)</Label>
              <Input
                value={form.finance_contact_name}
                onChange={(e) => setForm({ ...form, finance_contact_name: e.target.value })}
                data-testid="finance-contacts-name-input"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Motivo da alteração (opcional)</Label>
              <Textarea
                rows={2}
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                placeholder="Ex: Confirmado por telefone com D. Ana"
                data-testid="finance-contacts-reason-input"
              />
            </div>
            <div className="flex gap-2 pt-2">
              <Button variant="outline" onClick={() => setEditing(false)} size="sm">
                <X className="h-4 w-4 mr-1" /> Cancelar
              </Button>
              <Button onClick={save} disabled={saving} size="sm" data-testid="finance-contacts-save-btn">
                <Save className="h-4 w-4 mr-1" /> {saving ? 'A guardar…' : 'Guardar'}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <Tag className="h-4 w-4 text-slate-400" />
              <Badge className={SEGMENT_STYLES[client?.customer_segment] || SEGMENT_STYLES.UNKNOWN}>
                {client?.customer_segment || 'UNKNOWN'}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-slate-400" />
              {missingEmail ? (
                <span className="flex items-center gap-1 text-amber-700">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  <span data-testid="finance-contacts-email-missing">Email financeiro em falta</span>
                </span>
              ) : (
                <span data-testid="finance-contacts-email-value">{client.finance_email}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Phone className="h-4 w-4 text-slate-400" />
              <span>{client?.finance_mobile || client?.finance_phone || '—'}</span>
            </div>
            {client?.finance_contact_name && (
              <div className="flex items-center gap-2">
                <User className="h-4 w-4 text-slate-400" />
                <span>{client.finance_contact_name}</span>
              </div>
            )}
            {client?.finance_contacts_updated_at && (
              <div className="text-xs text-slate-400 pt-2 border-t">
                Última atualização: {new Date(client.finance_contacts_updated_at).toLocaleDateString('pt-PT')}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
