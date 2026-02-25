import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { NotificationProvider } from "./context/NotificationContext";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import TicketList from "./pages/TicketList";
import TicketDetail from "./pages/TicketDetail";
import CreateTicket from "./pages/CreateTicket";
import ArchivedTickets from "./pages/ArchivedTickets";
import Reminders from "./pages/Reminders";
import UserManagement from "./pages/UserManagement";
import CustomerManagement from "./pages/CustomerManagement";
import AdminSettings from "./pages/AdminSettings";
import AdminReports from "./pages/AdminReports";
import QuoteResponse from "./pages/QuoteResponse";
import Layout from "./components/Layout";

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-orange-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-zinc-600">A carregar...</p>
        </div>
      </div>
    );
  }
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }
  
  return <Layout>{children}</Layout>;
};

function AppRoutes() {
  const { user } = useAuth();
  
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/dashboard" replace /> : <Login />} />
      
      {/* Public route for quote response - NO AUTH */}
      <Route path="/quote/:token" element={<QuoteResponse />} />
      
      <Route path="/dashboard" element={
        <ProtectedRoute>
          <Dashboard />
        </ProtectedRoute>
      } />
      
      <Route path="/tickets" element={
        <ProtectedRoute allowedRoles={['ADMIN', 'SUPERVISOR', 'AGENT']}>
          <TicketList />
        </ProtectedRoute>
      } />
      
      <Route path="/tickets/new" element={
        <ProtectedRoute allowedRoles={['ADMIN', 'SUPERVISOR', 'AGENT', 'INTERNAL_CREATOR']}>
          <CreateTicket />
        </ProtectedRoute>
      } />
      
      <Route path="/tickets/:id" element={
        <ProtectedRoute allowedRoles={['ADMIN', 'SUPERVISOR', 'AGENT']}>
          <TicketDetail />
        </ProtectedRoute>
      } />
      
      <Route path="/tickets/archived" element={
        <ProtectedRoute allowedRoles={['ADMIN', 'SUPERVISOR']}>
          <ArchivedTickets />
        </ProtectedRoute>
      } />
      
      <Route path="/customers" element={
        <ProtectedRoute allowedRoles={['ADMIN', 'SUPERVISOR', 'AGENT']}>
          <CustomerManagement />
        </ProtectedRoute>
      } />
      
      <Route path="/users" element={
        <ProtectedRoute allowedRoles={['ADMIN']}>
          <UserManagement />
        </ProtectedRoute>
      } />
      
      <Route path="/settings" element={
        <ProtectedRoute allowedRoles={['ADMIN']}>
          <AdminSettings />
        </ProtectedRoute>
      } />
      
      <Route path="/reports" element={
        <ProtectedRoute allowedRoles={['ADMIN', 'SUPERVISOR']}>
          <AdminReports />
        </ProtectedRoute>
      } />
      
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <NotificationProvider>
          <AppRoutes />
          <Toaster position="top-right" richColors />
        </NotificationProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
