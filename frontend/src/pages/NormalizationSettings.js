import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { Settings, Plus, Trash2, Save, Car, Wrench, MapPin, X } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const tierColors = {
  premium: 'bg-violet-100 text-violet-700',
  mid: 'bg-blue-100 text-blue-700',
  budget: 'bg-zinc-100 text-zinc-600',
};

const NormalizationSettings = () => {
  const { getAuthHeaders } = useAuth();
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState('default');

  // Tire brands
  const [tireBrands, setTireBrands] = useState([]);
  const [savingTires, setSavingTires] = useState(false);

  // Services
  const [services, setServices] = useState([]);
  const [savingServices, setSavingServices] = useState(false);

  // Positions (read-only)
  const [positions, setPositions] = useState(null);

  // Filter
  const [tireSearch, setTireSearch] = useState('');
  const [serviceSearch, setServiceSearch] = useState('');

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const [configRes, posRes] = await Promise.all([
        axios.get(`${API_URL}/api/normalization-config`, { headers: getAuthHeaders() }),
        axios.get(`${API_URL}/api/normalization-config/positions`, { headers: getAuthHeaders() }),
      ]);
      setTireBrands(configRes.data.tire_brands || []);
      setServices(configRes.data.services || []);
      setSource(configRes.data.source || 'default');
      setPositions(posRes.data);
    } catch (e) {
      toast.error('Erro ao carregar configuração');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  // ===== TIRE BRANDS =====
  const addTireBrand = () => {
    setTireBrands(prev => [...prev, { name: '', aliases: [''], tier: 'mid' }]);
  };

  const updateBrand = (idx, field, value) => {
    setTireBrands(prev => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], [field]: value };
      return updated;
    });
  };

  const updateBrandAlias = (brandIdx, aliasIdx, value) => {
    setTireBrands(prev => {
      const updated = [...prev];
      const aliases = [...updated[brandIdx].aliases];
      aliases[aliasIdx] = value.toLowerCase().trim();
      updated[brandIdx] = { ...updated[brandIdx], aliases };
      return updated;
    });
  };

  const addBrandAlias = (brandIdx) => {
    setTireBrands(prev => {
      const updated = [...prev];
      updated[brandIdx] = { ...updated[brandIdx], aliases: [...updated[brandIdx].aliases, ''] };
      return updated;
    });
  };

  const removeBrandAlias = (brandIdx, aliasIdx) => {
    setTireBrands(prev => {
      const updated = [...prev];
      const aliases = updated[brandIdx].aliases.filter((_, i) => i !== aliasIdx);
      updated[brandIdx] = { ...updated[brandIdx], aliases };
      return updated;
    });
  };

  const removeBrand = (idx) => {
    setTireBrands(prev => prev.filter((_, i) => i !== idx));
  };

  const saveTireBrands = async () => {
    const valid = tireBrands.filter(b => b.name.trim());
    const cleaned = valid.map(b => ({
      ...b,
      name: b.name.trim(),
      aliases: b.aliases.filter(a => a.trim()).map(a => a.toLowerCase().trim()),
    }));

    // Validate
    const names = new Set();
    const allAliases = new Set();
    for (const b of cleaned) {
      if (names.has(b.name)) { toast.error(`Marca duplicada: ${b.name}`); return; }
      names.add(b.name);
      for (const a of b.aliases) {
        if (allAliases.has(a)) { toast.error(`Alias duplicado: ${a}`); return; }
        allAliases.add(a);
      }
    }

    setSavingTires(true);
    try {
      await axios.put(`${API_URL}/api/normalization-config/tire-brands`,
        { tire_brands: cleaned }, { headers: getAuthHeaders() });
      toast.success(`${cleaned.length} marcas guardadas`);
      setSource('database');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erro ao guardar');
    } finally {
      setSavingTires(false);
    }
  };

  // ===== SERVICES =====
  const addService = () => {
    setServices(prev => [...prev, { keyword: '', display_name: '', active: true }]);
  };

  const updateService = (idx, field, value) => {
    setServices(prev => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], [field]: value };
      return updated;
    });
  };

  const removeService = (idx) => {
    setServices(prev => prev.filter((_, i) => i !== idx));
  };

  const saveServices = async () => {
    const valid = services.filter(s => s.keyword.trim() && s.display_name.trim());
    const cleaned = valid.map(s => ({
      ...s,
      keyword: s.keyword.trim().toLowerCase(),
      display_name: s.display_name.trim(),
    }));

    const keywords = new Set();
    for (const s of cleaned) {
      if (keywords.has(s.keyword)) { toast.error(`Keyword duplicado: ${s.keyword}`); return; }
      keywords.add(s.keyword);
    }

    setSavingServices(true);
    try {
      await axios.put(`${API_URL}/api/normalization-config/services`,
        { services: cleaned }, { headers: getAuthHeaders() });
      toast.success(`${cleaned.length} serviços guardados`);
      setSource('database');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erro ao guardar');
    } finally {
      setSavingServices(false);
    }
  };

  // ===== FILTER =====
  const filteredBrands = tireBrands.filter(b =>
    !tireSearch || b.name.toLowerCase().includes(tireSearch.toLowerCase()) ||
    b.aliases.some(a => a.includes(tireSearch.toLowerCase()))
  );

  const filteredServices = services.filter(s =>
    !serviceSearch || s.keyword.includes(serviceSearch.toLowerCase()) ||
    s.display_name.toLowerCase().includes(serviceSearch.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-4 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="normalization-settings-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Normalização</h1>
          <p className="text-zinc-500">Configuração de nomes e marcas para orçamentos</p>
        </div>
        <Badge className={source === 'database' ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 text-zinc-600'}>
          {source === 'database' ? 'Configuração personalizada' : 'Configuração padrão'}
        </Badge>
      </div>

      {/* A) TIRE BRANDS */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Car className="h-5 w-5 text-orange-600" />
              Marcas de Pneus
              <Badge variant="secondary" className="ml-1">{tireBrands.length}</Badge>
            </CardTitle>
            <div className="flex gap-2">
              <Input
                placeholder="Filtrar marcas..."
                value={tireSearch}
                onChange={e => setTireSearch(e.target.value)}
                className="h-9 w-48 border-2 text-sm"
                data-testid="tire-search"
              />
              <Button variant="outline" size="sm" className="border-2" onClick={addTireBrand} data-testid="add-tire-brand-btn">
                <Plus className="h-4 w-4 mr-1" /> Adicionar
              </Button>
              <Button size="sm" onClick={saveTireBrands} disabled={savingTires}
                className="bg-orange-600 hover:bg-orange-700" data-testid="save-tire-brands-btn">
                <Save className="h-4 w-4 mr-1" />
                {savingTires ? 'A guardar...' : 'Guardar'}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
            {filteredBrands.map((brand, idx) => {
              const realIdx = tireBrands.indexOf(brand);
              return (
                <div key={realIdx} className="flex gap-3 items-start p-3 bg-zinc-50/80 rounded-lg border" data-testid={`tire-brand-row-${realIdx}`}>
                  <div className="flex-1 space-y-2">
                    <div className="flex gap-2 items-center">
                      <Input
                        value={brand.name}
                        onChange={e => updateBrand(realIdx, 'name', e.target.value)}
                        placeholder="Nome da marca"
                        className="h-9 border-2 font-medium flex-1"
                        data-testid={`tire-brand-name-${realIdx}`}
                      />
                      <Select value={brand.tier} onValueChange={v => updateBrand(realIdx, 'tier', v)}>
                        <SelectTrigger className="h-9 w-32 border-2" data-testid={`tire-brand-tier-${realIdx}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="premium">Premium</SelectItem>
                          <SelectItem value="mid">Mid</SelectItem>
                          <SelectItem value="budget">Budget</SelectItem>
                        </SelectContent>
                      </Select>
                      <Badge className={tierColors[brand.tier] || tierColors.mid}>
                        {brand.tier}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap gap-1.5 items-center">
                      <span className="text-[11px] text-zinc-400 font-medium">Aliases:</span>
                      {brand.aliases.map((alias, aIdx) => (
                        // eslint-disable-next-line react/no-array-index-key -- controlled input, alias values may be empty/duplicate
                        <div key={aIdx} className="flex items-center gap-0.5">
                          <Input
                            value={alias}
                            onChange={e => updateBrandAlias(realIdx, aIdx, e.target.value)}
                            placeholder="alias"
                            className="h-7 w-28 border text-xs font-mono"
                          />
                          {brand.aliases.length > 1 && (
                            <button onClick={() => removeBrandAlias(realIdx, aIdx)}
                              className="text-zinc-400 hover:text-red-500 p-0.5">
                              <X className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      ))}
                      <button onClick={() => addBrandAlias(realIdx)}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                        + alias
                      </button>
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" className="text-zinc-400 hover:text-red-600 mt-1"
                    onClick={() => removeBrand(realIdx)} data-testid={`remove-tire-brand-${realIdx}`}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              );
            })}
            {filteredBrands.length === 0 && (
              <p className="text-center text-zinc-400 py-8">
                {tireSearch ? 'Nenhuma marca encontrada' : 'Nenhuma marca configurada'}
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* B) SERVICES */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Wrench className="h-5 w-5 text-orange-600" />
              Serviços
              <Badge variant="secondary" className="ml-1">{services.length}</Badge>
            </CardTitle>
            <div className="flex gap-2">
              <Input
                placeholder="Filtrar serviços..."
                value={serviceSearch}
                onChange={e => setServiceSearch(e.target.value)}
                className="h-9 w-48 border-2 text-sm"
                data-testid="service-search"
              />
              <Button variant="outline" size="sm" className="border-2" onClick={addService} data-testid="add-service-btn">
                <Plus className="h-4 w-4 mr-1" /> Adicionar
              </Button>
              <Button size="sm" onClick={saveServices} disabled={savingServices}
                className="bg-orange-600 hover:bg-orange-700" data-testid="save-services-btn">
                <Save className="h-4 w-4 mr-1" />
                {savingServices ? 'A guardar...' : 'Guardar'}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
            {filteredServices.map((svc, idx) => {
              const realIdx = services.indexOf(svc);
              return (
                <div key={realIdx} className="flex gap-3 items-center p-2.5 bg-zinc-50/80 rounded-lg border" data-testid={`service-row-${realIdx}`}>
                  <Input
                    value={svc.keyword}
                    onChange={e => updateService(realIdx, 'keyword', e.target.value)}
                    placeholder="keyword (ex: calços)"
                    className="h-9 border-2 font-mono text-sm flex-1"
                    data-testid={`service-keyword-${realIdx}`}
                  />
                  <span className="text-zinc-300">→</span>
                  <Input
                    value={svc.display_name}
                    onChange={e => updateService(realIdx, 'display_name', e.target.value)}
                    placeholder="Nome exibido (ex: Pastilhas de travão)"
                    className="h-9 border-2 text-sm flex-1"
                    data-testid={`service-display-${realIdx}`}
                  />
                  <Switch
                    checked={svc.active !== false}
                    onCheckedChange={v => updateService(realIdx, 'active', v)}
                    data-testid={`service-active-${realIdx}`}
                  />
                  <Button variant="ghost" size="sm" className="text-zinc-400 hover:text-red-600"
                    onClick={() => removeService(realIdx)} data-testid={`remove-service-${realIdx}`}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              );
            })}
            {filteredServices.length === 0 && (
              <p className="text-center text-zinc-400 py-8">
                {serviceSearch ? 'Nenhum serviço encontrado' : 'Nenhum serviço configurado'}
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* C) POSITIONS (READ-ONLY) */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <MapPin className="h-5 w-5 text-orange-600" />
            Tokens de Posição
            <Badge variant="secondary" className="ml-1">Apenas leitura</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {positions && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-2">
                <Label className="font-semibold text-sm text-zinc-600">Eixo — Frente</Label>
                <div className="flex flex-wrap gap-1">
                  {(positions.axis?.front || []).map(t => (
                    <Badge key={t} variant="secondary" className="font-mono text-xs">{t}</Badge>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <Label className="font-semibold text-sm text-zinc-600">Eixo — Traseira</Label>
                <div className="flex flex-wrap gap-1">
                  {(positions.axis?.rear || []).map(t => (
                    <Badge key={t} variant="secondary" className="font-mono text-xs">{t}</Badge>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <Label className="font-semibold text-sm text-zinc-600">Lado — Esquerda</Label>
                <div className="flex flex-wrap gap-1">
                  {(positions.side?.left || []).map(t => (
                    <Badge key={t} variant="secondary" className="font-mono text-xs">{t}</Badge>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <Label className="font-semibold text-sm text-zinc-600">Lado — Direita</Label>
                <div className="flex flex-wrap gap-1">
                  {(positions.side?.right || []).map(t => (
                    <Badge key={t} variant="secondary" className="font-mono text-xs">{t}</Badge>
                  ))}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default NormalizationSettings;
