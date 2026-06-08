import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { ScrollArea } from './ui/scroll-area';
import NotificationCenter from './NotificationCenter';
import axios from 'axios';
import { 
  LayoutDashboard, 
  Ticket, 
  Plus, 
  Users, 
  UsersRound,
  LogOut, 
  Menu, 
  X,
  Wrench,
  Truck,
  ChevronRight,
  ChevronDown,
  Archive,
  Settings,
  BarChart3,
  Bell,
  ClipboardList,
  Send,
  Zap,
  Car
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const Layout = ({ children }) => {
  const { user, logout, getAuthHeaders } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState({});
  const [pendingIntakeCount, setPendingIntakeCount] = useState(0);
  const [pendingAlertsCount, setPendingAlertsCount] = useState(0);
  const [pendingRentingCount, setPendingRentingCount] = useState(0);
  const [pendingAssistenciasCount, setPendingAssistenciasCount] = useState(0);

  // Fetch pending intake count for badge
  useEffect(() => {
    const fetchPendingCount = async () => {
      if (!user || !['ADMIN', 'SUPERVISOR'].includes(user.role)) return;
      
      try {
        const response = await axios.get(`${API_URL}/api/intake/pending-count`, {
          headers: getAuthHeaders()
        });
        setPendingIntakeCount(response.data.count || 0);
      } catch (error) {
        console.error('Error fetching pending intake count:', error);
      }
    };

    fetchPendingCount();
    // Refresh count every 30 seconds
    const interval = setInterval(fetchPendingCount, 30000);
    return () => clearInterval(interval);
  }, [user, getAuthHeaders]);

  // Fetch pending alerts count for badge
  useEffect(() => {
    const fetchAlertsCount = async () => {
      if (!user) return;
      const hasAccess = ['ADMIN', 'SUPERVISOR'].includes(user.role) || user.has_alerts_access;
      if (!hasAccess) return;

      try {
        const response = await axios.get(`${API_URL}/api/telegram-alerts/alerts-count`, {
          headers: getAuthHeaders()
        });
        setPendingAlertsCount(response.data.count || 0);
      } catch (error) {
        // Module might be disabled - silent
      }
    };

    fetchAlertsCount();
    const interval = setInterval(fetchAlertsCount, 30000);
    return () => clearInterval(interval);
  }, [user, getAuthHeaders]);

  // Fetch pending Renting count for badge
  useEffect(() => {
    const fetchRentingCount = async () => {
      if (!user) return;
      const hasAccess = ['ADMIN', 'SUPERVISOR'].includes(user.role) || user.has_renting_access;
      if (!hasAccess) return;
      try {
        const response = await axios.get(`${API_URL}/api/renting/pending-count`, {
          headers: getAuthHeaders()
        });
        setPendingRentingCount(response.data.count || 0);
      } catch (error) {
        // Module might be disabled - silent
      }
    };

    fetchRentingCount();
    const interval = setInterval(fetchRentingCount, 30000);
    return () => clearInterval(interval);
  }, [user, getAuthHeaders]);

  // Fetch pending Assistências count for badge
  useEffect(() => {
    const fetchAssistenciasCount = async () => {
      if (!user) return;
      const hasAccess = ['ADMIN', 'SUPERVISOR'].includes(user.role) || user.has_assistencias_access;
      if (!hasAccess) return;
      try {
        const response = await axios.get(`${API_URL}/api/assistencias/pending-count`, {
          headers: getAuthHeaders()
        });
        setPendingAssistenciasCount(response.data.count || 0);
      } catch (error) {
        // Module might be disabled - silent
      }
    };
    fetchAssistenciasCount();
    const interval = setInterval(fetchAssistenciasCount, 30000);
    return () => clearInterval(interval);
  }, [user, getAuthHeaders]);

  // Note: Removed auto-refresh that was causing data loss when typing
  // Notifications are now handled via NotificationContext polling

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    {
      path: '/dashboard',
      label: 'Painel',
      icon: LayoutDashboard,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT', 'INTERNAL_CREATOR']
    },
    {
      label: 'Tickets',
      icon: Ticket,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT', 'INTERNAL_CREATOR'],
      badge: 'intake',
      children: [
        { path: '/tickets', label: 'Lista', icon: Ticket, roles: ['ADMIN', 'SUPERVISOR', 'AGENT'] },
        { path: '/tickets/new', label: 'Criar Novo', icon: Plus, roles: ['ADMIN', 'SUPERVISOR', 'AGENT', 'INTERNAL_CREATOR'] },
        { path: '/intake', label: 'Pré-Tickets', icon: ClipboardList, roles: ['ADMIN', 'SUPERVISOR'], badge: 'intake' },
        { path: '/tickets/archived', label: 'Arquivados', icon: Archive, roles: ['ADMIN', 'SUPERVISOR'] },
      ]
    },
    {
      path: '/alertas',
      label: 'Alertas',
      icon: Zap,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT'],
      badge: 'alerts',
      requireAlertsAccess: true
    },
    {
      path: '/renting',
      label: 'Renting',
      icon: Car,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT'],
      badge: 'renting',
      requireRentingAccess: true
    },
    {
      label: 'Assistências',
      icon: Truck,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT'],
      requireAssistenciasAccess: true,
      badge: 'assistencias',
      children: [
        { path: '/assistencias', label: 'Lista', icon: Truck, roles: ['ADMIN', 'SUPERVISOR', 'AGENT'] },
        { path: '/admin/assistencias-users', label: 'Bot & Utilizadores', icon: Users, roles: ['ADMIN'] },
      ]
    },
    {
      path: '/customers',
      label: 'Clientes',
      icon: UsersRound,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT']
    },
    {
      path: '/reminders',
      label: 'Lembretes',
      icon: Bell,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT']
    },
    {
      path: '/reports',
      label: 'Relatórios',
      icon: BarChart3,
      roles: ['ADMIN', 'SUPERVISOR']
    },
    {
      label: 'Administração',
      icon: Settings,
      roles: ['ADMIN', 'SUPERVISOR'],
      children: [
        { path: '/users', label: 'Utilizadores', icon: Users, roles: ['ADMIN'] },
        { path: '/settings', label: 'Configurações Gerais', icon: Settings, roles: ['ADMIN'] },
        { path: '/settings/normalization', label: 'Normalização', icon: Wrench, roles: ['ADMIN', 'SUPERVISOR'] },
        { path: '/telegram', label: 'Telegram (Bot Principal)', icon: Send, roles: ['ADMIN'] },
        { path: '/admin/telegram-users', label: 'Telegram (Utilizadores)', icon: Users, roles: ['ADMIN'] },
      ]
    },
  ];

  const filteredNavItems = navItems.filter(item => {
    if (!item.roles.includes(user?.role)) return false;
    // For alerts: ADMIN/SUPERVISOR always see it, AGENT only if has_alerts_access
    if (item.requireAlertsAccess && user?.role === 'AGENT' && !user?.has_alerts_access) return false;
    // For renting: ADMIN/SUPERVISOR always see it, AGENT only if has_renting_access
    if (item.requireRentingAccess && user?.role === 'AGENT' && !user?.has_renting_access) return false;
    if (item.requireAssistenciasAccess && user?.role === 'AGENT' && !user?.has_assistencias_access) return false;
    return true;
  }).map(item => {
    // Filter children by role too
    if (item.children) {
      return { ...item, children: item.children.filter(c => c.roles.includes(user?.role)) };
    }
    return item;
  });

  // Auto-expand groups whose child is currently active
  useEffect(() => {
    filteredNavItems.forEach(item => {
      if (item.children && item.children.some(c => c.path === location.pathname)) {
        setExpandedGroups(prev => prev[item.label] ? prev : { ...prev, [item.label]: true });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, user?.role]);

  const toggleGroup = (label) => {
    setExpandedGroups(prev => ({ ...prev, [label]: !prev[label] }));
  };

  const roleLabels = {
    ADMIN: 'Administrador',
    SUPERVISOR: 'Telefonista',
    AGENT: 'Rececionista',
    INTERNAL_CREATOR: 'Criador Interno'
  };

  return (
    <div className="min-h-screen bg-zinc-50 flex">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-50
        w-72 bg-slate-900 text-white
        transform transition-transform duration-300 ease-in-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="h-16 flex items-center justify-between px-6 border-b border-slate-800">
            <div className="flex items-center">
              <Wrench className="h-8 w-8 text-orange-500 mr-3" />
              <span className="text-xl font-black tracking-tight font-['Chivo']">PDPV Tickets</span>
            </div>
            <div className="flex items-center gap-2">
              <NotificationCenter />
              <button 
                className="lg:hidden p-1 hover:bg-slate-800 rounded"
                onClick={() => setSidebarOpen(false)}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Navigation */}
          <ScrollArea className="flex-1 py-4">
            <nav className="px-3 space-y-1">
              {filteredNavItems.map((item) => {
                const Icon = item.icon;

                // Group with children (collapsible)
                if (item.children) {
                  const isOpen = !!expandedGroups[item.label];
                  const hasActiveChild = item.children.some(c => c.path === location.pathname);
                  const groupBadge =
                    item.badge === 'assistencias' ? pendingAssistenciasCount :
                    item.badge === 'intake' ? pendingIntakeCount :
                    0;
                  return (
                    <div key={item.label}>
                      <button
                        type="button"
                        onClick={() => toggleGroup(item.label)}
                        data-testid={`nav-group-${item.label.toLowerCase()}`}
                        className={`
                          w-full flex items-center gap-3 px-4 py-3 rounded-lg
                          font-medium transition-all
                          ${hasActiveChild
                            ? 'bg-slate-800 text-white'
                            : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                          }
                        `}
                      >
                        <Icon className="h-5 w-5" />
                        <span>{item.label}</span>
                        {groupBadge > 0 && (
                          <span className="ml-auto bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
                            {groupBadge > 99 ? '99+' : groupBadge}
                          </span>
                        )}
                        {groupBadge > 0
                          ? null
                          : (isOpen
                              ? <ChevronDown className="h-4 w-4 ml-auto" />
                              : <ChevronRight className="h-4 w-4 ml-auto" />)
                        }
                      </button>
                      {isOpen && (
                        <div className="mt-1 ml-3 pl-3 border-l border-slate-700 space-y-1">
                          {item.children.map(child => {
                            const ChildIcon = child.icon;
                            const childActive = location.pathname === child.path;
                            return (
                              <Link
                                key={child.path}
                                to={child.path}
                                onClick={() => setSidebarOpen(false)}
                                data-testid={`nav-${child.path.replace(/\//g, '-').slice(1)}`}
                                className={`
                                  flex items-center gap-3 px-3 py-2 rounded-lg text-sm
                                  font-medium transition-all
                                  ${childActive
                                    ? 'bg-orange-600 text-white shadow'
                                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                                  }
                                `}
                              >
                                <ChildIcon className="h-4 w-4" />
                                <span>{child.label}</span>
                              </Link>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                }

                // Regular link item
                const isActive = location.pathname === item.path;
                const badgeCount = item.badge === 'intake' ? pendingIntakeCount : item.badge === 'alerts' ? pendingAlertsCount : item.badge === 'renting' ? pendingRentingCount : 0;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={() => setSidebarOpen(false)}
                    data-testid={`nav-${item.path.replace(/\//g, '-').slice(1) || 'dashboard'}`}
                    className={`
                      flex items-center gap-3 px-4 py-3 rounded-lg
                      font-medium transition-all relative
                      ${isActive 
                        ? 'bg-orange-600 text-white shadow-lg' 
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                      }
                    `}
                  >
                    <Icon className="h-5 w-5" />
                    <span>{item.label}</span>
                    {badgeCount > 0 && (
                      <span className="ml-auto bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
                        {badgeCount > 99 ? '99+' : badgeCount}
                      </span>
                    )}
                    {isActive && !badgeCount && <ChevronRight className="h-4 w-4 ml-auto" />}
                  </Link>
                );
              })}
            </nav>
          </ScrollArea>

          {/* User info */}
          <div className="p-4 border-t border-slate-800">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center">
                <span className="text-sm font-bold">
                  {user?.name?.charAt(0)?.toUpperCase() || 'U'}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate">{user?.name}</p>
                <p className="text-xs text-slate-400">{roleLabels[user?.role]}</p>
              </div>
            </div>
            <Button 
              variant="outline" 
              className="w-full border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white"
              onClick={handleLogout}
              data-testid="logout-btn"
            >
              <LogOut className="h-4 w-4 mr-2" />
              Sair
            </Button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-screen">
        {/* Mobile header */}
        <header className="lg:hidden h-16 bg-white border-b flex items-center px-4 sticky top-0 z-30">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="p-2 hover:bg-zinc-100 rounded-lg"
            data-testid="mobile-menu-btn"
          >
            <Menu className="h-6 w-6" />
          </button>
          <div className="flex items-center ml-3">
            <Wrench className="h-6 w-6 text-orange-600 mr-2" />
            <span className="font-bold text-lg">PDPV</span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-4 md:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;
