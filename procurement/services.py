from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from procurement.events.publisher import enqueue_event
from procurement.models import (
    AlternativeRequest,
    ExpectedDelivery,
    PurchaseOrder,
    PurchaseOrderItem,
    RFQ,
    RFQRecipient,
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierAgreement,
    SupplierComparison,
    SupplierOffer,
    SupplierOfferItem,
)


@transaction.atomic
def create_supplier(**data: Any) -> Supplier:
    supplier = Supplier(**data)
    supplier.full_clean()
    supplier.save()
    return supplier


@transaction.atomic
def create_rfq(
    purchase_request: PurchaseRequest,
    *,
    status: str = RFQ.Status.DRAFT,
    deadline_at: datetime | None = None,
) -> RFQ:
    rfq = RFQ(
        purchase_request=purchase_request,
        status=status,
        deadline_at=deadline_at,
    )
    rfq.full_clean()
    rfq.save()
    enqueue_event(
        "procurement.rfq_created",
        rfq.pk,
        {
            "rfq_id": str(rfq.pk),
            "purchase_request_id": str(rfq.purchase_request_id),
            "status": rfq.status,
        },
        company_id=purchase_request.company_id,
        project_id=purchase_request.project_id,
    )
    return rfq


@transaction.atomic
def add_rfq_recipient(
    rfq: RFQ,
    supplier: Supplier,
    *,
    channel: str = RFQRecipient.Channel.EMAIL,
    sent_at: datetime | None = None,
    delivery_status: str = RFQRecipient.DeliveryStatus.PENDING,
) -> RFQRecipient:
    # Serialize writes to an RFQ so concurrent registrations see existing rows.
    rfq = RFQ.objects.select_for_update().get(pk=rfq.pk)
    recipient = RFQRecipient(
        rfq=rfq,
        supplier=supplier,
        channel=channel,
        sent_at=sent_at,
        delivery_status=delivery_status,
    )
    recipient.full_clean()
    recipient.save()
    return recipient


@transaction.atomic
def register_supplier_offer(
    rfq: RFQ,
    supplier: Supplier,
    offer_data: dict[str, Any],
    items: Iterable[dict[str, Any]],
) -> SupplierOffer:
    items = list(items)
    if not items:
        raise ValidationError({"items": "An offer must contain at least one item."})

    rfq = RFQ.objects.select_for_update().get(pk=rfq.pk)
    offer = SupplierOffer(rfq=rfq, supplier=supplier, **offer_data)
    offer.full_clean()
    offer.save()

    for index, item_data in enumerate(items, start=1):
        item = SupplierOfferItem(supplier_offer=offer, **item_data)
        try:
            item.full_clean()
            if item.request_item.purchase_request_id != rfq.purchase_request_id:
                raise ValidationError(
                    {"request_item": "The item must belong to the RFQ purchase request."}
                )
        except ValidationError as error:
            raise ValidationError(
                {"items": [f"Item {index}: {message}" for message in error.messages]}
            ) from error
        item.save()

    enqueue_event(
        "procurement.supplier_offer_received",
        offer.pk,
        {
            "supplier_offer_id": str(offer.pk),
            "rfq_id": str(rfq.pk),
            "supplier_id": str(supplier.pk),
            "status": offer.status,
        },
        company_id=rfq.purchase_request.company_id,
        project_id=rfq.purchase_request.project_id,
    )
    return offer


@transaction.atomic
def create_purchase_request(
    *,
    project_id: UUID,
    specification_version_id: UUID,
    requested_by: UUID,
    company_id: UUID | None = None,
    supplier_agreement: SupplierAgreement | None = None,
    comment: str = "",
    items: Iterable[dict[str, Any]] | None = None,
) -> PurchaseRequest:
    purchase_request = PurchaseRequest(
        company_id=company_id or uuid4(),
        project_id=project_id,
        specification_version_id=specification_version_id,
        requested_by=requested_by,
        supplier_agreement=supplier_agreement,
        comment=comment,
    )
    purchase_request.full_clean()
    purchase_request.save()
    if items is not None:
        item_data = list(items)
        if not item_data:
            raise ValidationError({"items": "A purchase request must contain at least one item."})
        for index, values in enumerate(item_data, start=1):
            values = dict(values)
            values.setdefault("position", index)
            values.setdefault("estimated_unit_price", values.get("budget_price") or Decimal("0"))
            item = PurchaseRequestItem(purchase_request=purchase_request, **values)
            try:
                item.full_clean()
            except ValidationError as error:
                raise ValidationError(
                    {"items": [f"Item {index}: {message}" for message in error.messages]}
                ) from error
            item.save()
    enqueue_event(
        "procurement.request_created",
        purchase_request.pk,
        {
            "purchase_request_id": str(purchase_request.pk),
            "project_id": str(purchase_request.project_id),
            "specification_version_id": str(purchase_request.specification_version_id),
        },
        company_id=purchase_request.company_id,
        project_id=purchase_request.project_id,
        actor_id=purchase_request.requested_by,
    )
    return purchase_request


@transaction.atomic
def create_supplier_comparison(
    purchase_request: PurchaseRequest,
    *,
    version: int,
    criteria: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> SupplierComparison:
    comparison = SupplierComparison(
        purchase_request=purchase_request,
        version=version,
        criteria={} if criteria is None else criteria,
        result={} if result is None else result,
    )
    comparison.full_clean()
    comparison.save()
    enqueue_event(
        "procurement.comparison_created",
        comparison.pk,
        {
            "comparison_id": str(comparison.pk),
            "purchase_request_id": str(purchase_request.pk),
            "version": comparison.version,
        },
        company_id=purchase_request.company_id,
        project_id=purchase_request.project_id,
    )
    return comparison


@transaction.atomic
def create_purchase_order(
    *,
    project_id: UUID,
    supplier: Supplier,
    number: str,
    currency_code: str,
    items: Iterable[dict[str, Any]],
) -> PurchaseOrder:
    item_data = list(items)
    if not item_data:
        raise ValidationError({"items": "A purchase order must contain at least one item."})

    purchase_order = PurchaseOrder(
        project_id=project_id,
        supplier=supplier,
        number=number,
        currency_code=currency_code,
        total_amount=Decimal("0.0000"),
    )
    purchase_order.full_clean()
    purchase_order.save()

    # Preserve full product and sum precision before rounding the final amount.
    with localcontext() as decimal_context:
        decimal_context.prec = 40 + len(str(len(item_data)))
        total_amount = Decimal("0")
        for index, values in enumerate(item_data, start=1):
            item = PurchaseOrderItem(purchase_order=purchase_order, **values)
            try:
                item.full_clean()
            except ValidationError as error:
                raise ValidationError(
                    {"items": [f"Item {index}: {message}" for message in error.messages]}
                ) from error
            item.save()
            total_amount += item.quantity * item.unit_price

        purchase_order.total_amount = total_amount.quantize(
            Decimal("0.0001"),
            rounding=ROUND_HALF_UP,
        )
    purchase_order.full_clean()
    purchase_order.save(update_fields=("total_amount", "updated_at"))
    enqueue_event(
        "procurement.purchase_order_created",
        purchase_order.pk,
        {
            "purchase_order_id": str(purchase_order.pk),
            "project_id": str(purchase_order.project_id),
            "supplier_id": str(purchase_order.supplier_id),
            "number": purchase_order.number,
            "currency_code": purchase_order.currency_code,
            "total_amount": str(purchase_order.total_amount),
        },
        project_id=purchase_order.project_id,
    )
    return purchase_order


def _purchase_order_id(purchase_order: PurchaseOrder | UUID | str) -> UUID | str:
    return purchase_order.pk if isinstance(purchase_order, PurchaseOrder) else purchase_order


@transaction.atomic
def approve_purchase_order(purchase_order: PurchaseOrder | UUID | str) -> PurchaseOrder:
    order = PurchaseOrder.objects.select_for_update().get(pk=_purchase_order_id(purchase_order))
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError({"status": "Only draft purchase orders can be approved."})
    if not order.items.exists():
        raise ValidationError({"items": "A purchase order must contain at least one item."})

    order.status = PurchaseOrder.Status.APPROVED
    order.approved_at = timezone.now()
    order.full_clean()
    order.save(update_fields=("status", "approved_at", "updated_at"))
    enqueue_event(
        "procurement.purchase_order_approved",
        order.pk,
        {
            "purchase_order_id": str(order.pk),
            "status": order.status,
            "approved_at": order.approved_at.isoformat(),
        },
        project_id=order.project_id,
    )
    return order


@transaction.atomic
def mark_purchase_order_sent(purchase_order: PurchaseOrder | UUID | str) -> PurchaseOrder:
    order = PurchaseOrder.objects.select_for_update().get(pk=_purchase_order_id(purchase_order))
    if order.status != PurchaseOrder.Status.APPROVED or order.approved_at is None:
        raise ValidationError({"status": "Only approved purchase orders can be sent."})

    order.status = PurchaseOrder.Status.SENT
    order.sent_at = timezone.now()
    order.full_clean()
    order.save(update_fields=("status", "sent_at", "updated_at"))
    enqueue_event(
        "procurement.purchase_order_sent",
        order.pk,
        {
            "purchase_order_id": str(order.pk),
            "status": order.status,
            "sent_at": order.sent_at.isoformat(),
        },
        project_id=order.project_id,
    )
    return order


@transaction.atomic
def mark_rfq_sent(rfq: RFQ | UUID | str) -> RFQ:
    rfq_id = rfq.pk if isinstance(rfq, RFQ) else rfq
    current = RFQ.objects.select_for_update().get(pk=rfq_id)
    if current.status != RFQ.Status.DRAFT:
        raise ValidationError({"status": "Only draft RFQs can be sent."})
    current.status = RFQ.Status.OPEN
    current.full_clean()
    current.save(update_fields=("status", "updated_at"))
    enqueue_event(
        "procurement.rfq_sent",
        current.pk,
        {
            "rfq_id": str(current.pk),
            "purchase_request_id": str(current.purchase_request_id),
            "status": current.status,
            "updated_at": current.updated_at.isoformat(),
        },
        company_id=current.purchase_request.company_id,
        project_id=current.purchase_request.project_id,
    )
    return current


@transaction.atomic
def verify_supplier_offer(offer: SupplierOffer | UUID | str) -> SupplierOffer:
    offer_id = offer.pk if isinstance(offer, SupplierOffer) else offer
    current = SupplierOffer.objects.select_for_update().get(pk=offer_id)
    if current.status != SupplierOffer.Status.RECEIVED:
        raise ValidationError({"status": "Only received supplier offers can be verified."})
    current.status = SupplierOffer.Status.VERIFIED
    current.full_clean()
    current.save(update_fields=("status", "updated_at"))
    enqueue_event(
        "procurement.supplier_offer_verified",
        current.pk,
        {
            "supplier_offer_id": str(current.pk),
            "rfq_id": str(current.rfq_id),
            "supplier_id": str(current.supplier_id),
            "status": current.status,
        },
        company_id=current.rfq.purchase_request.company_id,
        project_id=current.rfq.purchase_request.project_id,
    )
    return current


@transaction.atomic
def create_alternative_request(
    *,
    project_id: UUID,
    request_item: PurchaseRequestItem,
    original_nomenclature_id: UUID,
    alternative_nomenclature_id: UUID,
) -> AlternativeRequest:
    alternative_request = AlternativeRequest(
        project_id=project_id,
        request_item=request_item,
        original_nomenclature_id=original_nomenclature_id,
        alternative_nomenclature_id=alternative_nomenclature_id,
    )
    alternative_request.full_clean()
    if alternative_request.project_id != request_item.purchase_request.project_id:
        raise ValidationError({"project_id": "The project must match the purchase request."})
    if alternative_request.original_nomenclature_id != request_item.nomenclature_id:
        raise ValidationError(
            {"original_nomenclature_id": "The original nomenclature must match the request item."}
        )
    alternative_request.save()
    enqueue_event(
        "procurement.alternative_requested",
        alternative_request.pk,
        {
            "alternative_request_id": str(alternative_request.pk),
            "project_id": str(alternative_request.project_id),
            "request_item_id": str(alternative_request.request_item_id),
            "original_nomenclature_id": str(alternative_request.original_nomenclature_id),
            "alternative_nomenclature_id": str(alternative_request.alternative_nomenclature_id),
        },
        company_id=request_item.purchase_request.company_id,
        project_id=alternative_request.project_id,
    )
    return alternative_request


@transaction.atomic
def record_alternative_technical_review(
    *,
    alternative_request_id: UUID | str,
    technical_review_id: UUID | str,
    decision: str,
) -> AlternativeRequest:
    if decision not in ("approved", "rejected"):
        raise ValidationError({"decision": "Decision must be approved or rejected."})
    alternative_request = AlternativeRequest.objects.select_for_update().get(
        pk=alternative_request_id
    )
    if alternative_request.status not in (
        AlternativeRequest.Status.REQUESTED,
        AlternativeRequest.Status.TECHNICAL_REVIEW,
    ):
        raise ValidationError({"status": "Technical review is not allowed in this status."})

    alternative_request.technical_review_id = technical_review_id
    alternative_request.status = (
        AlternativeRequest.Status.TECHNICALLY_APPROVED
        if decision == "approved"
        else AlternativeRequest.Status.TECHNICALLY_REJECTED
    )
    alternative_request.full_clean()
    alternative_request.save(update_fields=("technical_review_id", "status", "updated_at"))
    return alternative_request


@transaction.atomic
def record_alternative_client_decision(
    alternative_request: AlternativeRequest | UUID | str,
    decision: str,
) -> AlternativeRequest:
    if decision not in ("approved", "rejected"):
        raise ValidationError({"client_decision": "Decision must be approved or rejected."})
    request_id = alternative_request.pk if isinstance(alternative_request, AlternativeRequest) else alternative_request
    current = AlternativeRequest.objects.select_for_update().get(pk=request_id)
    if current.status != AlternativeRequest.Status.TECHNICALLY_APPROVED:
        raise ValidationError({"status": "Client decision requires a technically approved alternative."})

    current.client_decision = decision
    current.status = (
        AlternativeRequest.Status.APPROVED
        if decision == "approved"
        else AlternativeRequest.Status.REJECTED
    )
    current.full_clean()
    current.save(update_fields=("client_decision", "status", "updated_at"))
    event_name = (
        "procurement.alternative_approved"
        if decision == "approved"
        else "procurement.alternative_rejected"
    )
    enqueue_event(
        event_name,
        current.pk,
        {
            "alternative_request_id": str(current.pk),
            "project_id": str(current.project_id),
            "client_decision": decision,
            "status": current.status,
        },
        company_id=current.request_item.purchase_request.company_id,
        project_id=current.project_id,
    )
    return current


@transaction.atomic
def record_expected_delivery(
    *,
    purchase_order: PurchaseOrder,
    planned_date: date,
    actual_date: date | None = None,
    early_delivery_reason: str = "",
    status: str = ExpectedDelivery.Status.EXPECTED,
    tracking: dict[str, Any] | None = None,
) -> ExpectedDelivery:
    delivery = ExpectedDelivery(
        purchase_order=purchase_order,
        planned_date=planned_date,
        actual_date=actual_date,
        early_delivery_reason=early_delivery_reason.strip(),
        status=status,
        tracking={} if tracking is None else tracking,
    )
    delivery.full_clean()
    delivery.save()
    payload = {
        "expected_delivery_id": str(delivery.pk),
        "purchase_order_id": str(delivery.purchase_order_id),
        "planned_date": delivery.planned_date.isoformat(),
        "status": delivery.status,
    }
    enqueue_event("procurement.delivery_expected", delivery.pk, payload, project_id=purchase_order.project_id)
    if delivery.status == ExpectedDelivery.Status.DELAYED:
        enqueue_event("procurement.delivery_delayed", delivery.pk, payload, project_id=purchase_order.project_id)
    return delivery
