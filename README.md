# Bangladesh Law MCP Server

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-1.2%2B-purple.svg)](https://modelcontextprotocol.io)
[![Dataset size](https://img.shields.io/badge/acts-1%2C484%2B-green.svg)](https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset)
[![Years covered](https://img.shields.io/badge/years-1799%E2%80%932025-lightgrey.svg)](https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset)

> A [Model Context Protocol](https://modelcontextprotocol.io) server that lets any
> AI assistant — **Claude**, **Gemini**, **GPT**, Cursor, VS Code, Continue.dev,
> or any MCP-compatible client — query the full text of Bangladeshi legislation
> directly from natural language.

Built on top of the
[**Bangladesh Legal Acts Dataset**](https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset),
which contains **1,484+ acts** scraped from <http://bdlaws.minlaw.gov.bd/> and
enriched with the historical government and legal-system context for each
act's period.

---

## ✨ What you can ask

Once connected, your AI assistant can answer questions like:

- *"Find all Bangladesh acts from the 1970s related to land."*
- *"What was the legal framework when the Penal Code 1860 was enacted?"*
- *"Show me section 3 of the Code of Criminal Procedure."*
- *"Which government was in power when the Bangladesh University of Professionals Act 2009 was passed?"*
- *"Search the entire corpus for acts that mention 'environment protection'."*
- *"Is the Companies Act 1994 still in force?"*

---

## 🧰 Tools exposed

| Tool | Purpose |
|------|---------|
| `list_acts` | Browse acts with filters (year range, language, repealed/active, title substring) |
| `get_act` | Fetch a complete act by id (full sections, footnotes, government & legal context) |
| `get_section` | Pull a single section of an act |
| `search_acts` | Free-text search across titles or section bodies, with snippets |
| `get_statistics` | Aggregate dataset stats — year range, language distribution, top gov systems, repealed count |

Each act is also exposed as an MCP **resource** at `act://<act-id>` so clients
that prefer resource-style reads can pull the JSON directly.

---

## 📦 Installation

### 1. Clone this repo and the dataset side-by-side

```bash
git clone https://github.com/sakhadib/bangladesh-law-mcp.git
git clone https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset.git
```

You should now have:

```
bangladesh-law-mcp/
Bangladesh-Legal-Acts-Dataset/
```

The server will auto-discover the dataset in this sibling layout. If you keep
the dataset anywhere else, set `BLA_DATA_DIR` to its `Data/acts` folder (or to
the parent `Data/` folder).

> **About Git LFS:** the dataset uses LFS for the full corpus. If you only see
> a few hundred `.json` files in `Bangladesh-Legal-Acts-Dataset/Data/acts/`,
> run `git lfs install && git lfs pull` inside the dataset repo.

### 2. Install Python dependencies

```bash
cd bangladesh-law-mcp
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Or install the package itself:

```bash
pip install .
```

This registers a `bangladesh-law-mcp` command on your `PATH`.

### 3. Sanity check

```bash
python server.py
```

The server should print something like:

```
[INFO] bangladesh-law-mcp: Loading acts from .../Bangladesh-Legal-Acts-Dataset/Data/acts
[INFO] bangladesh-law-mcp: Indexing 1484 act files
[INFO] bangladesh-law-mcp: Index built: 1484 acts
```

and then sit silently on stdout (it's waiting for an MCP client on stdin). Press `Ctrl+C` to stop.

---

## 🔌 Connect an AI client

Pick your client. All of them connect over **stdio** — no API key, no network.

### Claude Desktop

Edit `claude_desktop_config.json`:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "bangladesh-law": {
      "command": "python",
      "args": ["C:\\absolute\\path\\to\\bangladesh-law-mcp\\server.py"]
    }
  }
}
```

Restart Claude Desktop. You'll see a 🔨 icon with the new tools in the chat
composer.

### VS Code / Cursor (one-click via `.vscode/mcp.json`)

A starter config is included at `.vscode/mcp.json` (edit the absolute path
to match your machine):

```json
{
  "servers": {
    "bangladesh-law": {
      "type": "stdio",
      "command": "python",
      "args": ["C:\\absolute\\path\\to\\bangladesh-law-mcp\\server.py"]
    }
  }
}
```

Then in VS Code run **MCP: List Servers** from the command palette and start
`bangladesh-law`.

### Gemini (via an MCP-compatible adapter)

Gemini itself doesn't speak MCP natively, but open-source MCP bridges
(LangChain's MCP adapter, the MCP Inspector, etc.) let you expose MCP tools to
Gemini. After installing such an adapter, point it at:

```bash
python /absolute/path/to/bangladesh-law-mcp/server.py
```

### GPT / ChatGPT (via MCP plugin / LangChain)

Same story — wire the stdio server into any MCP-aware orchestrator
(LangChain's `MCPAdapter`, AutoGen, CrewAI, etc.). The tool surface described
above is what your GPT agent will see.

### Continue.dev / Cline / Roo Code

Add to your MCP config:

```json
{
  "mcpServers": [
    {
      "name": "bangladesh-law",
      "command": "python",
      "args": ["/absolute/path/to/bangladesh-law-mcp/server.py"]
    }
  ]
}
```

---

## 🌐 Live Hosted Instance (Fly.io)

The server is deployed as an always-on Streamable HTTP endpoint on
[Fly.io](https://fly.io). Any MCP client that supports remote servers
can connect to:

```
https://bangladesh-law-mcp.fly.dev/mcp
```

A liveness check is available at:

```
https://bangladesh-law-mcp.fly.dev/healthz
```

### Connecting a remote-capable client

**VS Code / Cursor (Streamable HTTP):**

```json
{
  "servers": {
    "bangladesh-law": {
      "type": "streamableHttp",
      "url": "https://bangladesh-law-mcp.fly.dev/mcp"
    }
  }
}
```

**Claude Desktop (if/when remote MCP is supported):**

```json
{
  "mcpServers": {
    "bangladesh-law": {
      "type": "streamableHttp",
      "url": "https://bangladesh-law-mcp.fly.dev/mcp"
    }
  }
}
```

> **Note:** Most desktop MCP clients today only support `stdio`. The
> hosted endpoint is primarily for web-based agents, custom integrations,
> and future clients that support remote MCP. For local use, the stdio
> transport (above) remains the simplest option.

### Deploying your own instance

1. Install [flyctl](https://fly.io/docs/hands-on/install-flyctl/) and sign up.
2. Push this repo to GitHub.
3. Create a Fly app:

   ```bash
   fly launch --no-deploy   # generates fly.toml, uses the Dockerfile
   ```

4. Deploy:

   ```bash
   fly deploy --remote-only
   ```

5. (Optional) Set up auto-deploy on push — add a `FLY_API_TOKEN` GitHub
   secret (created with `fly tokens create deploy`) and the included
   `.github/workflows/deploy.yml` will deploy on every push to `main`.

---

## ⚙️ Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `BLA_DATA_DIR` | `<repo>/../Bangladesh-Legal-Acts-Dataset/Data/acts` (or sibling) | Where to find the act JSON files. Accepts the `acts/` folder or its parent `Data/` folder. |
| `BLA_LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`. Logs go to **stderr** so the stdio JSON-RPC stream stays clean. |
| `TRANSPORT` | `stdio` | `stdio` for local clients, `http` for hosted/Streamable-HTTP mode (Fly.io, Docker). |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address and port for the HTTP transport. |

---

## 🛠 Development

Run a one-liner smoke test (no client needed):

```bash
python -c "import asyncio, server
async def m():
    out = await server.mcp.call_tool('get_statistics', {})
    print(out[1])
asyncio.run(m())"
```

Lint:

```bash
pyflakes server.py
```

The included GitHub Actions workflow (`.github/workflows/ci.yml`) lints and
byte-compiles on Python 3.10, 3.11, and 3.12 for every push and PR.

---

## 🗂 Project layout

```
bangladesh-law-mcp/
├── .dockerignore
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml        # auto-deploy to Fly.io
├── .gitignore
├── Dockerfile                # multi-stage build (clones dataset with LFS)
├── LICENSE
├── README.md
├── SECURITY.md
├── fly.toml                  # Fly.io app config (always-on free tier)
├── pyproject.toml
├── requirements.txt
└── server.py                 # the entire MCP server
```

---

## 🙏 Thanks

This project stands on the shoulders of two friends whose help made it real:

- **Rubaiyat** — for the early feedback, the test queries, and the patient
  bug reports that shaped the tool surface.
- **Jarif** — for helping debug the stdio transport, walking through
  MCP-client integration on Windows, and pushing for the polished README and
  CI setup that make this thing actually shippable.

Thank you both. 💚

And of course, **thanks to [sakhadib](https://github.com/sakhadib) and every
contributor to the original
[Bangladesh Legal Acts Dataset](https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset)** —
without that carefully curated corpus, none of this would exist.

---

## 📄 License

- The **server code** in this repository is released under the
  [MIT License](LICENSE).
- The **underlying data** is from
  [sakhadib/Bangladesh-Legal-Acts-Dataset](https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset)
  and is licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Please attribute
  the original authors when reusing the data.
