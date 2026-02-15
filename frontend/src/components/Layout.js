import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { ScrollArea } from './ui/scroll-area';
import NotificationCenter from './NotificationCenter';
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
  Settings
} from 'lucide-react';

const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Auto-refresh page every 5 minutes
  useEffect(() => {
    const refreshInterval = setInterval(() => {
      window.location.reload();
    }, 5 * 60 * 1000); // 5 minutes in milliseconds

    return () => clearInterval(refreshInterval);
  }, []);

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
      path: '/tickets/archived', 
      label: 'Arquivados', 
      icon: Archive,
      roles: ['ADMIN', 'SUPERVISOR']
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
      path: '/settings', 
      label: 'Configurações', 
      icon: Settings,
      roles: ['ADMIN']
    },
  ];

  const filteredNavItems = navItems.filter(item => 
    item.roles.includes(user?.role)
  );

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
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={() => setSidebarOpen(false)}
                    data-testid={`nav-${item.path.replace(/\//g, '-').slice(1) || 'dashboard'}`}
                    className={`
                      flex items-center gap-3 px-4 py-3 rounded-lg
                      font-medium transition-all
                      ${isActive 
                        ? 'bg-orange-600 text-white shadow-lg' 
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
