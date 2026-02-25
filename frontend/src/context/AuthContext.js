import { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

const API_URL = process.env.REACT_APP_BACKEND_URL;

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState(localStorage.getItem('pdpv_token'));

  useEffect(() => {
    const checkAuth = async () => {
      const savedToken = localStorage.getItem('pdpv_token');
      if (savedToken) {
        try {
          const response = await axios.get(`${API_URL}/api/auth/me`, {
            headers: { Authorization: `Bearer ${savedToken}` }
          });
          setUser(response.data);
          setToken(savedToken);
        } catch (error) {
          localStorage.removeItem('pdpv_token');
          setToken(null);
          setUser(null);
        }
      }
      setLoading(false);
    };
    checkAuth();
  }, []);

  const login = async (email, password) => {
    const response = await axios.post(`${API_URL}/api/auth/login`, { email, password });
    const { token: newToken } = response.data;
    localStorage.setItem('pdpv_token', newToken);
    setToken(newToken);
    // Fetch full user data (includes dashboard preferences)
    const meResponse = await axios.get(`${API_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${newToken}` }
    });
    setUser(meResponse.data);
    return meResponse.data;
  };

  const logout = () => {
    localStorage.removeItem('pdpv_token');
    setToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    const savedToken = localStorage.getItem('pdpv_token');
    if (savedToken) {
      try {
        const response = await axios.get(`${API_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${savedToken}` }
        });
        setUser(response.data);
      } catch (_) {}
    }
  };

  const getAuthHeaders = () => ({
    Authorization: `Bearer ${token}`
  });

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout, getAuthHeaders, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
