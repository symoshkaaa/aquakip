from rest_framework.routers import DefaultRouter

from procurement.views import (
	AlternativeRequestViewSet,
	ExpectedDeliveryViewSet,
	PurchaseOrderViewSet,
	RFQViewSet,
	SupplierComparisonViewSet,
	SupplierOfferViewSet,
	SupplierViewSet,
	PurchaseRequestViewSet,
)


router = DefaultRouter(use_regex_path=False)
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-requests", PurchaseRequestViewSet, basename="purchase-request")
router.register("rfqs", RFQViewSet, basename="rfq")
router.register("supplier-offers", SupplierOfferViewSet, basename="supplier-offer")
router.register(
	"supplier-comparisons",
	SupplierComparisonViewSet,
	basename="supplier-comparison",
)
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register(
	"alternative-requests",
	AlternativeRequestViewSet,
	basename="alternative-request",
)
router.register(
	"expected-deliveries",
	ExpectedDeliveryViewSet,
	basename="expected-delivery",
)

app_name = "procurement"
urlpatterns = router.urls
