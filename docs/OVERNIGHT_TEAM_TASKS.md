## Aryan

- Build weather observation storage and APIs for submitting and retrieving the latest weather for a location. Include rainfall, temperature, humidity, observation time, and source.
- Validate measurements and location IDs. Protect weather submission with the existing MET-admin authentication; handle invalid input, missing observations, and database errors.
- Add weather API tests using fixture locations and observations, and document the request/response examples. No AI integration is required.

## Louvatu

- Add latitude, longitude, and division to location storage. Build location list/detail APIs and a repeatable script for adding clearly labelled Fiji demo locations.
- Connect the map's locations and coordinates to the location API. Keep search, markers, selection, and filters working; show an explicit no-prediction state when actual risk data is unavailable.
- Add location validation/API tests and map loading, empty, error, and retry states. Use labelled fixture risks for testing colours and filters without needing the AI model.

## Atharv

- Connect the administrator alert screen to the existing backend alert APIs: list, detail, manual draft, edit, approve, reject, and suppress. Collect a suppression reason and preserve changes after reload.
- Add a community alert panel using `/api/alerts/active`, with severity, location, message, timestamp, and periodic refresh. Update dashboard alert counts from actual API responses.
- Add frontend tests for alert actions, notifications, loading/errors, expired sessions, and role restrictions. Test using fixture locations/alerts; leave prediction cards in an explicit no-data state.

## Rishi

- Add PostgreSQL integration tests for the existing alert workflow: duplicate prevention, foreign keys, rollback, approval/suppression, and concurrent review requests. Use clearly labelled fixture predictions; do not call the AI model.
- Fill authentication/API test gaps, including incorrectly signed JWTs and alert pagination. Fix failures within authentication/alert code and rerun the existing backend tests.
- Set up CI for backend tests and frontend lint/type/build checks. Update setup instructions with working commands and a manual-alert demo walkthrough that uses fixture data and does not require AI inference.
