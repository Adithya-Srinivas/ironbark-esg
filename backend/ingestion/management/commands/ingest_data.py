import csv
import os
from datetime import datetime, date
from django.core.management.base import BaseCommand
from ingestion.models import (
    FuelDelivery, ElectricityReading, Incident,
    Supplier, EmissionFactor, DataQualityIssue
)


class Command(BaseCommand):
    help = 'Ingest all CSV files into the database'

    def handle(self, *args, **kwargs):
        # Clear existing data so we can re-run safely
        FuelDelivery.objects.all().delete()
        ElectricityReading.objects.all().delete()
        Incident.objects.all().delete()
        Supplier.objects.all().delete()
        EmissionFactor.objects.all().delete()
        DataQualityIssue.objects.all().delete()

        self.stdout.write('Starting ingestion...')
        self.ingest_emission_factors()
        self.ingest_fuel_deliveries()
        self.ingest_electricity()
        self.ingest_incidents()
        self.ingest_suppliers()
        self.stdout.write(self.style.SUCCESS('Ingestion complete.'))

    def log_issue(self, source_file, row_number, invoice_or_id,
                  field_name, issue_type, original_value, action_taken, notes):
        DataQualityIssue.objects.create(
            source_file=source_file,
            row_number=row_number,
            invoice_or_id=invoice_or_id,
            field_name=field_name,
            issue_type=issue_type,
            original_value=str(original_value),
            action_taken=action_taken,
            notes=notes,
        )

    def parse_date(self, date_str):
        date_str = date_str.strip()
        # Try ISO format: 2025-12-19
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date(), 'day'
        except ValueError:
            pass
        # Try DD/MM/YYYY: 21/05/2026
        try:
            return datetime.strptime(date_str, '%d/%m/%Y').date(), 'day'
        except ValueError:
            pass
        # Try Month-YY: Oct-25
        try:
            d = datetime.strptime(date_str, '%b-%y')
            return date(d.year, d.month, 1), 'month'
        except ValueError:
            pass
        raise ValueError(f'Cannot parse date: {date_str}')

    def parse_cost(self, cost_str):
        cost_str = cost_str.strip().replace('$', '').replace(',', '')
        if not cost_str:
            return None
        return float(cost_str)

    def parse_quantity(self, qty_str):
        return float(qty_str.strip().replace(',', ''))

    # ----------------------------------------------------------------
    # EMISSION FACTORS
    # ----------------------------------------------------------------
    def ingest_emission_factors(self):
        self.stdout.write('Ingesting emission factors...')
        with open('data/emission_factors.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                EmissionFactor.objects.create(
                    activity=row['activity'].strip(),
                    scope=int(row['scope']),
                    unit=row['unit'].strip(),
                    kg_co2e_per_unit=float(row['kg_co2e_per_unit']),
                    source=row['source'].strip(),
                )
        self.stdout.write('  Emission factors done.')

    # ----------------------------------------------------------------
    # FUEL DELIVERIES
    # ----------------------------------------------------------------
    def ingest_fuel_deliveries(self):
        self.stdout.write('Ingesting fuel deliveries...')
        seen_invoices = set()

        with open('data/fuel_deliveries.csv') as f:
            reader = csv.DictReader(f)
            # Strip whitespace from headers
            reader.fieldnames = [h.strip() for h in reader.fieldnames]

            for i, row in enumerate(reader, start=2):
                row = {k.strip(): v.strip() for k, v in row.items()}
                invoice = row.get('Invoice No', '').strip()

                # Check for duplicate invoice
                if invoice in seen_invoices:
                    self.log_issue(
                        'fuel_deliveries.csv', i, invoice,
                        'invoice_number', 'DUPLICATE_INVOICE',
                        invoice, 'rejected',
                        'Exact duplicate invoice number — row skipped.'
                    )
                    continue
                seen_invoices.add(invoice)

                # Parse quantity and unit
                qty = self.parse_quantity(row['Quantity'])
                unit = row['Unit'].lower()

                if unit == 'kl':
                    original_qty = qty
                    qty = qty * 1000
                    self.log_issue(
                        'fuel_deliveries.csv', i, invoice,
                        'quantity', 'UNIT_CONVERTED_KL_TO_L',
                        original_qty, 'fixed',
                        f'Converted {original_qty} kL to {qty} L.'
                    )

                # Check for negative quantity
                is_credit = False
                exclude = False
                if qty < 0:
                    is_credit = True
                    exclude = True
                    self.log_issue(
                        'fuel_deliveries.csv', i, invoice,
                        'quantity', 'NEGATIVE_QUANTITY',
                        qty, 'flagged',
                        'Both quantity and cost are negative with internally '
                        'consistent price per litre. Treated as credit note. '
                        'Excluded from emissions calculation.'
                    )

                # Parse date
                date_str = row['Delivery Date']
                try:
                    delivery_date, precision = self.parse_date(date_str)
                    if precision == 'month':
                        self.log_issue(
                            'fuel_deliveries.csv', i, invoice,
                            'delivery_date', 'MONTH_ONLY_DATE',
                            date_str, 'fixed',
                            'Month-only date normalised to first of month.'
                        )
                except ValueError as e:
                    self.log_issue(
                        'fuel_deliveries.csv', i, invoice,
                        'delivery_date', 'UNPARSEABLE_DATE',
                        date_str, 'rejected', str(e)
                    )
                    continue

                # Parse cost
                cost = self.parse_cost(row.get('Cost (AUD)', ''))

                # Fuel type and site area
                fuel_type = row['Fuel Type']
                site_area = row['Site Area']

                # Flag suspicious diesel to Light Vehicles
                if site_area == 'Light Vehicles' and fuel_type == 'Diesel' and qty > 10000:
                    self.log_issue(
                        'fuel_deliveries.csv', i, invoice,
                        'site_area', 'SUSPICIOUS_DIESEL_TO_LIGHT_VEHICLES',
                        qty, 'flagged',
                        f'{qty}L of diesel delivered to Light Vehicles. '
                        'Light vehicles typically use petrol. Included in '
                        'emissions but flagged for client review.'
                    )

                FuelDelivery.objects.create(
                    invoice_number=invoice,
                    delivery_date=delivery_date,
                    date_precision=precision,
                    fuel_type=fuel_type,
                    quantity_litres=qty,
                    cost_aud=cost,
                    site_area=site_area,
                    is_credit_note=is_credit,
                    exclude_from_emissions=exclude,
                )

        self.stdout.write('  Fuel deliveries done.')

    # ----------------------------------------------------------------
    # ELECTRICITY
    # ----------------------------------------------------------------
    def ingest_electricity(self):
        self.stdout.write('Ingesting electricity readings...')

        with open('data/electricity_meter_readings.csv') as f:
            reader = csv.DictReader(f)

            for i, row in enumerate(reader, start=2):
                row = {k.strip(): v.strip() for k, v in row.items()}
                meter_id = row['meter_id']
                period_str = row['period']
                period = datetime.strptime(period_str, '%Y-%m').date().replace(day=1)
                consumption = float(row['consumption'])
                unit_corrected = False

                # Flag MTR-07 unit error after Oct 2025
                if meter_id == 'MTR-07' and period >= date(2025, 10, 1):
                    if consumption < 10000:
                        original = consumption
                        consumption = consumption * 1000
                        unit_corrected = True
                        self.log_issue(
                            'electricity_meter_readings.csv', i, meter_id,
                            'consumption', 'LIKELY_UNIT_ERROR_MWH_NOT_KWH',
                            original, 'fixed',
                            f'MTR-07 reading of {original} from {period_str} is ~1000x lower '
                            'than prior months. Likely recorded in MWh instead of kWh. '
                            'Multiplied by 1000 to normalise.'
                        )

                # Flag March 2026 site-wide drop
                if period == date(2026, 3, 1):
                    self.log_issue(
                        'electricity_meter_readings.csv', i, meter_id,
                        'consumption', 'MARCH_2026_ANOMALOUS_DROP',
                        consumption, 'flagged',
                        'All meters show ~35% of normal consumption in March 2026. '
                        'Consistent with INC-2026-131: regional substation failure, '
                        'site ran on backup diesel generators for ~3 weeks.'
                    )

                ElectricityReading.objects.create(
                    meter_id=meter_id,
                    meter_description=row['meter_description'],
                    period=period,
                    consumption_kwh=consumption,
                    unit_corrected=unit_corrected,
                )

        # Flag missing MTR-06
        self.log_issue(
            'electricity_meter_readings.csv', None, 'MTR-06',
            'meter_id', 'MISSING_METER',
            'MTR-06', 'flagged',
            'MTR-06 is absent from all 18 months of data. '
            'Meters jump from MTR-05 to MTR-07. Either decommissioned, '
            'never installed, or missing from export.'
        )

        self.stdout.write('  Electricity done.')

    # ----------------------------------------------------------------
    # INCIDENTS
    # ----------------------------------------------------------------
    def ingest_incidents(self):
        self.stdout.write('Ingesting incidents...')
        seen_ids = {}

        SEVERITY_MAP = {
            '1': 1, '2': 2, '3': 3,
            'low': 1, 'medium': 2, 'high': 3,
        }

        with open('data/incident_register.csv') as f:
            reader = csv.DictReader(f)

            for i, row in enumerate(reader, start=2):
                row = {k.strip(): v.strip() for k, v in row.items()}
                incident_id = row['incident_id']

                # Check duplicate IDs
                if incident_id in seen_ids:
                    self.log_issue(
                        'incident_register.csv', i, incident_id,
                        'incident_id', 'DUPLICATE_INCIDENT_ID',
                        incident_id, 'flagged',
                        f'Incident ID {incident_id} used for two different incidents. '
                        'Both records kept but ID conflict must be resolved.'
                    )

                seen_ids[incident_id] = True

                # Parse date
                incident_date = datetime.strptime(row['incident_date'], '%d/%m/%Y').date()

                # Normalise severity
                severity_raw = row['severity'].strip().lower()
                severity = SEVERITY_MAP.get(severity_raw, None)
                if severity is None:
                    self.log_issue(
                        'incident_register.csv', i, incident_id,
                        'severity', 'UNRECOGNISED_SEVERITY',
                        row['severity'], 'flagged',
                        f'Severity value "{row["severity"]}" not recognised.'
                    )

                Incident.objects.create(
                    incident_id=incident_id,
                    incident_date=incident_date,
                    location=row['location'],
                    type_code=row['type_code'],
                    severity=severity,
                    description=row['description'],
                )

        self.stdout.write('  Incidents done.')

    # ----------------------------------------------------------------
    # SUPPLIERS
    # ----------------------------------------------------------------
    def ingest_suppliers(self):
        self.stdout.write('Ingesting suppliers...')
        seen_abns = {}

        with open('data/suppliers.csv') as f:
            reader = csv.DictReader(f)

            for i, row in enumerate(reader, start=2):
                row = {k.strip(): v.strip() for k, v in row.items()}
                name = row['supplier_name']
                abn = row['abn'] if row['abn'] else None
                spend = float(row['fy_spend_aud'])

                # Flag missing ABN
                if not abn:
                    self.log_issue(
                        'suppliers.csv', i, name,
                        'abn', 'MISSING_ABN',
                        '', 'flagged',
                        f'Supplier "{name}" has no ABN recorded.'
                    )

                # Flag invalid ABN (must be 11 digits)
                if abn:
                    abn_digits = abn.replace(' ', '')
                    if not abn_digits.isdigit() or len(abn_digits) != 11:
                        self.log_issue(
                            'suppliers.csv', i, name,
                            'abn', 'INVALID_ABN_FORMAT',
                            abn, 'flagged',
                            f'ABN "{abn}" is not a valid 11-digit Australian ABN.'
                        )

                # Flag duplicate ABN
                if abn and abn in seen_abns:
                    self.log_issue(
                        'suppliers.csv', i, name,
                        'abn', 'DUPLICATE_ABN',
                        abn, 'flagged',
                        f'ABN {abn} already used by "{seen_abns[abn]}". '
                        'Likely the same supplier entered twice with different name spellings.'
                    )

                if abn:
                    seen_abns[abn] = name

                Supplier.objects.create(
                    name=name,
                    abn=abn,
                    category=row['category'],
                    fy_spend_aud=spend,
                )

        self.stdout.write('  Suppliers done.')