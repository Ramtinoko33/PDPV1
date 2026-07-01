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
import TicketReplyPage from "./pages/TicketReplyPage";
import IntakePage from "./pages/IntakePage";
import TelegramPage from "./pages/TelegramPage";
import AlertsPage from "./pages/AlertsPage";
import RentingPage from "./pages/RentingPage";
import RentingDetail from "./pages/RentingDetail";
import AssistenciasPage from "./pages/AssistenciasPage";
import AssistenciasDetail from "./pages/AssistenciasDetail";
import AdminAssistenciasUsers from "./pages/AdminAssistenciasUsers";
import NormalizationSettings from "./pages/NormalizationSettings";
import AdminTelegramUsers from "./pages/AdminTelegramUsers";
import {
  FinanceDashboard,
  CollectionsToday,
  FinanceClients,
  FinanceClientDetail,
  FinanceImports,
  FinancePromises,
  Regularizations,
  BlockRequests
} from "./pages/finance";
import Layout from "./components/Layout";

// Module-level constants prevent new array creation on each render (avoids prop reference churn)
const ROLES_ALL = ['ADMIN', 'SUPERVISOR', 'AGENT'];
const ROLES_ALL_WITH_CREATOR = ['ADMIN', 'SUPERVISOR', 'AGENT', 'INTERNAL_CREATOR'];
const ROLES_MANAGERS = ['ADMIN', 'SUPERVISOR'];
const ROLES_ADMIN_ONLY = ['ADMIN'];

const ProtectedRoute = ({ children, allowedRoles, requireFinanceAccess }) => {
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
  
  // Check finance access (module-specific role independent of core role)
  if (requireFinanceAccess && !user.finance_role && user.role !== 'ADMIN') {
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
      
      {/* Public route for ticket reply - NO AUTH */}
      <Route path="/ticket/reply/:token" element={<TicketReplyPage />} />
      
      <Route path="/dashboard" element={
        <ProtectedRoute>
          <Dashboard />
        </ProtectedRoute>
      } />
      
      <Route path="/tickets" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <TicketList />
        </ProtectedRoute>
      } />
      
      <Route path="/tickets/new" element={
        <ProtectedRoute allowedRoles={ROLES_ALL_WITH_CREATOR}>
          <CreateTicket />
        </ProtectedRoute>
      } />
      
      <Route path="/tickets/:id" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <TicketDetail />
        </ProtectedRoute>
      } />
      
      <Route path="/tickets/archived" element={
        <ProtectedRoute allowedRoles={ROLES_MANAGERS}>
          <ArchivedTickets />
        </ProtectedRoute>
      } />
      
      <Route path="/reminders" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <Reminders />
        </ProtectedRoute>
      } />
      
      <Route path="/customers" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <CustomerManagement />
        </ProtectedRoute>
      } />
      
      <Route path="/users" element={
        <ProtectedRoute allowedRoles={ROLES_ADMIN_ONLY}>
          <UserManagement />
        </ProtectedRoute>
      } />
      
      <Route path="/settings" element={
        <ProtectedRoute allowedRoles={ROLES_ADMIN_ONLY}>
          <AdminSettings />
        </ProtectedRoute>
      } />
      
      <Route path="/settings/normalization" element={
        <ProtectedRoute allowedRoles={ROLES_MANAGERS}>
          <NormalizationSettings />
        </ProtectedRoute>
      } />
      
      <Route path="/reports" element={
        <ProtectedRoute allowedRoles={ROLES_MANAGERS}>
          <AdminReports />
        </ProtectedRoute>
      } />
      
      {/* Hidden module pages - only visible if module enabled */}
      <Route path="/intake" element={
        <ProtectedRoute allowedRoles={ROLES_MANAGERS}>
          <IntakePage />
        </ProtectedRoute>
      } />
      
      <Route path="/telegram" element={
        <ProtectedRoute allowedRoles={ROLES_ADMIN_ONLY}>
          <TelegramPage />
        </ProtectedRoute>
      } />
      
      <Route path="/alertas" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <AlertsPage />
        </ProtectedRoute>
      } />

      <Route path="/renting" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <RentingPage />
        </ProtectedRoute>
      } />

      <Route path="/renting/:id" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <RentingDetail />
        </ProtectedRoute>
      } />

      <Route path="/assistencias" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <AssistenciasPage />
        </ProtectedRoute>
      } />

      <Route path="/assistencias/:id" element={
        <ProtectedRoute allowedRoles={ROLES_ALL}>
          <AssistenciasDetail />
        </ProtectedRoute>
      } />

      <Route path="/admin/assistencias-users" element={
        <ProtectedRoute allowedRoles={ROLES_ADMIN_ONLY}>
          <AdminAssistenciasUsers />
        </ProtectedRoute>
      } />

      <Route path="/admin/telegram-users" element={
        <ProtectedRoute allowedRoles={ROLES_ADMIN_ONLY}>
          <AdminTelegramUsers />
        </ProtectedRoute>
      } />

      {/* CRM Finance module — gated by requireFinanceAccess */}
      <Route path="/finance" element={
        <ProtectedRoute requireFinanceAccess>
          <FinanceDashboard />
        </ProtectedRoute>
      } />
      <Route path="/finance/collections-today" element={
        <ProtectedRoute requireFinanceAccess>
          <CollectionsToday />
        </ProtectedRoute>
      } />
      <Route path="/finance/clients" element={
        <ProtectedRoute requireFinanceAccess>
          <FinanceClients />
        </ProtectedRoute>
      } />
      <Route path="/finance/clients/:clientId" element={
        <ProtectedRoute requireFinanceAccess>
          <FinanceClientDetail />
        </ProtectedRoute>
      } />
      <Route path="/finance/imports" element={
        <ProtectedRoute requireFinanceAccess>
          <FinanceImports />
        </ProtectedRoute>
      } />
      <Route path="/finance/promises" element={
        <ProtectedRoute requireFinanceAccess>
          <FinancePromises />
        </ProtectedRoute>
      } />
      <Route path="/finance/regularizations" element={
        <ProtectedRoute requireFinanceAccess>
          <Regularizations />
        </ProtectedRoute>
      } />
      <Route path="/finance/blocks" element={
        <ProtectedRoute requireFinanceAccess>
          <BlockRequests />
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
