# Homebound
_A safety app for explorers (divers, hikers, climbers, backpackers)._

---

## TL;DR
Create a trip plan with start time and ETA, share one-tap SMS/web links for check-in/out, and **auto-notify contacts** if you’re overdue. Overdue alerts include a concise, printable **PDF safety card**.

---

## Why Homebound
- **One-tap safety:** Participants get a unique link—no login required—to mark **Started** or **Safe**.
- **Automatic peace of mind:** If you don’t check out by **ETA + grace**, contacts are notified with plan details and a generated PDF.
- **Privacy by design:** MVP avoids background location; uses signed, scoped tokens instead of accounts.

---

## Key Features (MVP)
- **Create Plan:** Title, start, ETA, free-form location (optional GPX), notes, and emergency contacts.
- **One-Tap Check-In/Out:** Via SMS or public web links.
- **Overdue Escalation:** Automatic SMS/email with a PDF safety card when not checked out by ETA + grace.
- **Activity Log:** Timeline of check-ins/outs/overdues for each plan.

> **Non-Goals (MVP):** Real-time GPS tracking; complex roles/ACLs beyond share-tokens; payments/orgs/dashboards.

---

## User Stories
1. As a **backpacker**, I can share an easy-to-understand route with start/end times and notes, and my contacts are auto-notified if I don’t check in by the planned finish.
2. As a **scuba diver**, I can create a dive plan with specific locations and notify emergency contacts if I don’t check in after a set surface interval.
3. As a **climber**, I can let people know where I’m going and when I’ll be back.
4. As a **hiker**, if I get lost or go missing, my plan details and contacts are already in place.

---

## Architecture
- **Backend:** Python (FastAPI) + SQLite (SQLAlchemy)
- **Scheduling:** `c_scheduler` (CPython extension): durable min-heap/timer-wheel for due/overdue jobs (persisted to disk)
- **Messaging:** Pluggable SMS provider webhooks + SMTP for email (local dev can run email-only)
- **Frontend:** Server-rendered (Jinja2) with light htmx sprinkles; optional React later
- **Deploy:** Docker; friendly to Fly.io/Render/Railway

**Planned Flow**
1. Owner creates plan → server stores plan + generates signed check-in/out tokens.  
2. Server schedules an overdue job for **ETA + grace**.  
3. Participants receive SMS link → tap → server records check-in/out.  
4. If checkout occurs → cancel overdue. Else when time passes → overdue fires → notifications + PDF.

---

## Data Model (high-level)
- **plans**: id, title, start_at, eta_at, grace_minutes, location_text, notes, owner_contact_id, status
- **contacts**: id, plan_id, name, phone, email, notify_on_overdue
- **tokens**: id, plan_id, purpose (checkin|checkout), nonce, exp, hmac
- **events**: id, plan_id, kind (created|checkin|checkout|overdue|notify), at, meta
- **jobs**: id, plan_id, run_at, kind (overdue), canceled_at
