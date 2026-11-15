# pantry-notes

A weekend project so I stop buying a fourth jar of paprika.

I type short notes like "opened tahini, half left, expires march" into a text box. The app stores them in SQLite and lets me search them later by describing what I want to cook, not by exact words ("something creamy with chickpeas") and tells me which notes are closest.

This is just for home use. No accounts, no cloud, runs on a laptop.

## Run
```
uvicorn app:app --reload
```
Open `http://localhost:8000/docs` and use the two endpoints.

## Ideas for later
- barcode scanning
- shopping list export
- reminders when something is about to expire
