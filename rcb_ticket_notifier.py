"""Watch the RCB ticket page and alert by SMS and WhatsApp when tickets go live.

All account and match settings come from environment variables or a local
.env file (see .env.example).
"""

import json
import os
import sys
import time
from datetime import datetime
from datetime import time as dtime

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from twilio.rest import Client

load_dotenv()

# ─── CONFIG ───────────────────────────────────────────────────────────────────

def env_list(name, default=''):
    """Read a '|' separated list (page text often contains commas)."""
    return [item.strip() for item in os.getenv(name, default).split('|') if item.strip()]

URL        = os.getenv('TICKET_URL', 'https://shop.royalchallengers.com/ticket')
MATCH_NAME = os.getenv('MATCH_NAME', 'RCB match')

# Any ONE of these found = the page rendered correctly
HEALTH_CHECKS = env_list('HEALTH_CHECKS', 'BUY TICKETS|TICKETS NOT AVAILABLE')

# Any ONE of these found = tickets are live
TRIGGER_TEXTS = env_list('TRIGGER_TEXTS')

HEARTBEAT_EVERY     = 6     # hours between "still running" messages
NUM_ALERTS          = 10    # how many alerts to send when tickets go live / site down
ALERT_GAP           = 10    # seconds between each rapid alert

NORMAL_INTERVAL     = 300   # 5 minutes normally
PEAK_INTERVAL       = 60    # 1 minute during peak hours
PEAK_START          = (7,  0)
PEAK_END            = (23, 59)

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

# ─── RECIPIENTS ───────────────────────────────────────────────────────────────

def load_recipients():
    """Read RECIPIENT_1_*, RECIPIENT_2_*, ... until a number is missing."""
    recipients = []
    n = 1
    while os.getenv(f'RECIPIENT_{n}_PHONE'):
        def get(key, default=None):
            return os.getenv(f'RECIPIENT_{n}_{key}') or default

        sid, token, sms_from = get('ACCOUNT_SID'), get('AUTH_TOKEN'), get('SMS_FROM')
        if not (sid and token and sms_from):
            sys.exit(f'RECIPIENT_{n} needs ACCOUNT_SID, AUTH_TOKEN and SMS_FROM.')

        recipient = {
            'name': f'Recipient {n}',
            'phone': get('PHONE'),
            'sms_from': sms_from,
            'sms_client': Client(sid, token),
            'wa_client': None,
        }

        # WhatsApp is optional and may use a different Twilio account
        if get('WA_CONTENT_SID'):
            recipient['wa_client'] = Client(get('WA_ACCOUNT_SID', sid), get('WA_AUTH_TOKEN', token))
            recipient['wa_from'] = get('WA_FROM', '+14155238886')
            recipient['wa_content_sid'] = get('WA_CONTENT_SID')

        recipients.append(recipient)
        n += 1
    return recipients

RECIPIENTS = []     # filled at startup

# ─── SEND HELPERS ─────────────────────────────────────────────────────────────

def send_sms(r, body):
    try:
        msg = r['sms_client'].messages.create(from_=r['sms_from'], to=r['phone'], body=body)
        log(f"✅ [{r['name']}] SMS sent — SID: {msg.sid}")
    except Exception as e:
        log(f"❌ [{r['name']}] SMS failed: {e}")

def send_whatsapp(r, text):
    try:
        msg = r['wa_client'].messages.create(
            from_=f"whatsapp:{r['wa_from']}",
            content_sid=r['wa_content_sid'],
            content_variables=json.dumps({"1": text}),
            to=f"whatsapp:{r['phone']}"
        )
        log(f"✅ [{r['name']}] WhatsApp sent — SID: {msg.sid}")
    except Exception as e:
        log(f"❌ [{r['name']}] WhatsApp failed: {e}")

def notify(sms_body, wa_text):
    """Send SMS (and WhatsApp, if configured) to every recipient."""
    for r in RECIPIENTS:
        send_sms(r, sms_body)
    for r in RECIPIENTS:
        if r['wa_client']:
            send_whatsapp(r, wa_text)

# ─── RAPID ALERT BLASTS ───────────────────────────────────────────────────────

def rapid_alert_tickets():
    """Fire NUM_ALERTS rapid alerts to every recipient when tickets go live."""
    log(f"🚨 Firing {NUM_ALERTS} rapid alerts — TICKETS LIVE!")
    for i in range(1, NUM_ALERTS + 1):
        sms_body = f"🎟️ ALERT {i}/{NUM_ALERTS} — {MATCH_NAME} TICKETS LIVE! Book NOW: {URL}"
        wa_text  = f"RCB TICKETS LIVE! ALERT {i}/{NUM_ALERTS} — Book NOW!"
        notify(sms_body, wa_text)
        log(f"   Rapid alert {i}/{NUM_ALERTS} sent")
        if i < NUM_ALERTS:
            time.sleep(ALERT_GAP)
    log("✅ All rapid alerts sent.")

def rapid_alert_site_down(check_num, driver):
    """
    Fire rapid alerts when site is down.
    Re-checks the page between each alert — stops early if site recovers.
    Returns True if site came back up during the blast, False otherwise.
    """
    log(f"🚨 Firing up to {NUM_ALERTS} rapid alerts — SITE UNREACHABLE!")
    for i in range(1, NUM_ALERTS + 1):
        sms_body = f"⚠️ ALERT {i}/{NUM_ALERTS} — RCB ticket site is DOWN on check #{check_num}! Check manually: {URL}"
        wa_text  = f"RCB site DOWN! ALERT {i}/{NUM_ALERTS} — Check manually!"
        notify(sms_body, wa_text)
        log(f"   Site-down alert {i}/{NUM_ALERTS} sent")

        if i < NUM_ALERTS:
            time.sleep(ALERT_GAP)

            # ── Re-check if site recovered ────────────────────────────────────
            log(f"   🔄 Re-checking site before alert {i+1}...")
            _, page_healthy, load_error, _, _ = check_for_tickets(driver)

            if not load_error and page_healthy:
                log(f"   ✅ Site RECOVERED after alert {i}/{NUM_ALERTS}! Stopping alert blast.")
                notify(
                    sms_body=f"✅ RCB site is BACK UP (recovered mid-alert after {i} alerts). Still watching for {MATCH_NAME} tickets.",
                    wa_text=f"RCB site BACK UP after {i} alerts! Still watching for tickets."
                )
                return True  # site recovered

    log("✅ All site-down alerts sent. Site still down.")
    return False  # site still down after all alerts

# ─── TIMING ───────────────────────────────────────────────────────────────────

def is_peak_time():
    now = datetime.now().time()
    return dtime(PEAK_START[0], PEAK_START[1]) <= now <= dtime(PEAK_END[0], PEAK_END[1])

def get_interval():
    return PEAK_INTERVAL if is_peak_time() else NORMAL_INTERVAL

# ─── BROWSER ──────────────────────────────────────────────────────────────────

def make_driver():
    """Launch a headless Chrome instance that is reused across checks."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disk-cache-size=0")
    options.add_argument("--disable-application-cache")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver

def load_page(driver):
    """Open the ticket page. A failure is logged so the main loop can keep retrying."""
    try:
        driver.get(URL)
    except Exception as e:
        log(f"⚠️  Could not load the page: {e}")

def check_for_tickets(driver):
    """
    Refresh the page and look for health and trigger texts.
    Returns: (tickets_found, page_healthy, load_error, matched_trigger, matched_health)
    """
    try:
        driver.refresh()
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(5)  # give JavaScript time to render
        page_text = driver.find_element(By.TAG_NAME, "body").text.upper()

        matched_health = None
        for h in HEALTH_CHECKS:
            if h.upper() in page_text:
                matched_health = h
                break
        page_healthy = matched_health is not None

        matched_trigger = None
        for trigger in TRIGGER_TEXTS:
            if trigger.upper() in page_text:
                matched_trigger = trigger
                break
        tickets_found = matched_trigger is not None

        return tickets_found, page_healthy, False, matched_trigger, matched_health

    except Exception as e:
        log(f"⚠️  Error during page check: {e}")
        return False, False, True, None, None

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    RECIPIENTS.extend(load_recipients())
    if not RECIPIENTS:
        sys.exit("No recipients configured. Copy .env.example to .env and fill it in.")
    if not TRIGGER_TEXTS:
        sys.exit("TRIGGER_TEXTS is empty. Set it in your .env file.")

    log("=" * 55)
    log("🚀 RCB Ticket Notifier started")
    log(f"   Checking     : {URL}")
    log(f"   Match        : {MATCH_NAME}")
    log(f"   Recipients   : {len(RECIPIENTS)}")
    log(f"   Health checks: {HEALTH_CHECKS}")
    log(f"   Triggers     : {TRIGGER_TEXTS}")
    log(f"   Normal check : every {NORMAL_INTERVAL // 60} minutes")
    log(f"   Peak check   : every {PEAK_INTERVAL} seconds")
    log(f"   Heartbeat    : every {HEARTBEAT_EVERY} hours")
    log(f"   Rapid alerts : {NUM_ALERTS} blasts, {ALERT_GAP}s apart")
    log("=" * 55)

    log("🌐 Launching browser...")
    driver = make_driver()
    load_page(driver)
    log("✅ Browser ready")

    notify(
        sms_body=f"🚀 RCB Ticket Notifier is STARTED and running. You'll be alerted the moment {MATCH_NAME} tickets go live.",
        wa_text=f"RCB Notifier started! Watching for {MATCH_NAME} tickets."
    )

    last_heartbeat  = datetime.now()
    checks_done     = 0
    site_was_down   = False

    try:
        while True:
            checks_done += 1
            mode = "🔥 PEAK MODE" if is_peak_time() else "normal"
            log(f"🔍 Check #{checks_done} — scanning page... [{mode}]")

            tickets_found, page_healthy, load_error, matched_trigger, matched_health = check_for_tickets(driver)

            # ── Site completely unreachable ───────────────────────────────────
            if load_error:
                log(f"⚠️  Load error on check #{checks_done} — site unreachable!")
                if not site_was_down:
                    recovered = rapid_alert_site_down(checks_done, driver)
                    site_was_down = not recovered
                else:
                    notify(
                        sms_body=f"⚠️ RCB site still DOWN on check #{checks_done}. Check manually: {URL}",
                        wa_text=f"RCB site still DOWN on check #{checks_done}. Check manually!"
                    )
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = make_driver()
                load_page(driver)
                time.sleep(get_interval())
                continue

            # ── Health check failed (page loaded but looks wrong) ─────────────
            elif not page_healthy:
                log(f"🚨 Health check FAILED on check #{checks_done} — page may not be rendering correctly.")
                if not site_was_down:
                    recovered = rapid_alert_site_down(checks_done, driver)
                    site_was_down = not recovered
                else:
                    notify(
                        sms_body=f"🚨 RCB site health check still FAILING on check #{checks_done}. Check manually: {URL}",
                        wa_text=f"RCB site health STILL FAILING on check #{checks_done}. Check manually!"
                    )
                time.sleep(get_interval())
                continue

            # ── Tickets found — fire rapid alerts and stop ────────────────────
            elif tickets_found:
                log(f"🎟️  {MATCH_NAME} TICKETS ARE LIVE! Matched: '{matched_trigger}'.")
                rapid_alert_tickets()
                log("✅ All ticket alerts sent. Stopping script.")
                break

            # ── All good — site healthy, no tickets yet ───────────────────────
            else:
                if site_was_down:
                    notify(
                        sms_body=f"✅ RCB site is BACK UP on check #{checks_done}. Still watching for {MATCH_NAME} tickets.",
                        wa_text=f"RCB site is BACK UP on check #{checks_done}. Still watching!"
                    )
                    site_was_down = False

                log(f"✅ Page healthy (matched: '{matched_health}'). No tickets yet. Next check in {get_interval()}s.")

            # ── Heartbeat ─────────────────────────────────────────────────────
            hours_since = (datetime.now() - last_heartbeat).total_seconds() / 3600
            if hours_since >= HEARTBEAT_EVERY:
                log(f"💓 Sending heartbeat ({hours_since:.1f}h since last)...")
                notify(
                    sms_body=f"💓 RCB Notifier still running. Total checks: {checks_done}. {MATCH_NAME} tickets not live yet.",
                    wa_text=f"RCB Notifier still running. {checks_done} checks done. No tickets yet."
                )
                last_heartbeat = datetime.now()

            time.sleep(get_interval())

    finally:
        log("🛑 Closing browser...")
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
