import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Convert VAPID key from base64 to Uint8Array
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export function usePushNotifications() {
  const [isSupported, setIsSupported] = useState(false);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [permission, setPermission] = useState('default');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Check if push notifications are supported
  useEffect(() => {
    const supported = 'serviceWorker' in navigator && 'PushManager' in window;
    setIsSupported(supported);
    
    if (supported) {
      setPermission(Notification.permission);
      checkSubscription();
    }
  }, []);

  // Check if user is already subscribed
  const checkSubscription = async () => {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      setIsSubscribed(!!subscription);
    } catch (err) {
      console.error('Error checking subscription:', err);
    }
  };

  // Register the service worker
  const registerServiceWorker = async () => {
    if (!('serviceWorker' in navigator)) {
      throw new Error('Service Workers não suportados');
    }
    
    const registration = await navigator.serviceWorker.register('/sw.js');
    await navigator.serviceWorker.ready;
    return registration;
  };

  // Subscribe to push notifications
  const subscribe = useCallback(async () => {
    if (!isSupported) {
      setError('Notificações push não suportadas neste browser');
      return false;
    }

    setLoading(true);
    setError(null);

    try {
      // Request notification permission
      const permissionResult = await Notification.requestPermission();
      setPermission(permissionResult);
      
      if (permissionResult !== 'granted') {
        setError('Permissão de notificações negada');
        return false;
      }

      // Register service worker
      const registration = await registerServiceWorker();
      
      // Get VAPID public key from server
      const token = localStorage.getItem('token');
      const { data } = await axios.get(`${API_URL}/api/push/vapid-public-key`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      const vapidPublicKey = urlBase64ToUint8Array(data.publicKey);
      
      // Subscribe to push
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: vapidPublicKey
      });
      
      // Send subscription to server
      await axios.post(`${API_URL}/api/push/subscribe`, subscription.toJSON(), {
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      
      setIsSubscribed(true);
      return true;
    } catch (err) {
      console.error('Error subscribing to push:', err);
      setError(err.message || 'Erro ao ativar notificações');
      return false;
    } finally {
      setLoading(false);
    }
  }, [isSupported]);

  // Unsubscribe from push notifications
  const unsubscribe = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      
      if (subscription) {
        // Notify server
        const token = localStorage.getItem('token');
        await axios.delete(`${API_URL}/api/push/unsubscribe`, {
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          data: subscription.toJSON()
        });
        
        // Unsubscribe locally
        await subscription.unsubscribe();
      }
      
      setIsSubscribed(false);
      return true;
    } catch (err) {
      console.error('Error unsubscribing:', err);
      setError(err.message || 'Erro ao desativar notificações');
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    isSupported,
    isSubscribed,
    permission,
    loading,
    error,
    subscribe,
    unsubscribe
  };
}
