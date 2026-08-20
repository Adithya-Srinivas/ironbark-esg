# Ironbark Ridge Resources ESG Compliance Dashboard


## Write-up

## How to Run Everything

### Option 1: Docker (recommended)

Prerequisites: Docker Desktop installed and running.

```bash
git clone <your-repo-url>
cd ironbark-esg
cp backend/.env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
docker compose up --build
```

Then in a separate terminal, load the data:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py ingest_data
docker compose exec backend python manage.py run_ai_classification
```

Dashboard: http://localhost:3000  
API: http://localhost:8000/api/

### Option 2: Local

**Backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your database credentials and ANTHROPIC_API_KEY
python manage.py migrate
python manage.py ingest_data
python manage.py run_ai_classification
python manage.py runserver
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

Dashboard: http://localhost:5173

**Running tests**
```bash
cd backend
python manage.py test ingestion api
```

## Technology Choices

The challenge suggested Node.js for the backend and Vue for the frontend. I chose Django and React instead and I want to be transparent about why.

Django is the backend framework I am most productive in. It has a first class ORM that made the data modelling and ingestion pipeline straightforward, built in admin for inspecting loaded data during development, and PostgreSQL support out of the box. I am comfortable with Node.js and could have used it, but I would have spent more time debugging framework specific behaviour and less time on the actual problem which was data quality, emissions logic, and the AI layer. I chose the tool that let me move with confidence.

Same reasoning for React over Vue. I know React well enough to focus on what the dashboard needs to show rather than on framework syntax. Vue is not fundamentally different and I am comfortable picking it up, but switching frameworks mid challenge would have added unnecessary debugging time for no benefit to the end result.

I want to be clear that I am not opposed to Node.js or Vue. If this role requires them day to day I will learn them. I have done the same with every new tool I have picked up. But for a take home where the output is what matters, I backed my strengths.

## Data Problems I Found and What I Did About Each

### fuel_deliveries.csv

**Duplicate invoices.** Six invoice numbers appeared twice in the file: INV-40292, INV-40497, INV-40962, INV-40357, INV-40266, INV-40349, INV-40715. I skipped the second occurrence on load using get_or_create and logged each duplicate to the data quality report.

**Quantities in kilolitres instead of litres.** Several invoices recorded quantity in kL such as INV-40373 at 84.03 kL, INV-40677 at 64.43 kL, and INV-40210 at 52.15 kL. The values were clearly orders of magnitude smaller than other deliveries. I multiplied each by 1000, stored as litres, and flagged as fixed with notes. If not caught, emissions would have been understated by a factor of 1000 for those deliveries.

**Credit note (negative quantity).** INV-41777 recorded negative 12,500 L at negative $23,375. Both quantity and cost were negative and the price per litre ($1.87/L) was internally consistent with other deliveries, indicating a legitimate credit note rather than a data entry error. I stored it with is_credit_note=True and exclude_from_emissions=True, excluding it from all emissions calculations.

**Month only dates.** Some invoices had dates like "Jan-25" or "Aug-25" with no specific day. I stored these as the first of the month (e.g. 2025-01-01) with date_precision="month" to signal reduced precision. Emissions grouping is by month so this does not affect calculations.

**Missing costs.** A small number of invoices had no cost recorded. I stored these as null and flagged them in the data quality report.

### electricity_meter_readings.csv

**MTR-07 unit error.** The Ventilation and Dewatering meter (MTR-07) recorded around 252,000 kWh per month from January to September 2025, then dropped to around 260 kWh from October 2025 onwards which is a factor of approximately 1000. The most likely explanation is that whoever entered the data switched from kWh to MWh without updating the unit column since 260 MWh equals 260,000 kWh which is consistent with prior months. I flagged rather than auto corrected because silently multiplying by 1000 would inflate emissions figures if the assumption turned out to be wrong. Logged as requiring manual verification.

**March 2026 consumption drop.** All six meters recorded approximately one third of their normal consumption in March 2026. Cross referencing with the incident register, INC-2026-131 explains this: a regional substation failure caused site wide grid power loss for approximately three weeks with operations running on backup diesel generators. I flagged this with a note linking to INC-2026-131 and retained the data because this is a real operational event, not a data error.

**Missing MTR-06.** Meters run MTR-01 through MTR-07 with no MTR-06 present anywhere in the dataset. I logged this as a gap. It could indicate a decommissioned meter or a missing file.

### incident_register.csv

**Duplicate incident IDs.** INC-2025-011 appeared twice with different dates and descriptions, a VEH incident on 02/06/2025 and an ENV incident on 19/06/2025. I retained both records and flagged the duplicate ID in the data quality report.

**Mixed severity formats.** Some incidents recorded severity as integers (1, 2, 3) and others as text (Low, Medium, High). I normalised all to integers where Low=1, Medium=2, High=3. Non parseable values were stored as null rather than rejected so no incident records were lost.

**Severity values inconsistent with descriptions.** INC-2025-118 recorded a fractured forearm requiring surgery at Mater Hospital as severity 1 (Low). INC-2025-141 recorded lacerated fingers requiring sutures and an LTI as severity 1. These are clearly understated. I stored them as recorded because I do not override source data, but the AI classification layer subsequently flagged both as severity inconsistencies.

### suppliers.csv

**Duplicate suppliers by ABN.** Ironline Fuel Distributors appeared twice under slightly different names (Pty Ltd vs P/L) with the same ABN 63 004 085 616. Blackwood Heavy Maintenance appeared twice with a spelling variation (Maintanence) and the same ABN. I linked duplicates via a duplicate_of foreign key rather than merging them, preserving both spend records while making the relationship explicit.

**Missing ABNs.** SafeGuard PPE Supplies and one Ironline entry had no ABN recorded. I stored these as null and flagged them.

**Invalid ABN.** TerraForm Rehabilitation Co had ABN "5501822" which is only 7 digits. A valid Australian ABN is always 11 digits. I stored it as is and flagged it as invalid format.

## One Insight I Was Not Asked to Find

**The March 2026 grid outage tells a story across three datasets.**

In March 2026, electricity consumption across all meters dropped to roughly one third of normal. In isolation this looks like a data problem. But cross referencing with the incident register reveals INC-2026-131: a regional substation failure that knocked out grid supply for approximately three weeks with the site running on backup diesel generators throughout.

This single infrastructure event shows up across three datasets at the same time. All meters show dramatically reduced grid consumption for March 2026. Diesel deliveries spike in the surrounding weeks as generators run continuously. And INC-2026-134 records multiple crews reporting fatigue from extended shifts covering generator operations and manual restarts.

This is the kind of cross dataset correlation that raw data cannot surface on its own. A sustainability lead looking at the electricity chart alone would flag it as a data error. With incident context, it becomes a reportable operational event with measurable emissions impact and a documented human health consequence.

## How I Used AI Tools

I used Claude throughout the build for code generation, for explaining unfamiliar concepts like emission factor methodology, and NGER reporting context, and for drafting the AI classification logic itself.

The most instructive moment was reviewing the AI classification output for the incident register. The model (claude-haiku-4-5) flagged 5 incidents as psychosocial hazards. Four of them were correct which were verbal abuse from a supervisor, burnout from sustained overtime, retaliation after raising a safety concern, and fatigue from extended shift coverage. The fifth, INC-2026-131, was a false positive. The description reads:

"Regional substation failure caused loss of grid supply to site. Backup diesel generators run continuously for approximately three weeks while repairs completed."

There are no people in that description. No stress, no mental health angle. The model appeared to pattern match on the operational intensity of the language and misclassified an infrastructure incident as a psychosocial one.

I caught this by reading every AI output against the original source record, not spot checking but reading all of them. The false positive was kept in the system rather than silently removed because in compliance software the audit trail matters. The limitation is documented here so a reviewer knows to treat INC-2026-131's psychosocial flag with scepticism.

This reinforced the principle the challenge itself states: hallucinated findings are worse than no findings. AI classification is a first pass that surfaces candidates for human review, not a final determination.

## What I Would Build Next

**Natural language query interface.** 

The dashboard currently shows fixed views and the sustainability lead can only see what I decided to show them. A natural language interface would let them type a question in plain English like "how many vehicle incidents happened in the North Pit this year?" and get an answer back without writing any code or SQL. Behind the scenes, Claude would read the question, figure out what database query is needed, run it against PostgreSQL, and return the answer with a reference back to the exact records it used. This is achievable with function calling where you give Claude a defined set of tools it can use to query specific tables, and it decides which tool to call based on the question. It aligns directly with what ESGAgent.ai is building as a product.