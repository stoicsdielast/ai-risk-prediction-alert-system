# Alert creation and administrator management

This guide describes the current persisted workflows. The operational alert API
and the isolated synthetic analysis API remain separate. The deployment still
uses the V1 model; no inference rules, probabilities or risk tiers were changed.

## Why the simulation buttons were disabled

The location prediction table is rendered in
`frontend/src/components/research/SyntheticReplay.tsx`. Its original condition
was `busy || !info.alerts_enabled || risk not in HIGH/VERY_HIGH`. The action column
was shown only to `MET_ADMIN`. `/api/synthetic/info` supplies `alerts_enabled`
from `SYNTHETIC_DEMO_ENABLED`, which was false in the local configuration.

The click calls `createSyntheticAlert`, then `POST /api/synthetic/admin/alerts`.
The backend checks the current JWT account and MET role, the feature gate, active
registry location, imported weather, hourly timezone-aware timestamp, and model
output. It originally rejected every risk below HIGH as well. Neither a
cooldown nor an existing active operational alert disabled those table buttons.
Duplicate synthetic requests already referred to the same prediction/alert.

## Create an isolated test alert

1. Apply migrations with `cd backend && .venv/bin/python -m alembic upgrade head`.
2. To opt in on a development installation, set `SYNTHETIC_DEMO_ENABLED=true` in
   `backend/.env` and restart the backend. The default remains false. This setting
   was enabled locally as part of this fix; it does not enable operational delivery.
3. Sign in with an active, approved `MET_ADMIN` account and open Historical analysis.
4. Load an hour with complete eligible model output. HIGH/VERY_HIGH rows offer
   **Create simulated alert**. LOW/MODERATE rows offer **Create test alert**.
5. Review the saved pending record in **Simulated alert workflows**. Approve it
   there if needed; approval is still explicit and restricted to administrators.

Low-risk creation sends `test_alert: true` to the existing endpoint and persists
`synthetic_alerts.is_test=true`. Without this explicit opt-in, LOW/MODERATE is
rejected. Missing history or an ongoing simulated flood without a forecast is
still ineligible, even for tests. Existing records are reused without reviving
closed alerts; load a different hour for a new test. Concurrent requests also
converge on one record under PostgreSQL row locking and unique constraints.

These rows retain `source_type=synthetic` and the research-demonstration notice.
They live only in `synthetic_predictions` and `synthetic_alerts`, cannot enter
`/api/alerts/active`, and never enqueue operational notifications. Optional browser
messages in this view are explicitly labelled simulations; LOW/MODERATE tests do
not trigger its HIGH/VERY_HIGH notification rule. The V3 research view remains
read-only and cannot create alerts.

Each disabled action has a visible, accessible reason: operator gate, incomplete
forecast, duplicate record, or an action in progress. Non-admins see an access
explanation. Successful actions and server errors produce feedback.

## Operational lifecycle and history

| Action | Permitted starting state | Persisted result |
| --- | --- | --- |
| Create manual draft | Active location; approved MET admin | PENDING |
| Create from stored model prediction | HIGH/VERY_HIGH genuine prediction; existing cooldown rules | PENDING or existing alert |
| Edit / approve / reject | PENDING | Existing review behaviour |
| Acknowledge | APPROVED and unexpired | Original status retained; first actor and timestamp recorded |
| Resolve with reason | APPROVED | RESOLVED; prior approval and expiry retained |
| Cancel with reason | PENDING or APPROVED | CANCELLED; prior review retained |
| Suppress with reason | PENDING or APPROVED | SUPPRESSED; existing compatibility action retained |
| View expired alerts | Previously approved, past expiry | Remains APPROVED in storage; displayed as Expired in history |

The management page provides **All alerts**, **Active alerts**, and **Alert
history** views. Enter an **Action reason**, then choose **Resolve** or **Cancel
alert** and confirm. The administrator-only detail view retains actor IDs,
acknowledgement/closure timestamps, reason, and previous approval timestamps.
Active and public feeds exclude resolved/cancelled/expired records. The history
view also includes rejected and suppressed records. Acknowledgement does not
withdraw a warning and is idempotent.

The existing creation/list/detail endpoints are reused. New operational actions
are `PATCH /api/admin/alerts/{id}/{acknowledge|resolve|cancel}`. Synthetic actions
use `POST /api/synthetic/admin/alerts/{id}/{acknowledge|resolve|cancel}`, matching
that API's existing approval method. All require current JWT MET authorization.
Synthetic cleanup remains available if the creation feature gate is later off.

Operational AI threshold, sample-data restrictions, configured TTL, severity
escalation and same-prediction deduplication remain in force. Resolved/cancelled
events also participate in the original cooldown window; closing a record is
not a way to create another same-severity event immediately. Existing manual MET
drafts retain their established severity discretion and do not use AI cooldown.

No permanent deletion endpoint was added. Cancellation removes incorrect alerts
from active views while preserving history. The audit fields retain the first
acknowledgement and final closure; this is not a version history of draft edits.

## Migration and verification

Revision `20261024_alert_management` follows `20261023_notifications`. It adds
RESOLVED/CANCELLED enum values, nullable acknowledgement/closure audit columns,
synthetic test metadata, and closure constraints. Existing rows, references,
approval timestamps and expiry values are not rewritten. Synthetic and
operational history stay in their original tables.

The upgrade was verified against real PostgreSQL in a disposable schema,
including preservation of an existing approved alert, concurrent test creation,
and rollback protection. It was also applied to the local database with unchanged
counts for users, locations, predictions, alerts, synthetic datasets, observations,
predictions and alerts. Other installations must run `alembic upgrade head`
before starting the updated application.

Downgrade refuses to discard acknowledgement/closure audit or explicit test
records. When safe, it removes only the new columns/constraints; PostgreSQL enum
labels remain because removing them requires rebuilding the enum type.

Verification commands:

```bash
cd backend
.venv/bin/python -m pytest tests -q
WEATHER_POSTGRES_TEST=1 .venv/bin/python -m pytest weather_tests -q
cd ../frontend
npm run lint
npm run test
npm run build  # includes TypeScript checks
```

The PostgreSQL tests create uniquely named temporary schemas and delete only
those schemas. They do not change the application's existing data.
