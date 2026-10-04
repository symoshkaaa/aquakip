import uuid

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Supplier(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        BLOCKED = "blocked", "Blocked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_id = models.UUIDField(default=uuid.uuid4)
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    bin = models.CharField(max_length=20, null=True, blank=True)
    supplier_type = models.CharField(max_length=48, default="other")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
    )
    rating = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    tax_identifier = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "procurement_supplier"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("code",), name="uniq_supplier_code"),
            models.UniqueConstraint(
                fields=("company_id", "bin"),
                condition=models.Q(bin__isnull=False),
                name="supplier_company_bin_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class SupplierAgreement(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"
        TERMINATED = "terminated", "Terminated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="agreements",
    )
    agreement_type = models.CharField(max_length=48, default="supply")
    contract_number = models.CharField(max_length=64, null=True, blank=True)
    exclusive = models.BooleanField(default=False)
    agreement_number = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    currency = models.CharField(max_length=3, default="KZT")
    amount_limit = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        null=True,
        blank=True,
    )
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    terms = models.JSONField(default=dict, blank=True)
    payment_terms = models.TextField(blank=True)

    class Meta:
        db_table = "procurement_supplier_agreement"
        ordering = ("supplier__name", "agreement_number")
        constraints = [
            models.UniqueConstraint(
                fields=("supplier", "agreement_number"),
                name="uniq_supplier_agreement_number",
            ),
            models.UniqueConstraint(
                fields=("supplier", "contract_number"),
                condition=models.Q(contract_number__isnull=False),
                name="agreement_supplier_contract_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valid_to__isnull=True)
                    | models.Q(valid_to__gte=models.F("valid_from"))
                ),
                name="chk_supplier_agreement_valid_dates",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valid_until__isnull=True)
                    | models.Q(valid_until__gte=models.F("valid_from"))
                ),
                name="agreement_valid_dates_ordered",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(amount_limit__isnull=True)
                    | models.Q(amount_limit__gte=0)
                ),
                name="chk_supplier_agreement_amount_limit_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.agreement_number


class PurchaseRequest(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        ORDERED = "ordered", "Ordered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_id = models.UUIDField(default=uuid.uuid4)
    project_id = models.UUIDField()
    specification_version_id = models.UUIDField()
    requested_by = models.UUIDField()
    supplier_agreement = models.ForeignKey(
        SupplierAgreement,
        on_delete=models.PROTECT,
        related_name="purchase_requests",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    currency = models.CharField(max_length=3, default="KZT")
    required_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)

    class Meta:
        db_table = "procurement_purchase_request"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return str(self.id)


class PurchaseRequestItem(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )
    position = models.PositiveIntegerField()
    nomenclature_id = models.UUIDField()
    unit_id = models.UUIDField()
    required_by = models.DateField(null=True, blank=True)
    budget_price = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        null=True,
        blank=True,
    )
    route_type = models.CharField(max_length=48, default="standard")
    description = models.CharField(max_length=512, blank=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    estimated_unit_price = models.DecimalField(max_digits=20, decimal_places=4)

    class Meta:
        db_table = "procurement_purchase_request_item"
        ordering = ("purchase_request", "position")
        constraints = [
            models.UniqueConstraint(
                fields=("purchase_request", "position"),
                name="uniq_purchase_request_item_position",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="chk_purchase_request_item_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(estimated_unit_price__gte=0),
                name="chk_purchase_request_item_estimated_unit_price_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(budget_price__isnull=True)
                    | models.Q(budget_price__gte=0)
                ),
                name="request_item_budget_nonnegative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.purchase_request_id}: {self.position}"


class RFQ(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.PROTECT,
        related_name="rfqs",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    deadline_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "procurement_rfq"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return str(self.id)


class RFQRecipient(TimestampedModel):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"
        PORTAL = "portal", "Portal"
        MANUAL = "manual", "Manual"

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rfq = models.ForeignKey(
        RFQ,
        on_delete=models.PROTECT,
        related_name="recipients",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="rfq_recipients",
    )
    channel = models.CharField(
        max_length=32,
        choices=Channel.choices,
        default=Channel.EMAIL,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(
        max_length=32,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        db_index=True,
    )

    class Meta:
        db_table = "procurement_rfq_recipient"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("rfq", "supplier"),
                name="uniq_rfq_recipient_supplier",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rfq_id}: {self.supplier_id}"


class SupplierOffer(TimestampedModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        VERIFIED = "verified", "Verified"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rfq = models.ForeignKey(
        RFQ,
        on_delete=models.PROTECT,
        related_name="supplier_offers",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="offers",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.RECEIVED,
        db_index=True,
    )
    currency_code = models.CharField(
        max_length=3,
        default="KZT",
        validators=[
            RegexValidator(
                regex=r"\A[A-Z]{3}\Z",
                message="Use a three-letter uppercase currency code.",
            ),
        ],
    )
    offer_date = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    source_document_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "procurement_supplier_offer"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("rfq", "supplier", "source_document_id"),
                condition=models.Q(source_document_id__isnull=False),
                name="uniq_offer_source_per_supplier_rfq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valid_until__isnull=True)
                    | models.Q(valid_until__gte=models.F("offer_date"))
                ),
                name="chk_supplier_offer_valid_dates",
            ),
        ]

    def __str__(self) -> str:
        return str(self.id)


class SupplierOfferItem(TimestampedModel):
    class Availability(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        IN_STOCK = "in_stock", "In stock"
        ON_ORDER = "on_order", "On order"
        OUT_OF_STOCK = "out_of_stock", "Out of stock"

    class TechnicalMatch(models.TextChoices):
        NOT_REVIEWED = "not_reviewed", "Not reviewed"
        MATCH = "match", "Match"
        PARTIAL = "partial", "Partial match"
        MISMATCH = "mismatch", "Mismatch"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier_offer = models.ForeignKey(
        SupplierOffer,
        on_delete=models.PROTECT,
        related_name="items",
    )
    request_item = models.ForeignKey(
        PurchaseRequestItem,
        on_delete=models.PROTECT,
        related_name="supplier_offer_items",
    )
    nomenclature_id = models.UUIDField()
    quantity = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(0)],
    )
    unit_price = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        validators=[MinValueValidator(0)],
    )
    availability = models.CharField(
        max_length=32,
        choices=Availability.choices,
        default=Availability.UNKNOWN,
    )
    delivery_days = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    technical_match = models.CharField(
        max_length=32,
        choices=TechnicalMatch.choices,
        default=TechnicalMatch.NOT_REVIEWED,
    )

    class Meta:
        db_table = "procurement_supplier_offer_item"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("supplier_offer", "request_item", "nomenclature_id"),
                name="uniq_offer_item_request_nomenclature",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name="chk_offer_item_quantity_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="chk_offer_item_unit_price_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(delivery_days__isnull=True)
                    | models.Q(delivery_days__gte=0)
                ),
                name="chk_offer_item_delivery_days_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.supplier_offer_id}: {self.request_item_id}"


class SupplierComparison(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.PROTECT,
        related_name="comparisons",
    )
    version = models.IntegerField(validators=[MinValueValidator(1)])
    criteria = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "procurement_supplier_comparison"
        ordering = ("purchase_request", "version")
        constraints = [
            models.UniqueConstraint(
                fields=("purchase_request", "version"),
                name="uniq_comparison_request_version",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gt=0),
                name="chk_comparison_version_positive",
            ),
        ]


class PurchaseOrder(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        SENT = "sent", "Sent"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_id = models.UUIDField(db_index=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    number = models.CharField(max_length=64)
    currency_code = models.CharField(
        max_length=3,
        validators=[
            RegexValidator(
                regex=r"\A[A-Z]{3}\Z",
                message="Use a three-letter uppercase currency code.",
            ),
        ],
    )
    total_amount = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        default=0,
        validators=[MinValueValidator(0)],
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "procurement_purchase_order"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("project_id", "number"),
                name="uniq_purchase_order_project_number",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="chk_purchase_order_total_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.number


class PurchaseOrderItem(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="items",
    )
    nomenclature_id = models.UUIDField()
    quantity = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(0)],
    )
    unit_price = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        validators=[MinValueValidator(0)],
    )
    expected_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "procurement_purchase_order_item"
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name="chk_purchase_order_item_quantity_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="chk_purchase_order_item_unit_price_non_negative",
            ),
        ]


class AlternativeRequest(TimestampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        TECHNICAL_REVIEW = "technical_review", "Technical review"
        TECHNICALLY_APPROVED = "technically_approved", "Technically approved"
        TECHNICALLY_REJECTED = "technically_rejected", "Technically rejected"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_id = models.UUIDField(db_index=True)
    request_item = models.ForeignKey(
        PurchaseRequestItem,
        on_delete=models.PROTECT,
        related_name="alternative_requests",
    )
    original_nomenclature_id = models.UUIDField()
    alternative_nomenclature_id = models.UUIDField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_index=True,
    )
    technical_review_id = models.UUIDField(null=True, blank=True)
    client_decision = models.CharField(max_length=32, null=True, blank=True)

    class Meta:
        db_table = "procurement_alternative_request"
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(
                    original_nomenclature_id=models.F("alternative_nomenclature_id")
                ),
                name="chk_alternative_nomenclature_differs",
            ),
        ]


class ExpectedDelivery(TimestampedModel):
    class Status(models.TextChoices):
        EXPECTED = "expected", "Expected"
        IN_TRANSIT = "in_transit", "In transit"
        DELIVERED = "delivered", "Delivered"
        DELAYED = "delayed", "Delayed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="expected_deliveries",
    )
    planned_date = models.DateField()
    actual_date = models.DateField(null=True, blank=True)
    early_delivery_reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.EXPECTED,
        db_index=True,
    )
    tracking = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "procurement_expected_delivery"
        ordering = ("planned_date", "id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(actual_date__isnull=True)
                    | models.Q(actual_date__gte=models.F("planned_date"))
                    | models.Q(early_delivery_reason__regex=r"\S")
                ),
                name="chk_delivery_dates_or_early_reason",
            ),
        ]


class OutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=128)
    event_version = models.PositiveIntegerField(default=1)
    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.UUIDField()
    payload = models.JSONField()
    correlation_id = models.UUIDField(null=True, blank=True)
    causation_id = models.UUIDField(null=True, blank=True)
    company_id = models.UUIDField(null=True, blank=True)
    project_id = models.UUIDField(null=True, blank=True)
    actor_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "procurement_outbox_event"
        ordering = ("created_at", "id")
        indexes = [
            models.Index(
                fields=("created_at", "id"),
                condition=models.Q(published_at__isnull=True),
                name="proc_outbox_pending_idx",
            ),
            models.Index(fields=("aggregate_type", "aggregate_id"), name="proc_outbox_aggregate_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(event_version__gte=1), name="proc_outbox_version_positive"),
        ]


class InboxEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"

    event_id = models.UUIDField(primary_key=True, editable=False)
    producer = models.CharField(max_length=64)
    event_type = models.CharField(max_length=128)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.RECEIVED)

    class Meta:
        db_table = "procurement_inbox_event"
        indexes = [models.Index(fields=("status", "received_at"), name="proc_inbox_status_idx")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status="received", processed_at__isnull=True)
                    | models.Q(status="processed", processed_at__isnull=False)
                ),
                name="proc_inbox_processed_state",
            ),
        ]
