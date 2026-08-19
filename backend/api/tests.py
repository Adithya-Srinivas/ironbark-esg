from django.test import TestCase
from ingestion.models import FuelDelivery, ElectricityReading, EmissionFactor, DataQualityIssue, Incident
import datetime


class EmissionsCalculationTest(TestCase):
    """
    Scope 1 = fuel litres × emission factor (2.70 kg CO2e/L for diesel)
    Scope 2 = kWh × emission factor (0.71 kg CO2e/kWh for QLD grid)
    This is the core business logic — if it's wrong, the whole dashboard is wrong.
    """

    def setUp(self):
        EmissionFactor.objects.create(
            activity='Diesel combustion (stationary & transport)',
            scope=1, unit='L', kg_co2e_per_unit=2.70,
            source='Indicative factor for this exercise',
        )
        EmissionFactor.objects.create(
            activity='Petrol (ULP) combustion',
            scope=1, unit='L', kg_co2e_per_unit=2.31,
            source='Indicative factor for this exercise',
        )
        EmissionFactor.objects.create(
            activity='Grid electricity - Queensland',
            scope=2, unit='kWh', kg_co2e_per_unit=0.71,
            source='Indicative factor for this exercise',
        )
        # One diesel delivery in January 2025: 10000 L
        FuelDelivery.objects.create(
            invoice_number='TEST-001',
            delivery_date=datetime.date(2025, 1, 15),
            fuel_type='Diesel',
            quantity_litres=10000,
            site_area='Processing Plant',
            exclude_from_emissions=False,
        )
        # One electricity reading in January 2025: 5000 kWh
        ElectricityReading.objects.create(
            meter_id='MTR-01',
            meter_description='Processing Plant',
            period=datetime.date(2025, 1, 1),
            consumption_kwh=5000,
        )

    def test_scope1_calculation(self):
        response = self.client.get('/api/emissions/monthly/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        jan = next(m for m in data if m['month'] == '2025-01')
        # 10000 L × 2.70 = 27000 kg CO2e
        self.assertAlmostEqual(jan['scope1_kg_co2e'], 27000.0, places=1)

    def test_scope2_calculation(self):
        response = self.client.get('/api/emissions/monthly/')
        data = response.json()
        jan = next(m for m in data if m['month'] == '2025-01')
        # 5000 kWh × 0.71 = 3550 kg CO2e
        self.assertAlmostEqual(jan['scope2_kg_co2e'], 3550.0, places=1)

    def test_credit_note_excluded(self):
        """A credit note must not reduce the emissions total."""
        FuelDelivery.objects.create(
            invoice_number='TEST-CREDIT',
            delivery_date=datetime.date(2025, 1, 20),
            fuel_type='Diesel',
            quantity_litres=-12500,
            site_area='Haul Fleet',
            is_credit_note=True,
            exclude_from_emissions=True,
        )
        response = self.client.get('/api/emissions/monthly/')
        data = response.json()
        jan = next(m for m in data if m['month'] == '2025-01')
        # Should still be 27000 — credit note must not affect the total
        self.assertAlmostEqual(jan['scope1_kg_co2e'], 27000.0, places=1)


class DataQualityEndpointTest(TestCase):
    """
    The data quality report is a key deliverable.
    Test that the endpoint returns the right structure and counts.
    """

    def setUp(self):
        DataQualityIssue.objects.create(
            source_file='fuel_deliveries.csv',
            row_number=10, invoice_or_id='INV-40373',
            field_name='unit', issue_type='unit_conversion',
            original_value='kL', action_taken='fixed',
            notes='Converted kL to L',
        )
        DataQualityIssue.objects.create(
            source_file='fuel_deliveries.csv',
            row_number=123, invoice_or_id='INV-41777',
            field_name='quantity', issue_type='credit_note',
            original_value='-12500', action_taken='flagged',
            notes='Negative quantity treated as credit note',
        )
        DataQualityIssue.objects.create(
            source_file='electricity_meter_readings.csv',
            row_number=61, invoice_or_id='MTR-07',
            field_name='consumption', issue_type='unit_error',
            original_value='277.0', action_taken='flagged',
            notes='Suspected unit error: Oct 2025 onwards ~1000x lower',
        )

    def test_endpoint_returns_200(self):
        response = self.client.get('/api/data-quality/')
        self.assertEqual(response.status_code, 200)

    def test_total_issues_count(self):
        response = self.client.get('/api/data-quality/')
        data = response.json()
        self.assertEqual(data['total_issues'], 3)

    def test_grouped_by_file(self):
        response = self.client.get('/api/data-quality/')
        data = response.json()
        # by_file is a dict: {'fuel_deliveries.csv': 2, ...}
        self.assertEqual(data['by_file']['fuel_deliveries.csv'], 2)
        self.assertEqual(data['by_file']['electricity_meter_readings.csv'], 1)

    def test_grouped_by_action(self):
        response = self.client.get('/api/data-quality/')
        data = response.json()
        # by_action is a dict: {'fixed': 1, 'flagged': 2}
        self.assertEqual(data['by_action']['fixed'], 1)
        self.assertEqual(data['by_action']['flagged'], 2)

class IncidentSummaryEndpointTest(TestCase):
    """
    The incident summary endpoint must return all required keys
    and correctly count psychosocial flags and severity inconsistencies.
    """

    def setUp(self):
        Incident.objects.create(
            incident_id='INC-2026-109',
            incident_date=datetime.date(2026, 2, 3),
            location='Open Cut - South Pit',
            type_code='OTH',
            severity=1,
            description='Crew member reported exclusion from toolbox talks after raising a safety concern.',
            ai_psychosocial_flag=True,
            ai_severity_consistent=False,
            ai_severity_inconsistency_reason='Description suggests high distress; severity 1 appears understated.',
            ai_processed=True,
        )
        Incident.objects.create(
            incident_id='INC-2025-001',
            incident_date=datetime.date(2025, 1, 26),
            location='Open Cut - South Pit',
            type_code='VEH',
            severity=1,
            description='Service truck tyre blowout, controlled stop, no injury.',
            ai_psychosocial_flag=False,
            ai_severity_consistent=True,
            ai_processed=True,
        )

    def test_endpoint_returns_200(self):
        response = self.client.get('/api/incidents/summary/')
        self.assertEqual(response.status_code, 200)

    def test_required_keys_present(self):
        response = self.client.get('/api/incidents/summary/')
        data = response.json()
        for key in ['monthly_trend', 'by_type', 'by_severity', 'psychosocial_flags', 'severity_inconsistencies']:
            self.assertIn(key, data)

    def test_psychosocial_flag_count(self):
        response = self.client.get('/api/incidents/summary/')
        data = response.json()
        self.assertEqual(len(data['psychosocial_flags']), 1)
        self.assertEqual(data['psychosocial_flags'][0]['incident_id'], 'INC-2026-109')

    def test_severity_inconsistency_count(self):
        response = self.client.get('/api/incidents/summary/')
        data = response.json()
        self.assertEqual(len(data['severity_inconsistencies']), 1)