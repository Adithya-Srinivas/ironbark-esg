from django.db import models


class FuelDelivery(models.Model):
    invoice_number = models.CharField(max_length=20, unique=True)
    delivery_date = models.DateField()
    date_precision = models.CharField(
        max_length=10,
        choices=[('day', 'Day'), ('month', 'Month')],
        default='day'
    )
    fuel_type = models.CharField(max_length=20)
    quantity_litres = models.FloatField()
    cost_aud = models.FloatField(null=True, blank=True)
    site_area = models.CharField(max_length=50)
    is_credit_note = models.BooleanField(default=False)
    exclude_from_emissions = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = 'Fuel Deliveries'

    def __str__(self):
        return f"{self.invoice_number} - {self.delivery_date}"


class ElectricityReading(models.Model):
    meter_id = models.CharField(max_length=10)
    meter_description = models.CharField(max_length=100)
    period = models.DateField()
    consumption_kwh = models.FloatField()
    unit_corrected = models.BooleanField(default=False)

    class Meta:
        unique_together = ('meter_id', 'period')

    def __str__(self):
        return f"{self.meter_id} - {self.period}"


class Incident(models.Model):
    SEVERITY_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
    ]

    incident_id = models.CharField(max_length=20)
    incident_date = models.DateField()
    location = models.CharField(max_length=50)
    type_code = models.CharField(max_length=10)
    severity = models.IntegerField(null=True, blank=True, choices=SEVERITY_CHOICES)
    description = models.TextField()

    # AI-populated fields — null until you run the AI command
    ai_category = models.CharField(max_length=50, null=True, blank=True)
    ai_psychosocial_flag = models.BooleanField(null=True, blank=True)
    ai_severity_consistent = models.BooleanField(null=True, blank=True)
    ai_severity_inconsistency_reason = models.CharField(
        max_length=500, null=True, blank=True
    )
    ai_processed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.incident_id} - {self.incident_date}"


class Supplier(models.Model):
    name = models.CharField(max_length=100)
    abn = models.CharField(max_length=20, null=True, blank=True)
    category = models.CharField(max_length=100)
    fy_spend_aud = models.FloatField()
    duplicate_of = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='duplicates'
    )

    def __str__(self):
        return self.name


class EmissionFactor(models.Model):
    activity = models.CharField(max_length=100)
    scope = models.IntegerField()
    unit = models.CharField(max_length=10)
    kg_co2e_per_unit = models.FloatField()
    source = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.activity} (Scope {self.scope})"


class DataQualityIssue(models.Model):
    ACTION_CHOICES = [
        ('fixed', 'Fixed'),
        ('flagged', 'Flagged'),
        ('rejected', 'Rejected'),
    ]

    source_file = models.CharField(max_length=50)
    row_number = models.IntegerField(null=True, blank=True)
    invoice_or_id = models.CharField(max_length=50, null=True, blank=True)
    field_name = models.CharField(max_length=50, null=True, blank=True)
    issue_type = models.CharField(max_length=50)
    original_value = models.TextField(null=True, blank=True)
    action_taken = models.CharField(max_length=10, choices=ACTION_CHOICES)
    notes = models.TextField()

    def __str__(self):
        return f"{self.source_file} - {self.issue_type}"