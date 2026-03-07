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

### Running the Agent (Example)

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

