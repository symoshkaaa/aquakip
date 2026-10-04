# Generated manually for the initial procurement domain models.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Supplier",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("code", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("tax_identifier", models.CharField(blank=True, max_length=64)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=64)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "procurement_supplier",
                "ordering": ("name",),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("code",),
                        name="uniq_supplier_code",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="SupplierAgreement",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("agreement_number", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("active", "Active"),
                            ("suspended", "Suspended"),
                            ("expired", "Expired"),
                            ("terminated", "Terminated"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("currency", models.CharField(default="KZT", max_length=3)),
                (
                    "amount_limit",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=20,
                        null=True,
                    ),
                ),
                ("valid_from", models.DateField()),
                ("valid_to", models.DateField(blank=True, null=True)),
                ("payment_terms", models.TextField(blank=True)),
                (
                    "supplier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="agreements",
                        to="procurement.supplier",
                    ),
                ),
            ],
            options={
                "db_table": "procurement_supplier_agreement",
                "ordering": ("supplier__name", "agreement_number"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("supplier", "agreement_number"),
                        name="uniq_supplier_agreement_number",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(("valid_to__isnull", True))
                            | models.Q(("valid_to__gte", models.F("valid_from")))
                        ),
                        name="chk_supplier_agreement_valid_dates",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(("amount_limit__isnull", True))
                            | models.Q(("amount_limit__gte", 0))
                        ),
                        name="chk_supplier_agreement_amount_limit_non_negative",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PurchaseRequest",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("project_id", models.UUIDField()),
                ("specification_version_id", models.UUIDField()),
                ("requested_by", models.UUIDField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("submitted", "Submitted"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("cancelled", "Cancelled"),
                            ("ordered", "Ordered"),
                        ],
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("currency", models.CharField(default="KZT", max_length=3)),
                ("required_at", models.DateTimeField(blank=True, null=True)),
                ("comment", models.TextField(blank=True)),
                (
                    "supplier_agreement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="purchase_requests",
                        to="procurement.supplieragreement",
                    ),
                ),
            ],
            options={
                "db_table": "procurement_purchase_request",
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="PurchaseRequestItem",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("position", models.PositiveIntegerField()),
                ("nomenclature_id", models.UUIDField()),
                ("unit_id", models.UUIDField()),
                ("description", models.CharField(blank=True, max_length=512)),
                (
                    "quantity",
                    models.DecimalField(decimal_places=6, max_digits=20),
                ),
                (
                    "estimated_unit_price",
                    models.DecimalField(decimal_places=4, max_digits=20),
                ),
                (
                    "purchase_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="procurement.purchaserequest",
                    ),
                ),
            ],
            options={
                "db_table": "procurement_purchase_request_item",
                "ordering": ("purchase_request", "position"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("purchase_request", "position"),
                        name="uniq_purchase_request_item_position",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("quantity__gt", 0)),
                        name="chk_purchase_request_item_quantity_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("estimated_unit_price__gte", 0)),
                        name=(
                            "chk_purchase_request_item_estimated_unit_price_"
                            "non_negative"
                        ),
                    ),
                ],
            },
        ),
    ]
