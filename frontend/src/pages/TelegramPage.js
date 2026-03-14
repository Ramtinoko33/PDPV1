import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { 
  Send, 
  RefreshCw, 
  CheckCircle2, 
  XCircle, 
  Link as LinkIcon,
  Settings,
  Bot,
  Webhook
} from 'lucide-react';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TelegramPage = () => {
  const { getAuthHeaders } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [settingWebhook, setSettingWebhook] = useState(false);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_URL}/api/telegram/status`, {
        headers: getAuthHeaders()
      });
      setStatus(response.data);
    } catch (error) {
      console.error('Error fetching Telegram status:', error);
      toast.error('Erro ao carregar estado do Telegram');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleSetupWebhook = async () => {
    setSettingWebhook(true);
    try {
      const response = await axios.post(`${API_URL}/api/telegram/setup-webhook`, {}, {
        headers: getAuthHeaders()
      });
      toast.success(response.data.message || 'Webhook configurado com sucesso');
      fetchStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao configurar webhook');
    } finally {
      setSettingWebhook(false);
    }
  };

  const handleDeleteWebhook = async () => {
    if (!window.confirm('Tem certeza que deseja remover o webhook?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/telegram/webhook`, {
        headers: getAuthHeaders()
      });
      toast.success('Webhook removido');
      fetchStatus();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao remover webhook');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-zinc-800 flex items-center gap-2">
            <Send className="h-7 w-7 text-blue-500" />
            Telegram Bot
          </h1>
          <p className="text-zinc-500 text-sm mt-1">
            Configuração e estado do bot Telegram
          </p>
        </div>
        <Button onClick={fetchStatus} variant="outline" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </Button>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Bot Token</p>
                <p className="text-lg font-semibold mt-1">
                  {status?.bot_configured ? 'Configurado' : 'Não configurado'}
                </p>
              </div>
              {status?.bot_configured ? (
                <CheckCircle2 className="h-10 w-10 text-green-500" />
              ) : (
                <XCircle className="h-10 w-10 text-red-500" />
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Gemini AI</p>
                <p className="text-lg font-semibold mt-1">
                  {status?.gemini_configured ? 'Configurado' : 'Não configurado'}
                </p>
              </div>
              {status?.gemini_configured ? (
                <CheckCircle2 className="h-10 w-10 text-green-500" />
              ) : (
                <XCircle className="h-10 w-10 text-amber-500" />
              )}
            </div>
            {!status?.gemini_configured && (
              <p className="text-xs text-zinc-400 mt-2">
                Sem Gemini, o bot usa extração por regex
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-500">Webhook</p>
                <p className="text-lg font-semibold mt-1">
                  {status?.webhook?.url ? 'Ativo' : 'Não configurado'}
                </p>
              </div>
              {status?.webhook?.url ? (
                <CheckCircle2 className="h-10 w-10 text-green-500" />
              ) : (
                <XCircle className="h-10 w-10 text-red-500" />
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Webhook Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Webhook className="h-5 w-5 text-zinc-500" />
            Configuração do Webhook
          </CardTitle>
          <CardDescription>
            O webhook é necessário para receber mensagens do Telegram
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {status?.webhook?.url ? (
            <div className="space-y-4">
              <div className="p-4 bg-zinc-50 rounded-lg">
                <Label className="text-xs text-zinc-500">URL do Webhook</Label>
                <p className="font-mono text-sm mt-1 break-all">
                  {status.webhook.url}
                </p>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-zinc-50 rounded-lg">
                  <Label className="text-xs text-zinc-500">Atualizações pendentes</Label>
                  <p className="font-semibold mt-1">
                    {status.webhook.pending_update_count || 0}
                  </p>
                </div>
                <div className="p-3 bg-zinc-50 rounded-lg">
                  <Label className="text-xs text-zinc-500">IP</Label>
                  <p className="font-mono text-sm mt-1">
                    {status.webhook.ip_address || '-'}
                  </p>
                </div>
              </div>

              <div className="flex gap-2">
                <Button onClick={handleSetupWebhook} disabled={settingWebhook}>
                  {settingWebhook ? <RefreshCw className="h-4 w-4 animate-spin mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                  Reconfigurar
                </Button>
                <Button onClick={handleDeleteWebhook} variant="destructive">
                  Remover Webhook
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                <p className="text-amber-800">
                  O webhook não está configurado. Configure-o para começar a receber mensagens.
                </p>
              </div>
              <Button onClick={handleSetupWebhook} disabled={settingWebhook} className="gap-2">
                {settingWebhook ? <RefreshCw className="h-4 w-4 animate-spin" /> : <LinkIcon className="h-4 w-4" />}
                Configurar Webhook Automaticamente
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* How it works */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-zinc-500" />
            Como funciona
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="list-decimal list-inside space-y-2 text-sm text-zinc-600">
            <li>O cliente envia uma mensagem para o bot no Telegram</li>
            <li>O bot analisa a mensagem e extrai informações (matrícula, medida de pneu, etc.)</li>
            <li>Se encontrar a matrícula na base de dados, associa ao cliente existente</li>
            <li>Cria automaticamente um pré-ticket no sistema</li>
            <li>Envia confirmação ao cliente com o número de referência</li>
            <li>A equipa pode ver e converter os pré-tickets em "Pré-Tickets" no menu</li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
};

export default TelegramPage;
