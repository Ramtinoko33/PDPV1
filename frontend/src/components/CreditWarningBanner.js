import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { ShieldAlert } from 'lucide-react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export const CreditWarningBanner = ({ phone }) => {
  const { getAuthHeaders } = useAuth();
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!phone) return;
    axios.get(`${API_URL}/api/finance/credit-warning`, {
      params: { phone },
      headers: getAuthHeaders(),
    })
      .then((res) => setShow(!!res.data?.show_warning))
      .catch(() => setShow(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phone]);

  if (!show) return null;

  return (
    <div
      className="bg-amber-50 border border-amber-300 rounded-lg p-4 flex items-center gap-3"
      data-testid="credit-warning-banner"
    >
      <ShieldAlert className="h-5 w-5 text-amber-600 flex-shrink-0" />
      <p className="text-sm font-medium text-amber-800">
        Cliente com validação financeira necessária antes de novo crédito.
      </p>
    </div>
  );
};
