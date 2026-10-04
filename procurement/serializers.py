from decimal import Decimal

from rest_framework import serializers

from procurement.models import (
    AlternativeRequest,
    ExpectedDelivery,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    RFQ,
    RFQRecipient,
    SupplierComparison,
    SupplierOffer,
    SupplierOfferItem,
    Supplier,
)
from procurement.services import (
    add_rfq_recipient,
    create_alternative_request,
    create_purchase_order,
    create_purchase_request,
    create_supplier,
    create_supplier_comparison,
    create_rfq,
    record_expected_delivery,
    register_supplier_offer,
)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = (
            "id", "company_id", "code", "name", "bin", "supplier_type", "status",
            "rating", "email", "phone", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        return create_supplier(**validated_data)


class PurchaseRequestItemSerializer(serializers.ModelSerializer):
    position = serializers.IntegerField(min_value=1, required=False)
    quantity = serializers.DecimalField(max_digits=20, decimal_places=6, min_value=Decimal("0.000001"))
    budget_price = serializers.DecimalField(
        max_digits=20, decimal_places=4, min_value=Decimal("0"), required=False, allow_null=True
    )

    class Meta:
        model = PurchaseRequestItem
        fields = (
            "id", "purchase_request", "position", "description", "nomenclature_id",
            "quantity", "unit_id", "required_by", "budget_price", "route_type",
            "estimated_unit_price", "created_at", "updated_at",
        )
        read_only_fields = ("id", "purchase_request", "estimated_unit_price", "created_at", "updated_at")
        validators = []


class PurchaseRequestSerializer(serializers.ModelSerializer):
    items = PurchaseRequestItemSerializer(many=True, allow_empty=False)

    class Meta:
        model = PurchaseRequest
        fields = (
            "id", "company_id", "project_id", "specification_version_id", "requested_by",
            "supplier_agreement", "status", "comment", "items", "created_at", "updated_at",
        )
        read_only_fields = ("id", "status", "created_at", "updated_at")

    def create(self, validated_data):
        return create_purchase_request(**validated_data)


class RFQSerializer(serializers.ModelSerializer):
    class Meta:
        model = RFQ
        fields = (
            "id",
            "purchase_request",
            "status",
            "deadline_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        return create_rfq(**validated_data)


class RFQRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = RFQRecipient
        fields = (
            "id",
            "rfq",
            "supplier",
            "channel",
            "sent_at",
            "delivery_status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "rfq", "created_at", "updated_at")
        validators = []

    def create(self, validated_data):
        return add_rfq_recipient(**validated_data)


class SupplierOfferItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierOfferItem
        fields = (
            "id",
            "supplier_offer",
            "request_item",
            "nomenclature_id",
            "quantity",
            "unit_price",
            "availability",
            "delivery_days",
            "technical_match",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "supplier_offer", "created_at", "updated_at")
        validators = []


class SupplierOfferSerializer(serializers.ModelSerializer):
    items = SupplierOfferItemSerializer(many=True, allow_empty=False)

    class Meta:
        model = SupplierOffer
        fields = (
            "id",
            "rfq",
            "supplier",
            "status",
            "currency_code",
            "offer_date",
            "valid_until",
            "source_document_id",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        validators = []

    def create(self, validated_data):
        rfq = validated_data.pop("rfq")
        supplier = validated_data.pop("supplier")
        items = validated_data.pop("items")
        return register_supplier_offer(rfq, supplier, validated_data, items)


class SupplierComparisonSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierComparison
        fields = (
            "id",
            "purchase_request",
            "version",
            "criteria",
            "result",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        return create_supplier_comparison(**validated_data)


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderItem
        fields = (
            "id",
            "nomenclature_id",
            "quantity",
            "unit_price",
            "expected_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, allow_empty=False)

    class Meta:
        model = PurchaseOrder
        fields = (
            "id",
            "project_id",
            "supplier",
            "status",
            "number",
            "currency_code",
            "total_amount",
            "approved_at",
            "sent_at",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "total_amount",
            "approved_at",
            "sent_at",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        items = validated_data.pop("items")
        return create_purchase_order(items=items, **validated_data)


class AlternativeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlternativeRequest
        fields = (
            "id",
            "project_id",
            "request_item",
            "original_nomenclature_id",
            "alternative_nomenclature_id",
            "status",
            "technical_review_id",
            "client_decision",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "technical_review_id",
            "client_decision",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        return create_alternative_request(**validated_data)


class ExpectedDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpectedDelivery
        fields = (
            "id",
            "purchase_order",
            "planned_date",
            "actual_date",
            "early_delivery_reason",
            "status",
            "tracking",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        return record_expected_delivery(**validated_data)
