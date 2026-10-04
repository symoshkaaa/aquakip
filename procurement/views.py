from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from procurement.models import RFQ, SupplierOffer
from procurement.models import (
    AlternativeRequest,
    ExpectedDelivery,
    PurchaseOrder,
    PurchaseRequest,
    Supplier,
    SupplierComparison,
)
from procurement.serializers import (
    RFQRecipientSerializer,
    RFQSerializer,
    SupplierOfferSerializer,
    AlternativeRequestSerializer,
    ExpectedDeliverySerializer,
    PurchaseOrderSerializer,
    SupplierComparisonSerializer,
    SupplierSerializer,
    PurchaseRequestSerializer,
)
from procurement.services import approve_purchase_order, mark_purchase_order_sent


class ProcurementPagination(LimitOffsetPagination):
    default_limit = 100
    max_limit = 500


class ProcurementViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    pagination_class = ProcurementPagination
    lookup_value_converter = "uuid"
    filter_fields: tuple[str, ...] = ()

    def get_queryset(self):
        queryset = super().get_queryset()
        for field in self.filter_fields:
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
            exc = ValidationError(detail)
        return super().handle_exception(exc)


class RFQViewSet(ProcurementViewSet):
    queryset = RFQ.objects.select_related("purchase_request")
    serializer_class = RFQSerializer
    filter_fields = ("purchase_request", "status")

    @action(
        detail=True,
        methods=("get", "post"),
        serializer_class=RFQRecipientSerializer,
    )
    def recipients(self, request, pk=None):
        rfq = self.get_object()
        if request.method == "GET":
            recipients = rfq.recipients.select_related("supplier")
            page = self.paginate_queryset(recipients)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(rfq=rfq)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SupplierOfferViewSet(ProcurementViewSet):
    queryset = SupplierOffer.objects.select_related("rfq", "supplier").prefetch_related(
        "items"
    )
    serializer_class = SupplierOfferSerializer
    filter_fields = ("rfq", "supplier", "status")


class SupplierViewSet(ProcurementViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "code", "bin", "email")
    filter_fields = ("status",)


class PurchaseRequestViewSet(ProcurementViewSet):
    queryset = PurchaseRequest.objects.prefetch_related("items")
    serializer_class = PurchaseRequestSerializer
    filter_fields = ("project_id", "status")


class SupplierComparisonViewSet(ProcurementViewSet):
    queryset = SupplierComparison.objects.select_related("purchase_request")
    serializer_class = SupplierComparisonSerializer
    filter_fields = ("purchase_request",)


class PurchaseOrderViewSet(ProcurementViewSet):
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items")
    serializer_class = PurchaseOrderSerializer
    filter_fields = ("project_id", "supplier", "status")

    @action(detail=True, methods=("post",))
    def approve(self, request, pk=None):
        purchase_order = approve_purchase_order(self.get_object())
        return Response(self.get_serializer(purchase_order).data)

    @action(detail=True, methods=("post",))
    def send(self, request, pk=None):
        purchase_order = mark_purchase_order_sent(self.get_object())
        return Response(self.get_serializer(purchase_order).data)


class AlternativeRequestViewSet(ProcurementViewSet):
    queryset = AlternativeRequest.objects.select_related("request_item")
    serializer_class = AlternativeRequestSerializer


class ExpectedDeliveryViewSet(ProcurementViewSet):
    queryset = ExpectedDelivery.objects.select_related(
        "purchase_order",
        "purchase_order__supplier",
    )
    serializer_class = ExpectedDeliverySerializer
    filter_fields = ("purchase_order", "status")
