import json
import os
import re
from datetime import date

import redis
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
twilio = Client(os.environ["TWILIO_SID"], os.environ["TWILIO_TOKEN"])
HOST_NUMBER = os.environ["HOST_NUMBER"]
FROM_NUMBER = os.environ["TWILIO_FROM"]
URGENT = re.compile(r"(no (hot )?water|locked out|gas|smell|flood|fire|broken|can't get in)", re.I)


def booking_for(phone):
    raw = r.get(f"booking:{phone}")
    return json.loads(raw) if raw else None


def best_snippet(prop, text):
    with open(f"manuals/{prop}.json", encoding="utf8") as fh:
        snippets = json.load(fh)
    words = set(re.findall(r"[a-z]+", text.lower()))
    scored = [(len(words & set(s["keywords"])), s) for s in snippets]
    score, snip = max(scored, key=lambda t: t[0])
    return (snip, score)


def notify_host(phone, prop, text):
    twilio.messages.create(
        to=HOST_NUMBER, from_=FROM_NUMBER,
        body=f"[{prop}] guest {phone[-4:]} says: {text[:240]}")


@app.post("/sms")
def sms():
    body = request.form["Body"].strip()
    sender = request.form["From"].replace("whatsapp:", "")
    out = MessagingResponse()
    booking = booking_for(sender)
    if not booking or not (booking["checkin"] <= date.today().isoformat() <= booking["checkout"]):
        out.message("Hi! I can only help guests with a current booking. Please contact your host.")
        return str(out)
    if URGENT.search(body):
        notify_host(sender, booking["property"], body)
        out.message("Sorry about that. I have alerted your host and they will reply shortly.")
        return str(out)
    snip, score = best_snippet(booking["property"], body)
    if score == 0:
        notify_host(sender, booking["property"], body)
        out.message("I am not sure about that one, so I have asked your host to reply.")
    else:
        out.message(snip["answer"])
    return str(out)
