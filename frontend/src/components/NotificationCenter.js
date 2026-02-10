import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNotifications } from '../context/NotificationContext';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { 
  Bell, 
  BellRing, 
  Check, 
  CheckCheck, 
  Ticket, 
  X,
  Settings
} from 'lucide-react';

const NotificationCenter = () => {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);
  const {
    notifications,
    unreadCount,
    webPushEnabled,
    markAsRead,
    markAllAsRead,
    requestWebPushPermission
  } = useNotifications();

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNotificationClick = (notification) => {
    if (!notification.read) {
      markAsRead(notification.id);
    }
    if (notification.ticket_id) {
      navigate(`/tickets/${notification.ticket_id}`);
      setIsOpen(false);
    }
  };

  const formatTime = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Agora';
    if (diffMins < 60) return `${diffMins}m`;
    if (diffHours < 24) return `${diffHours}h`;
    if (diffDays < 7) return `${diffDays}d`;
    return date.toLocaleDateString('pt-PT');
  };

  const getTypeIcon = (type) => {
    switch (type) {
      case 'warning':
        return <div className="w-2 h-2 rounded-full bg-amber-500" />;
      case 'error':
        return <div className="w-2 h-2 rounded-full bg-red-500" />;
      case 'success':
        return <div className="w-2 h-2 rounded-full bg-emerald-500" />;
      default:
        return <div className="w-2 h-2 rounded-full bg-blue-500" />;
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Bell Button */}
      <Button
        variant="ghost"
        size="sm"
        className="relative p-2 hover:bg-slate-800"
        onClick={() => setIsOpen(!isOpen)}
        data-testid="notification-bell"
      >
        {unreadCount > 0 ? (
          <BellRing className="h-5 w-5 text-slate-300" />
        ) : (
          <Bell className="h-5 w-5 text-slate-300" />
        )}
        {unreadCount > 0 && (
          <Badge className="absolute -top-1 -right-1 h-5 min-w-5 flex items-center justify-center bg-red-500 text-white text-xs p-0 rounded-full">
            {unreadCount > 99 ? '99+' : unreadCount}
          </Badge>
        )}
      </Button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute left-0 lg:left-auto lg:right-0 mt-2 w-80 md:w-96 bg-white rounded-xl shadow-2xl border border-zinc-200 z-50 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b bg-zinc-50">
            <h3 className="font-bold text-slate-900">Notificações</h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-zinc-500 hover:text-zinc-700"
                  onClick={markAllAsRead}
                  data-testid="mark-all-read"
                >
                  <CheckCheck className="h-4 w-4 mr-1" />
                  Marcar todas
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="p-1"
                onClick={() => setIsOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Web Push Permission Banner */}
          {!webPushEnabled && 'Notification' in window && Notification.permission !== 'denied' && (
            <div className="p-3 bg-orange-50 border-b border-orange-100">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Settings className="h-4 w-4 text-orange-600" />
                  <span className="text-sm text-orange-800">Ativar notificações do browser?</span>
                </div>
                <Button
                  size="sm"
                  className="h-7 text-xs bg-orange-600 hover:bg-orange-700"
                  onClick={requestWebPushPermission}
                  data-testid="enable-push"
                >
                  Ativar
                </Button>
              </div>
            </div>
          )}

          {/* Notifications List */}
          <ScrollArea className="max-h-96">
            {notifications.length === 0 ? (
              <div className="p-8 text-center text-zinc-500">
                <Bell className="h-12 w-12 mx-auto mb-3 text-zinc-300" />
                <p>Sem notificações</p>
              </div>
            ) : (
              <div className="divide-y">
                {notifications.map((notification) => (
                  <div
                    key={notification.id}
                    className={`p-4 cursor-pointer transition-colors hover:bg-zinc-50 ${
                      !notification.read ? 'bg-blue-50/50' : ''
                    }`}
                    onClick={() => handleNotificationClick(notification)}
                    data-testid={`notification-${notification.id}`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-1.5">
                        {getTypeIcon(notification.type)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <p className={`text-sm font-semibold truncate ${
                            !notification.read ? 'text-slate-900' : 'text-zinc-600'
                          }`}>
                            {notification.title}
                          </p>
                          <span className="text-xs text-zinc-400 whitespace-nowrap">
                            {formatTime(notification.created_at)}
                          </span>
                        </div>
                        <p className="text-sm text-zinc-600 mt-0.5 line-clamp-2">
                          {notification.body}
                        </p>
                        {notification.ticket_number && (
                          <div className="flex items-center gap-1 mt-1">
                            <Ticket className="h-3 w-3 text-orange-600" />
                            <span className="text-xs font-mono text-orange-600">
                              {notification.ticket_number}
                            </span>
                          </div>
                        )}
                      </div>
                      {!notification.read && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="p-1 h-6 w-6"
                          onClick={(e) => {
                            e.stopPropagation();
                            markAsRead(notification.id);
                          }}
                        >
                          <Check className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </div>
      )}
    </div>
  );
};

export default NotificationCenter;
