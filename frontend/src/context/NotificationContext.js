import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { useAuth } from './AuthContext';
import { toast } from 'sonner';

const NotificationContext = createContext(null);

const API_URL = process.env.REACT_APP_BACKEND_URL;
const WS_URL = API_URL.replace('https://', 'wss://').replace('http://', 'ws://');

export const NotificationProvider = ({ children }) => {
  const { user, token } = useAuth();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [webPushEnabled, setWebPushEnabled] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Request Web Push permission
  const requestWebPushPermission = useCallback(async () => {
    if (!('Notification' in window)) {
      console.log('Este browser não suporta notificações');
      return false;
    }

    if (Notification.permission === 'granted') {
      setWebPushEnabled(true);
      return true;
    }

    if (Notification.permission !== 'denied') {
      const permission = await Notification.requestPermission();
      if (permission === 'granted') {
        setWebPushEnabled(true);
        toast.success('Notificações ativadas!');
        return true;
      }
    }
    return false;
  }, []);

  // Show browser notification
  const showBrowserNotification = useCallback((title, body, data = {}) => {
    if (webPushEnabled && Notification.permission === 'granted') {
      const notification = new Notification(title, {
        body,
        icon: '/favicon.ico',
        badge: '/favicon.ico',
        tag: data.ticket_id || 'pdpv-notification',
        requireInteraction: false,
        silent: false
      });

      notification.onclick = () => {
        window.focus();
        if (data.ticket_id) {
          window.location.href = `/tickets/${data.ticket_id}`;
        }
        notification.close();
      };

      // Auto close after 5 seconds
      setTimeout(() => notification.close(), 5000);
    }
  }, [webPushEnabled]);

  // Fetch notifications from API
  const fetchNotifications = useCallback(async () => {
    if (!token) return;
    
    try {
      const [notifRes, countRes] = await Promise.all([
        axios.get(`${API_URL}/api/notifications`, {
          headers: { Authorization: `Bearer ${token}` }
        }),
        axios.get(`${API_URL}/api/notifications/unread-count`, {
          headers: { Authorization: `Bearer ${token}` }
        })
      ]);
      setNotifications(notifRes.data);
      setUnreadCount(countRes.data.count);
    } catch (error) {
      console.error('Error fetching notifications:', error);
    }
  }, [token]);

  // Mark notification as read
  const markAsRead = useCallback(async (notificationId) => {
    if (!token) return;
    
    try {
      await axios.put(
        `${API_URL}/api/notifications/${notificationId}/read`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setNotifications(prev => 
        prev.map(n => n.id === notificationId ? { ...n, read: true } : n)
      );
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (error) {
      console.error('Error marking notification as read:', error);
    }
  }, [token]);

  // Mark all as read
  const markAllAsRead = useCallback(async () => {
    if (!token) return;
    
    try {
      await axios.put(
        `${API_URL}/api/notifications/read-all`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch (error) {
      console.error('Error marking all as read:', error);
    }
  }, [token]);

  // WebSocket connection
  const connectWebSocket = useCallback(() => {
    if (!token || !user) return;

    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    try {
      const ws = new WebSocket(`${WS_URL}/ws/${token}`);
      
      ws.onopen = () => {
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'notification') {
            const notification = data.data;
            
            // Add to local state
            setNotifications(prev => [notification, ...prev]);
            setUnreadCount(prev => prev + 1);
            
            // Show in-app toast
            toast(notification.title, {
              description: notification.body,
              action: notification.ticket_id ? {
                label: 'Ver',
                onClick: () => window.location.href = `/tickets/${notification.ticket_id}`
              } : undefined
            });
            
            // Show browser notification
            showBrowserNotification(notification.title, notification.body, {
              ticket_id: notification.ticket_id
            });
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      };

      ws.onclose = (event) => {
        console.log('WebSocket disconnected', event.code);
        wsRef.current = null;
        
        // Reconnect after 5 seconds if not intentional close
        if (event.code !== 1000 && token) {
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket();
          }, 5000);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      wsRef.current = ws;

      // Ping every 30 seconds to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 30000);

      return () => {
        clearInterval(pingInterval);
        ws.close();
      };
    } catch (error) {
      console.error('Error connecting WebSocket:', error);
    }
  }, [token, user, showBrowserNotification]);

  // Connect WebSocket when user logs in
  useEffect(() => {
    if (token && user) {
      fetchNotifications();
      connectWebSocket();

      // Check Web Push permission status
      if ('Notification' in window && Notification.permission === 'granted') {
        setWebPushEnabled(true);
      }
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [token, user, fetchNotifications, connectWebSocket]);

  return (
    <NotificationContext.Provider value={{
      notifications,
      unreadCount,
      webPushEnabled,
      fetchNotifications,
      markAsRead,
      markAllAsRead,
      requestWebPushPermission
    }}>
      {children}
    </NotificationContext.Provider>
  );
};

export const useNotifications = () => {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotifications must be used within NotificationProvider');
  }
  return context;
};
