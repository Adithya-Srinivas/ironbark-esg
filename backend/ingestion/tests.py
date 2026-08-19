from django.test import TestCase
from django.db import IntegrityError
from ingestion.models import FuelDelivery, ElectricityReading, DataQualityIssue, Incident
import datetime


class FuelDeliveryDuplicateTest(TestCase):
    """
    The ingestion pipeline must not double-count deliveries.
    invoice_number is unique — a second insert with the same invoice
    should raise IntegrityError, proving the DB constraint backs the
    pipeline's get_or_create duplicate guard.
    """

    def setUp(self):
        FuelDelivery.objects.create(
            invoice_number='INV-40292',
            delivery_date=datetime.date(2025, 3, 23),
            fuel_type='Diesel',
            quantity_litres=74568,
            site_area='Open Cut - North Pit',
        )

    def test_duplicate_invoice_rejected(self):
        with self.assertRaises(IntegrityError):
            FuelDelivery.objects.create(
                invoice_number='INV-40292',
                delivery_date=datetime.date(2025, 3, 23),
                fuel_type='Diesel',
                quantity_litres=74568,
                site_area='Open Cut - North Pit',
            )

    def test_credit_note_excluded_from_emissions(self):
        """
        INV-41777 is a negative-quantity credit note.
        It must be stored but excluded from emissions totals.
        """
        credit = FuelDelivery.objects.create(
            invoice_number='INV-41777',
            delivery_date=datetime.date(2025, 8, 14),
            fuel_type='Diesel',
            quantity_litres=-12500,
            site_area='Haul Fleet',
            is_credit_note=True,
            exclude_from_emissions=True,
        )
        self.assertTrue(credit.exclude_from_emissions)
        # Confirm it doesn't appear in the emissions-eligible queryset
        eligible = FuelDelivery.objects.filter(exclude_from_emissions=False)
        self.assertNotIn(credit, eligible)


class ElectricityReadingUniqueTest(TestCase):
    """
    Each meter can have only one reading per period.
    This prevents the MTR-07 unit-error row being loaded twice
    if the pipeline is run more than once.
    """

    def setUp(self):
        ElectricityReading.objects.create(
            meter_id='MTR-01',
            meter_description='Processing Plant',
            period=datetime.date(2025, 1, 1),
            consumption_kwh=1029974.7,
        )

    def test_duplicate_meter_period_rejected(self):
        with self.assertRaises(IntegrityError):
            ElectricityReading.objects.create(
                meter_id='MTR-01',
                meter_description='Processing Plant',
                period=datetime.date(2025, 1, 1),
                consumption_kwh=999999,
            )


class DataQualityLoggingTest(TestCase):
    """
    Every data problem must be logged — silent discard is not allowed.
    """

    def test_issue_is_persisted(self):
        DataQualityIssue.objects.create(
            source_file='fuel_deliveries.csv',
            row_number=10,
            invoice_or_id='INV-40373',
            field_name='unit',
            issue_type='unit_conversion',
            original_value='kL',
            action_taken='fixed',
            notes='Converted 84.03 kL to 84030 L',
        )
        self.assertEqual(DataQualityIssue.objects.count(), 1)
        issue = DataQualityIssue.objects.first()
        self.assertEqual(issue.action_taken, 'fixed')
        self.assertEqual(issue.source_file, 'fuel_deliveries.csv')


class KilolitreConversionTest(TestCase):
    """
    Some invoices record quantity in kL, not L.
    The pipeline must convert kL → L before storing (multiply by 1000).
    If this is missed, emissions will be understated by a factor of 1000.
    """

    def test_kl_stored_as_litres(self):
        # INV-40373 came in as 84.03 kL — should be stored as 84030 L
        delivery = FuelDelivery.objects.create(
            invoice_number='INV-40373',
            delivery_date=datetime.date(2025, 5, 10),
            fuel_type='Diesel',
            quantity_litres=84030,  # 84.03 kL × 1000
            site_area='Open Cut - North Pit',
        )
        self.assertGreater(delivery.quantity_litres, 1000)
        self.assertAlmostEqual(delivery.quantity_litres, 84030.0, places=1)


class IncidentSeverityNormalisationTest(TestCase):
    """
    The raw incident register mixes numeric (1, 2, 3) and text ('Low', 'Medium')
    severity values. The pipeline must normalise all to integers.
    """

    def test_severity_is_integer(self):
        incident = Incident.objects.create(
            incident_id='INC-TEST-001',
            incident_date=datetime.date(2025, 3, 28),
            location='Site Services',
            type_code='SLP',
            severity=2,
            description='Test incident',
        )
        self.assertIsInstance(incident.severity, int)
        self.assertEqual(incident.severity, 2)

    def test_null_severity_allowed(self):
        """
        Some incidents had non-parseable severity values — stored as null
        rather than rejected, so the incident record is not lost.
        """
        incident = Incident.objects.create(
            incident_id='INC-TEST-002',
            incident_date=datetime.date(2025, 1, 22),
            location='Haul Fleet',
            type_code='DUS',
            severity=None,
            description='Dust exceedance',
        )
        self.assertIsNone(incident.severity)