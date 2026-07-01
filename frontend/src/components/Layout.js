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
  ChevronRight,
  Archive,
  Settings,
  BarChart3,
  Bell,
  ClipboardList,
  Send,
  Landmark,
  TrendingDown,
  FileSpreadsheet,
  UserCheck
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const Layout = ({ children }) => {
  const { user, logout, getAuthHeaders } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [pendingIntakeCount, setPendingIntakeCount] = useState(0);

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
      path: '/tickets', 
      label: 'Tickets', 
      icon: Ticket,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT']
    },
    { 
      path: '/tickets/new', 
      label: 'Novo Ticket', 
      icon: Plus,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT', 'INTERNAL_CREATOR']
    },
    { 
      path: '/intake', 
      label: 'Pré-Tickets', 
      icon: ClipboardList,
      roles: ['ADMIN', 'SUPERVISOR'],
      badge: 'intake'
    },
    { 
      path: '/tickets/archived', 
      label: 'Arquivados', 
      icon: Archive,
      roles: ['ADMIN', 'SUPERVISOR']
    },
    { 
      path: '/reminders', 
      label: 'Lembretes', 
      icon: Bell,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT']
    },
    { 
      path: '/customers', 
      label: 'Clientes', 
      icon: UsersRound,
      roles: ['ADMIN', 'SUPERVISOR', 'AGENT']
    },
    { 
      path: '/users', 
      label: 'Utilizadores', 
      icon: Users,
      roles: ['ADMIN']
    },
    { 
      path: '/reports', 
      label: 'Relatórios', 
      icon: BarChart3,
      roles: ['ADMIN', 'SUPERVISOR']
    },
    { 
      path: '/telegram', 
      label: 'Telegram', 
      icon: Send,
      roles: ['ADMIN']
    },
    { 
      path: '/settings', 
      label: 'Configurações', 
      icon: Settings,
      roles: ['ADMIN']
    },
  ];

  // Finance menu items - shown only if user has finance_role
  const financeNavItems = [
    {
      path: '/finance',
      label: 'CRM Finance',
      icon: Landmark,
      financeRoles: ['OWNER', 'FINANCE_REVIEWER', 'COLLECTIONS_AGENT']
    },
    {
      path: '/finance/collections',
      label: 'Cobranças Hoje',
      icon: TrendingDown,
      financeRoles: ['OWNER', 'FINANCE_REVIEWER', 'COLLECTIONS_AGENT']
    },
    {
      path: '/finance/clients',
      label: 'Clientes Fin.',
      icon: UserCheck,
      financeRoles: ['OWNER', 'FINANCE_REVIEWER', 'COLLECTIONS_AGENT']
    },
    {
      path: '/finance/imports',
      label: 'Importações',
      icon: FileSpreadsheet,
      financeRoles: ['OWNER', 'FINANCE_REVIEWER', 'COLLECTIONS_AGENT']
    },
  ];

  const filteredNavItems = navItems.filter(item => 
    item.roles.includes(user?.role)
  );

  // Filter finance items by finance_role
  const filteredFinanceItems = user?.finance_role 
    ? financeNavItems.filter(item => item.financeRoles.includes(user.finance_role))
    : [];

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
                const isActive = location.pathname === item.path;
                const badgeCount = item.badge === 'intake' ? pendingIntakeCount : 0;
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
              
              {/* Finance Section */}
              {filteredFinanceItems.length > 0 && (
                <>
                  <div className="my-4 mx-4 border-t border-slate-700" />
                  <p className="px-4 py-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    CRM Finance
                  </p>
                  {filteredFinanceItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = location.pathname === item.path || 
                      (item.path === '/finance' && location.pathname === '/finance');
                    return (
                      <Link
                        key={item.path}
                        to={item.path}
                        onClick={() => setSidebarOpen(false)}
                        data-testid={`nav-${item.path.replace(/\//g, '-').slice(1)}`}
                        className={`
                          flex items-center gap-3 px-4 py-3 rounded-lg
                          font-medium transition-all relative
                          ${isActive 
                            ? 'bg-emerald-600 text-white shadow-lg' 
                            : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                          }
                        `}
                      >
                        <Icon className="h-5 w-5" />
                        <span>{item.label}</span>
                        {isActive && <ChevronRight className="h-4 w-4 ml-auto" />}
                      </Link>
                    );
                  })}
                </>
              )}
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
