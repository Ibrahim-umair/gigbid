# stay-helper

Guests of a holiday rental should not need to download anything to find the Wi-Fi password.

This small web hook receives incoming text messages and WhatsApp messages from Twilio, looks up which property and booking the sender belongs to, and replies using only that property's house manual. If it is not sure, or if the message sounds urgent, it tells the guest the host has been told and pings the host.

## Pieces
- `/sms` webhook (form-encoded POST from Twilio)
- Manual snippets in `manuals/<property>.json`
- Escalation: urgent keywords or low confidence -> message to host number
- Numbers are purged 30 days after checkout (`purge.py`, run by cron)

## Local testing
Expose port 8000 with a tunnel and set the Twilio sandbox webhook to `/sms`.
