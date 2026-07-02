import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import axios from 'axios';
import { toast } from 'sonner';
import { SlidersHorizontal, Save } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const FinanceSettings = () => {
  const { user, getAuthHeaders } = useAuth();
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);

  const canEdit = user?.role === 'ADMIN' || user?.finance_role === 'OWNER';

  useEffect(() => {
    axios.get(`${API_URL}/api/finance/settings`, { headers: getAuthHeaders() })
      .then((res) => setSettings(res.data))
      .catch((err) => console.error('Erro ao carregar configurações:', err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await axios.put(`${API_URL}/api/finance/settings`, {
        residual_document_threshold: parseFloat(settings.residual_document_threshold),
        residual_client_threshold: parseFloat(settings.residual_client_threshold),
        residual_percentage_threshold: parseFloat(settings.residual_percentage_threshold),
        residual_max_documents: parseInt(settings.residual_max_documents, 10),
        show_credit_warning_on_tickets: settings.show_credit_warning_on_tickets,
      }, { headers: getAuthHeaders() });
      setSettings(res.data);
      toast.success('Configurações guardadas');
    } catch (err) {
      console.error('Erro ao guardar:', err);
      toast.error(err.response?.data?.detail || 'Erro ao guardar configurações');
    } finally {
      setSaving(false);
    }
  };

  const setField = (field, value) => setSettings((prev) => ({ ...prev, [field]: value }));

  if (!settings) return <div className="p-8 text-center text-slate-500">A carregar...</div>;

  return (
    <div className="space-y-6 max-w-3xl" data-testid="finance-settings-page">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Configurações Finance</h1>
        <p className="text-slate-500 text-sm">
          Regras de saldos residuais e avisos {!canEdit && '(apenas leitura — só o OWNER pode alterar)'}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <SlidersHorizontal className="h-5 w-5" />
            Saldos Residuais
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Máximo por documento (€)</Label>
              <Input
                type="number" step="0.01" min="0"
                value={settings.residual_document_threshold}
                onChange={(e) => setField('residual_document_threshold', e.target.value)}
                disabled={!canEdit}
                data-testid="settings-residual-doc-input"
              />
              <p className="text-xs text-slate-500">Documento com saldo até este valor é residual</p>
            </div>
            <div className="space-y-1.5">
              <Label>Máximo acumulado por cliente (€)</Label>
              <Input
                type="number" step="0.01" min="0"
                value={settings.residual_client_threshold}
                onChange={(e) => setField('residual_client_threshold', e.target.value)}
                disabled={!canEdit}
                data-testid="settings-residual-client-input"
              />
              <p className="text-xs text-slate-500">Acima disto o cliente vai para revisão interna</p>
            </div>
            <div className="space-y-1.5">
              <Label>Percentagem máxima da fatura</Label>
              <Input
                type="number" step="0.001" min="0" max="1"
                value={settings.residual_percentage_threshold}
                onChange={(e) => setField('residual_percentage_threshold', e.target.value)}
                disabled={!canEdit}
                data-testid="settings-residual-pct-input"
              />
              <p className="text-xs text-slate-500">Ex: 0.005 = 0,5% do valor original da fatura</p>
            </div>
            <div className="space-y-1.5">
              <Label>Máximo de documentos residuais por cliente</Label>
              <Input
                type="number" step="1" min="1"
                value={settings.residual_max_documents}
                onChange={(e) => setField('residual_max_documents', e.target.value)}
                disabled={!canEdit}
                data-testid="settings-residual-maxdocs-input"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Avisos nos Tickets</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border">
            <div>
              <Label className="font-semibold">Mostrar aviso genérico nos tickets</Label>
              <p className="text-xs text-slate-500 mt-0.5">
                "Cliente com validação financeira necessária antes de novo crédito" — mostrado a todos os
                utilizadores quando o cliente está bloqueado/crítico, sem revelar valores.
              </p>
            </div>
            <Switch
              checked={!!settings.show_credit_warning_on_tickets}
              onCheckedChange={(checked) => setField('show_credit_warning_on_tickets', checked)}
              disabled={!canEdit}
              data-testid="settings-credit-warning-switch"
            />
          </div>
        </CardContent>
      </Card>

      {canEdit && (
        <Button onClick={handleSave} disabled={saving} data-testid="settings-save-btn">
          <Save className="h-4 w-4 mr-2" />
          {saving ? 'A guardar...' : 'Guardar Configurações'}
        </Button>
      )}
    </div>
  );
};

export default FinanceSettings;
