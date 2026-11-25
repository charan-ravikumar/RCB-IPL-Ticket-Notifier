<div align="center">

# 🎟️ RCB Ticket Notifier

**Get an SMS and WhatsApp alert when Royal Challengers Bengaluru tickets go live.**

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![Selenium](https://img.shields.io/badge/Selenium-headless%20Chrome-43B02A?logo=selenium&logoColor=white)
![Twilio](https://img.shields.io/badge/Twilio-SMS%20%2B%20WhatsApp-F22F46)

[Quick start](#-quick-start) •
[Configuration](#%EF%B8%8F-configuration) •
[How it works](#-how-it-works) •
[Troubleshooting](#-troubleshooting)

</div>

---

IPL tickets can sell out quickly. This script keeps an eye on the [RCB ticket page](https://shop.royalchallengers.com/ticket) for you and sends a burst of alerts as soon as the text you are waiting for appears.

## ✨ Features

| | |
|---|---|
| 🔍 **Real browser checks** | Headless Chrome renders the page, so JavaScript content is visible |
| ⚡ **Two polling speeds** | Every 60 s during peak hours, every 5 min otherwise |
| 📲 **SMS + WhatsApp** | Sent through Twilio, to as many recipients as you configure |
| 🚨 **Alert bursts** | 10 alerts, 10 s apart, when tickets are detected |
| 🛠️ **Outage detection** | Warns you if the page fails to load or looks wrong, and when it recovers |
| 💓 **Heartbeat** | A "still running" message about every 6 hours |

## 🚀 Quick start

### Prerequisites

- Python 3.9 or newer
- Google Chrome (Selenium 4 downloads the matching ChromeDriver automatically)
- A [Twilio](https://www.twilio.com/) account with an SMS-capable number

### 1. Clone and install

```bash
git clone https://github.com/charan-ravikumar/RCB-Ticket-Notifier.git
cd RCB-Ticket-Notifier

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set up Twilio

1. Copy your **Account SID** and **Auth Token** from the Twilio Console.
2. Get a Twilio phone number for SMS. Trial accounts can only message verified numbers.
3. *(Optional, for WhatsApp)* Join the [WhatsApp Sandbox](https://www.twilio.com/docs/whatsapp/sandbox) from the recipient's phone, and note the **Content SID** of a template that has a single variable, `{{1}}`.

### 3. Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your values.

### 4. Run

```bash
python rcb_ticket_notifier.py
```

You should receive a "started" message. Keep the terminal open and the computer awake. Press `Ctrl+C` to stop.

## ⚙️ Configuration

### Environment variables (`.env`)

| Variable | Required | Description |
|---|:---:|---|
| `TRIGGER_TEXTS` | ✅ | `\|`-separated texts that mean tickets are live |
| `MATCH_NAME` | | Match name used in alert messages |
| `HEALTH_CHECKS` | | `\|`-separated texts that show the page loaded properly |
| `TICKET_URL` | | Page to watch |
| `RECIPIENT_1_PHONE` | ✅ | Number to alert, with country code |
| `RECIPIENT_1_ACCOUNT_SID` | ✅ | Twilio Account SID |
| `RECIPIENT_1_AUTH_TOKEN` | ✅ | Twilio Auth Token |
| `RECIPIENT_1_SMS_FROM` | ✅ | Your Twilio SMS number |
| `RECIPIENT_1_WA_CONTENT_SID` | | Enables WhatsApp for this recipient |
| `RECIPIENT_1_WA_FROM` | | WhatsApp sender (defaults to the sandbox number) |
| `RECIPIENT_1_WA_ACCOUNT_SID` / `_WA_AUTH_TOKEN` | | Only if WhatsApp uses another Twilio account |

Add more people with `RECIPIENT_2_*`, `RECIPIENT_3_*` and so on. Numbering must have no gaps.

> [!IMPORTANT]
> **Choose triggers carefully.** Matching is a simple case-insensitive substring search. Use text that appears *only* when your match is on sale, such as its date or the opponent's name. Broad entries like `APR` or `BUY TICKETS` will fire on other matches.
>
> **Keep health checks current.** At least one must always be on a working page, even after your tickets appear. Otherwise the page is reported as broken and triggers are ignored.

### Timing (top of `rcb_ticket_notifier.py`)

| Setting | Default | Meaning |
|---|---|---|
| `PEAK_INTERVAL` | `60` s | Delay between checks in peak hours |
| `NORMAL_INTERVAL` | `300` s | Delay between checks otherwise |
| `PEAK_START` / `PEAK_END` | `07:00` / `23:59` | Peak window, in local time |
| `NUM_ALERTS` | `10` | Alerts per burst |
| `ALERT_GAP` | `10` s | Delay between alerts in a burst |
| `HEARTBEAT_EVERY` | `6` h | Delay between status messages |

## 🧠 How it works

```mermaid
flowchart TD
    A([Start]) --> B[Open ticket page in headless Chrome<br/>and send a 'started' message]
    B --> C[Refresh page and read visible text]
    C --> D{Loaded?}
    D -- No --> E[Alert: site down<br/>restart browser]
    D -- Yes --> F{Health text found?}
    F -- No --> G[Alert: page looks wrong]
    F -- Yes --> H{Trigger text found?}
    H -- Yes --> I[🎟️ Send alert burst]
    I --> J([Stop])
    H -- No --> K[Send recovery or heartbeat<br/>message if due]
    E --> W[Wait 60 s or 5 min]
    G --> W
    K --> W
    W --> C
```

- The **first** failure triggers a burst of up to 10 alerts, which stops early if the page recovers. While it stays down, you get one alert per check.
- Once tickets are detected, the script sends its burst and **exits**. Restart it to watch for another match.

## 📁 Project structure

```
.
├── rcb_ticket_notifier.py   # The notifier: run this
├── find_api_endpoints.py    # Optional developer helper
├── .env.example             # Configuration template
├── requirements.txt         # Python dependencies
└── README.md
```

### 🧪 What is `find_api_endpoints.py`?

An exploration tool, **not** needed to receive alerts. It:

1. Downloads the HTML of the ticket page.
2. Finds the site's main JavaScript bundle (`/assets/index-*.js`).
3. Prints every URL embedded in that bundle.
4. Highlights those containing words such as `ticket`, `match`, `event` or `api`.

The goal is to discover a backend API that could be polled directly, which would be faster and lighter than driving a browser.

```bash
python find_api_endpoints.py
```

## 🩺 Troubleshooting

| Problem | What to check |
|---|---|
| `No recipients configured` | `.env` exists and has `RECIPIENT_1_PHONE` |
| SMS fails | Credentials, number format, and trial-account verification |
| WhatsApp fails | The recipient has joined the sandbox (membership expires) and the Content SID belongs to that account |
| Constant "health check failed" | Update `HEALTH_CHECKS` to text currently on the page |
| Alert fires immediately | A trigger is too broad |
| Chrome does not start | Install or update Google Chrome |

## ⚠️ Good to know

- Detection depends on the page's wording, so a site redesign can break it.
- Twilio charges for messages. With two recipients on SMS and WhatsApp, one burst is 40 messages.
- This script only notifies you. It does not book tickets.
- Check the website's terms of use and keep the polling interval reasonable.

## 🔒 Security

Credentials and phone numbers belong in `.env`, which git ignores. If a token is ever exposed, rotate it in the Twilio Console.

---

<div align="center">

*An unofficial fan project, not affiliated with Royal Challengers Bengaluru, the IPL or Twilio.*

**Ee Sala Cup Namde! 🔴⚫**

</div>
