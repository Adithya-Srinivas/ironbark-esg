import json
import anthropic
from django.core.management.base import BaseCommand
from ingestion.models import Incident


class Command(BaseCommand):
    help = 'Classify incidents using Claude AI'

    def handle(self, *args, **kwargs):
        client = anthropic.Anthropic()

        incidents = Incident.objects.filter(ai_processed=False)
        total = incidents.count()
        self.stdout.write(f'Processing {total} incidents...')

        for i, incident in enumerate(incidents, start=1):
            self.stdout.write(f'  [{i}/{total}] {incident.incident_id}...')

            try:
                response = client.messages.create(
                    model='claude-haiku-4-5',
                    max_tokens=500,
                    system="""You are a workplace safety classifier for an Australian mine.
                Your job is to classify incident reports accurately and identify hidden risks.
                Always return ONLY valid JSON. No explanation, no markdown, no code blocks.""",
                    messages=[{
                        'role': 'user',
                        'content': f"""Classify this incident:

                Incident ID: {incident.incident_id}
                Location: {incident.location}
                Type Code: {incident.type_code}
                Recorded Severity: {incident.severity} (1=Low, 2=Medium, 3=High)
                Description: {incident.description}

                Return this exact JSON structure:
                {{
                    "category": "one of: Physical Injury, Environmental, Equipment, Vehicle, Dust/Air Quality, Psychosocial, Electrical, Other",
                    "psychosocial_flag": true or false,
                    "psychosocial_reason": "brief reason if true, else null",
                    "severity_consistent": true or false,
                    "severity_inconsistency_reason": "brief reason if inconsistent, else null"
                    }}

                Rules:
                - psychosocial_flag = true if description mentions bullying, harassment, verbal abuse, exclusion, overwork, fatigue from management decisions, stress, anxiety, poor sleep, or interpersonal conflict
                - severity_consistent = false if the description clearly does not match the recorded severity (e.g. hospital transport logged as Low, or minor near-miss logged as High)"""
                    }]
                )

                raw = response.content[0].text.strip()

                # Strip markdown code blocks if Claude returns them
                if raw.startswith('```'):
                    raw = raw.split('```')[1]
                    if raw.startswith('json'):
                        raw = raw[4:]
                    raw = raw.strip()

                result = json.loads(raw)

                incident.ai_category = result.get('category', 'Other')
                incident.ai_psychosocial_flag = result.get('psychosocial_flag', False)
                incident.ai_severity_consistent = result.get('severity_consistent', True)
                incident.ai_severity_inconsistency_reason = result.get('severity_inconsistency_reason')
                incident.ai_processed = True
                incident.save()

                self.stdout.write(
                    f'    category={incident.ai_category} '
                    f'psychosocial={incident.ai_psychosocial_flag} '
                    f'consistent={incident.ai_severity_consistent}'
                )

            except json.JSONDecodeError as e:
                self.stdout.write(self.style.WARNING(
                    f'    JSON parse error for {incident.incident_id}: {e}'
                ))
                self.stdout.write(f'    Raw response: {raw}')

            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'    Error for {incident.incident_id}: {e}'
                ))

        processed = Incident.objects.filter(ai_processed=True).count()
        self.stdout.write(self.style.SUCCESS(f'Done. {processed} incidents classified.'))