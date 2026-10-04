import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import { SupplierDetail, SupplierForm, SuppliersList } from "./pages/Suppliers";
import { PurchaseRequestDetail, PurchaseRequestForm, PurchaseRequestsList } from "./pages/PurchaseRequests";
import PurchaseOrderForm from "./pages/PurchaseOrderForm";
import AlternativeRequests from "./pages/AlternativeRequests";
import ExpectedDeliveries from "./pages/ExpectedDeliveries";
import { PurchaseOrderDetail, PurchaseOrderList } from "./pages/PurchaseOrders";
import RfqDetail from "./pages/RfqDetail";
import Rfqs, { RfqForm } from "./pages/Rfqs";
import { SupplierComparisonDetail, SupplierComparisonForm, SupplierComparisonsList } from "./pages/SupplierComparisons";
import SupplierOffers, { SupplierOfferDetail, SupplierOfferForm } from "./pages/SupplierOffers";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="suppliers" element={<SuppliersList />} />
        <Route path="suppliers/new" element={<SupplierForm />} />
        <Route path="suppliers/:supplierId" element={<SupplierDetail />} />
        <Route path="purchase-requests" element={<PurchaseRequestsList />} />
        <Route path="purchase-requests/new" element={<PurchaseRequestForm />} />
        <Route path="purchase-requests/:requestId" element={<PurchaseRequestDetail />} />
        <Route path="rfqs" element={<Rfqs />} />
        <Route path="rfqs/new" element={<RfqForm />} />
        <Route path="rfqs/:rfqId" element={<RfqDetail />} />
        <Route path="supplier-offers" element={<SupplierOffers />} />
        <Route path="supplier-offers/new" element={<SupplierOfferForm />} />
        <Route path="supplier-offers/:offerId" element={<SupplierOfferDetail />} />
        <Route path="supplier-comparisons" element={<SupplierComparisonsList />} />
        <Route path="supplier-comparisons/new" element={<SupplierComparisonForm />} />
        <Route path="supplier-comparisons/:comparisonId" element={<SupplierComparisonDetail />} />
        <Route path="purchase-orders" element={<PurchaseOrderList />} />
        <Route path="purchase-orders/new" element={<PurchaseOrderForm />} />
        <Route path="purchase-orders/:orderId" element={<PurchaseOrderDetail />} />
        <Route path="alternative-requests" element={<AlternativeRequests />} />
        <Route path="expected-deliveries" element={<ExpectedDeliveries />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
