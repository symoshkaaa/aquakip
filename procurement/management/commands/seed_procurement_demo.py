from datetime import timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from procurement.models import (
    AlternativeRequest, ExpectedDelivery, PurchaseOrder, PurchaseRequest,
    PurchaseRequestItem, RFQ, RFQRecipient, Supplier, SupplierComparison, SupplierOffer, SupplierOfferItem,
)
from procurement.services import (
    approve_purchase_order, create_purchase_order, create_supplier_comparison,
    mark_purchase_order_sent, register_supplier_offer,
)


def demo_id(key):
    return uuid5(NAMESPACE_URL, f"aquakip/procurement/demo/{key}")


class Command(BaseCommand):
    help = "Create a linked procurement demo dataset without duplicating existing demo records."

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate(timezone=ZoneInfo("Asia/Almaty"))
        suppliers = []
        for index, (name, rating) in enumerate((
            ("Aqua Supply", "4.750"), ("Pump Systems KZ", "4.620"), ("HydroTech", "4.400"),
        ), start=1):
            supplier, _ = Supplier.objects.get_or_create(
                id=demo_id(f"supplier-{index}"),
                defaults={
                    "company_id": demo_id("company"), "code": f"DEMO-SUP-{index:03}",
                    "name": name, "supplier_type": "equipment",
                    "status": Supplier.Status.ACTIVE, "rating": Decimal(rating),
                    "email": f"sales{index}@example.com", "phone": f"+7 727 555 010{index}",
                },
            )
            suppliers.append(supplier)

        requests, rfqs = [], []
        for index in (1, 2):
            request, _ = PurchaseRequest.objects.get_or_create(
                id=demo_id(f"request-{index}"),
                defaults={
                    "company_id": demo_id("company"), "project_id": demo_id(f"project-{index}"),
                    "specification_version_id": demo_id(f"specification-{index}"),
                    "requested_by": demo_id("requester"), "status": PurchaseRequest.Status.SUBMITTED,
                    "comment": "Pump station equipment" if index == 1 else "Water treatment equipment",
                },
            )
            for position, (description, quantity, budget) in enumerate((
                ("Circulation pump", "2.000000", "185000.0000"),
                ("Control panel", "1.000000", "95000.0000"),
            ), start=1):
                PurchaseRequestItem.objects.get_or_create(
                    id=demo_id(f"request-{index}-item-{position}"),
                    defaults={
                        "purchase_request": request, "position": position,
                        "description": description, "nomenclature_id": demo_id(f"nomenclature-{position}"),
                        "unit_id": demo_id("unit-piece"), "quantity": Decimal(quantity),
                        "required_by": today + timedelta(days=14), "budget_price": Decimal(budget),
                        "estimated_unit_price": Decimal(budget), "route_type": "standard",
                    },
                )
            rfq, _ = RFQ.objects.get_or_create(
                id=demo_id(f"rfq-{index}"),
                defaults={
                    "purchase_request": request, "status": RFQ.Status.OPEN,
                    "deadline_at": timezone.now() + timedelta(days=5 + index),
                },
            )
            for supplier in suppliers:
                RFQRecipient.objects.get_or_create(
                    rfq=rfq, supplier=supplier,
                    defaults={"channel": RFQRecipient.Channel.EMAIL,
                              "delivery_status": RFQRecipient.DeliveryStatus.PENDING},
                )
            requests.append(request)
            rfqs.append(rfq)

        offers = []
        for index, supplier in enumerate(suppliers, start=1):
            document_id = demo_id(f"offer-document-{index}")
            offer = SupplierOffer.objects.filter(
                rfq=rfqs[0], supplier=supplier, source_document_id=document_id,
            ).first()
            if offer is None:
                offer = register_supplier_offer(
                    rfqs[0], supplier,
                    {"currency_code": "KZT", "offer_date": today,
                     "valid_until": today + timedelta(days=30), "source_document_id": document_id},
                    [{
                        "request_item": item, "nomenclature_id": item.nomenclature_id,
                        "quantity": item.quantity,
                        "unit_price": item.budget_price + Decimal(index * 1000),
                        "availability": SupplierOfferItem.Availability.IN_STOCK,
                        "delivery_days": 5 + index,
                        "technical_match": SupplierOfferItem.TechnicalMatch.MATCH,
                    } for item in requests[0].items.all()],
                )
            offers.append(offer)

        if not SupplierComparison.objects.filter(purchase_request=requests[0], version=1).exists():
            create_supplier_comparison(
                requests[0], version=1,
                criteria={"price": "Unit prices", "delivery": "Delivery days", "technical_match": "Match"},
                result={
                    "selected_offer_id": str(offers[0].id),
                    "selected_supplier_id": str(suppliers[0].id),
                    "offers": [{
                        "supplier_id": str(offer.supplier_id), "offer_id": str(offer.id),
                        "currency_code": offer.currency_code,
                        "items": [{"nomenclature_id": str(item.nomenclature_id),
                                   "quantity": str(item.quantity), "unit_price": str(item.unit_price),
                                   "delivery_days": item.delivery_days, "availability": item.availability,
                                   "technical_match": item.technical_match} for item in offer.items.all()],
                    } for offer in offers],
                },
            )

        orders = []
        for index, target in enumerate((
            PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.APPROVED, PurchaseOrder.Status.SENT,
        ), start=1):
            number = f"DEMO-PO-{index:03}"
            order = PurchaseOrder.objects.filter(project_id=requests[0].project_id, number=number).first()
            if order is None:
                offer = offers[index - 1]
                order = create_purchase_order(
                    project_id=requests[0].project_id, supplier=offer.supplier,
                    number=number, currency_code=offer.currency_code,
                    items=[{"nomenclature_id": item.nomenclature_id,
                            "quantity": item.quantity, "unit_price": item.unit_price,
                            "expected_date": today + timedelta(days=item.delivery_days or 7)}
                           for item in offer.items.all()],
                )
                if target in (PurchaseOrder.Status.APPROVED, PurchaseOrder.Status.SENT):
                    order = approve_purchase_order(order)
                if target == PurchaseOrder.Status.SENT:
                    order = mark_purchase_order_sent(order)
            orders.append(order)

        ExpectedDelivery.objects.get_or_create(
            id=demo_id("delivery-upcoming"),
            defaults={"purchase_order": orders[2], "planned_date": today + timedelta(days=7),
                      "status": ExpectedDelivery.Status.IN_TRANSIT,
                      "tracking": {"carrier": "Aqua Logistics", "tracking_number": "AK-DEMO-001"}},
        )
        ExpectedDelivery.objects.get_or_create(
            id=demo_id("delivery-early"),
            defaults={"purchase_order": orders[2], "planned_date": today,
                      "actual_date": today - timedelta(days=1), "early_delivery_reason": "Earlier delivery window agreed",
                      "status": ExpectedDelivery.Status.DELIVERED, "tracking": {"received_by": "Demo warehouse"}},
        )
        AlternativeRequest.objects.get_or_create(
            id=demo_id("alternative"),
            defaults={"project_id": requests[0].project_id, "request_item": requests[0].items.first(),
                      "original_nomenclature_id": requests[0].items.first().nomenclature_id,
                      "alternative_nomenclature_id": demo_id("alternative-nomenclature"),
                      "status": AlternativeRequest.Status.REQUESTED},
        )
        self.stdout.write(self.style.SUCCESS(
            "Demo ready: 3 suppliers, 2 requests, 2 RFQs, 6 recipients, 3 offers, "
            "1 comparison, 3 orders, 2 deliveries, 1 alternative. Existing demo records preserved."
        ))
