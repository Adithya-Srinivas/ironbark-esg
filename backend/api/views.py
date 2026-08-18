from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Sum, Count
from ingestion.models import (
    FuelDelivery, ElectricityReading, Incident,
    EmissionFactor, DataQualityIssue
)
from collections import defaultdict


@api_view(['GET'])
def monthly_emissions(request):
    # Get emission factors
    diesel_factor = EmissionFactor.objects.get(activity__icontains='Diesel').kg_co2e_per_unit
    petrol_factor = EmissionFactor.objects.get(activity__icontains='Petrol').kg_co2e_per_unit
    elec_factor = EmissionFactor.objects.get(scope=2).kg_co2e_per_unit

    # Scope 1 — fuel deliveries (exclude credit notes)
    deliveries = FuelDelivery.objects.filter(exclude_from_emissions=False)
    scope1_by_month = defaultdict(float)

    for d in deliveries:
        key = d.delivery_date.strftime('%Y-%m')
        factor = diesel_factor if d.fuel_type == 'Diesel' else petrol_factor
        scope1_by_month[key] += d.quantity_litres * factor

    # Scope 2 — electricity
    readings = ElectricityReading.objects.all()
    scope2_by_month = defaultdict(float)

    for r in readings:
        key = r.period.strftime('%Y-%m')
        scope2_by_month[key] += r.consumption_kwh * elec_factor

    # Merge into sorted list
    all_months = sorted(set(list(scope1_by_month.keys()) + list(scope2_by_month.keys())))
    result = []
    for month in all_months:
        result.append({
            'month': month,
            'scope1_kg_co2e': round(scope1_by_month.get(month, 0), 2),
            'scope2_kg_co2e': round(scope2_by_month.get(month, 0), 2),
            'total_kg_co2e': round(scope1_by_month.get(month, 0) + scope2_by_month.get(month, 0), 2),
        })

    return Response(result)


@api_view(['GET'])
def incident_summary(request):
    incidents = Incident.objects.all().values(
        'incident_id', 'incident_date', 'location',
        'type_code', 'severity', 'description',
        'ai_category', 'ai_psychosocial_flag',
        'ai_severity_consistent', 'ai_severity_inconsistency_reason',
        'ai_processed'
    )

    # Monthly trend
    monthly = defaultdict(int)
    for inc in incidents:
        key = inc['incident_date'].strftime('%Y-%m')
        monthly[key] += 1

    monthly_trend = [{'month': k, 'count': v} for k, v in sorted(monthly.items())]

    # By type
    by_type = list(
        Incident.objects.values('type_code').annotate(count=Count('id'))
    )

    # By severity
    by_severity = list(
        Incident.objects.values('severity').annotate(count=Count('id'))
    )

    # Psychosocial flags
    psychosocial = list(
        Incident.objects.filter(ai_psychosocial_flag=True).values(
            'incident_id', 'incident_date', 'description',
            'ai_category', 'ai_severity_inconsistency_reason'
        )
    )

    # Severity inconsistencies
    inconsistent = list(
        Incident.objects.filter(ai_severity_consistent=False).values(
            'incident_id', 'incident_date', 'severity',
            'description', 'ai_severity_inconsistency_reason'
        )
    )

    return Response({
        'monthly_trend': monthly_trend,
        'by_type': by_type,
        'by_severity': by_severity,
        'psychosocial_flags': psychosocial,
        'severity_inconsistencies': inconsistent,
    })


@api_view(['GET'])
def data_quality(request):
    issues = list(DataQualityIssue.objects.values(
        'source_file', 'row_number', 'invoice_or_id',
        'field_name', 'issue_type', 'original_value',
        'action_taken', 'notes'
    ))

    # Summary by file
    by_file = defaultdict(int)
    by_action = defaultdict(int)
    for issue in issues:
        by_file[issue['source_file']] += 1
        by_action[issue['action_taken']] += 1

    return Response({
        'total_issues': len(issues),
        'by_file': dict(by_file),
        'by_action': dict(by_action),
        'issues': issues,
    })