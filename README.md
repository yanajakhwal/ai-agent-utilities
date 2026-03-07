## Regulatory Document Agent

This project implements the agent described in `agent_session.md`:

- Parse an incoming email for a **matter number** and **document type**
- Navigate the Nova Scotia Regulatory Board public database
- Download up to **10 documents**
- Compress them into a **ZIP file**
- (Optionally) email the ZIP file back with **metadata about the matter**

### Setup

1. **Create a virtual environment** (optional but recommended):

```bash
python -m venv .venv
source .venv/bin/activate  # on macOS/Linux
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
python -m playwright install
```

### Run from the command line

From the `ai-agent-utilities` directory (with your venv activated):

```bash
python run_agent.py
```

Or pass a message:

```bash
python run_agent.py "Hi Agent, can you give me Other Documents from M12205?"
```

Without SMTP configured, the agent still parses the message, scrapes the site, and creates the ZIP in `./downloads`; it just won’t send an email.

#### Email setup (Gmail → any recipient)

1. Copy the example env file and edit it:
   ```bash
   cp .env.example .env
   ```
2. In `.env`, set:
   - `SMTP_USER` = your Gmail address (e.g. `yanajakhwal@gmail.com`)
   - `SMTP_PASSWORD` = a **Gmail App Password** (not your normal password)
   - `EMAIL_TO` = recipient (e.g. `yjakhwal@uwaterloo.ca`)
3. Create a Gmail App Password:
   - Go to [Google Account → Security → App passwords](https://myaccount.google.com/apppasswords)
   - Sign in, create an app password for “Mail”, copy the 16-character password into `SMTP_PASSWORD` in `.env`
4. Run the agent from `ai-agent-utilities`; it will load `.env` and send the ZIP to `EMAIL_TO`.

### Running the Agent (Python API)

The core orchestration function is `run_agent` in `agent/orchestrator.py`.

Example usage:

```python
from pathlib import Path
from agent.orchestrator import run_agent

email_text = "Hi Agent, can you give me Other Documents from M12205?"

result = run_agent(
    email_text=email_text,
    download_root=Path("./downloads"),
    smtp_config={
        "host": "smtp.example.com",
        "port": 465,
        "user": "smtp-user",
        "password": "smtp-password",
    },
)

print(result)
```

This will:

- Parse the email
- Drive a headless browser to locate and download up to 10 matching documents
- Create a ZIP archive in `./downloads`
- Send an email with the ZIP attached (using the provided SMTP settings)

> Note: The DOM selectors used in the scraper are based on assumptions and may need to be adjusted against the live site.

