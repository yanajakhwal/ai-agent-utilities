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
python3 run_agent.py "Hi Agent, can you give me Other Documents from M12383?"
```

To see it in the browser instead of runnign it in the back,
```bash
python3 run_agent.py --headed "Hi Agent, can you give me Other Documents from M12383?"
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

This will:

- Parse the email
- Drive a headless browser to locate and download up to 10 matching documents
- Create a ZIP archive in `./downloads`
- Send an email with the ZIP attached (using the provided SMTP settings)

> Note: The DOM selectors used in the scraper are based on assumptions and may need to be adjusted against the live site.

### Approach & Lessons Learned

I split the problem into isolated components — **email parser**, **scraper**, **zipper**, and **mailer** — each in its own module, with a single **orchestrator** that wires them together. This made it easy to build and test each piece independently. I started with a naive version using standard Playwright selectors based on assumptions about the site's HTML, then iterated against the live site using `--headed` mode and debug screenshots to fix what broke.

- The UARB site is built on **FileMaker/GWT (Google Web Toolkit)**, which renders the entire UI as nested `<div>` elements rather than native HTML form controls (`<input>`, `<select>`, etc.). Standard Playwright selectors like `page.fill()` or `page.click("text=...")` don't work reliably here.
- Because of GWT, interaction had to be done via **bounding-box coordinate clicks** and `page.evaluate()` JavaScript — find the element in the DOM, get its `getBoundingClientRect()`, then `page.mouse.click(x, y)`.
- GWT **splits visible labels across multiple sibling divs** (e.g. "Other Docs" becomes two separate `<div>` elements: "Other" and "Docs"). Tab navigation had to search for a keyword match and then locate the closest number-only element below it spatially, rather than relying on the full label text.
- **Metadata extraction is entirely spatial.** There are no semantic class names or `data-` attributes — headers have child sort-arrow buttons so they aren't leaf nodes. The scraper anchors on the matter number element and classifies nearby leaf divs by content patterns (dates via regex, title by length, etc.) and relative position.
- Downloading files required **multiple fallback strategies**: direct HTTP fetch via `href`, catching Playwright's `expect_download` event, and checking for new tabs/popups — because the site's "GO GET IT" modal triggers downloads differently depending on the document.
- Debug screenshots at key steps (after search results load, after navigating to a doc tab) were essential for iterating on selectors without re-running the full flow each time.
