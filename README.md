# AI-Driven Evidence Dashboard

An AI Action Agent embedded in an [Evidence.dev](https://evidence.dev) dashboard. The agent accepts natural language commands via a chat widget and uses **Gemini 2.5 Flash** (Vertex AI) with structured function calling to control the dashboard through deterministic actions — **no browser automation**.

## Architecture

![Architecture Diagram](docs/architecture.png)

**Data Flow:**

1. **User** types a natural language command in the chat widget
2. **AgentChat.svelte** sends an HTTP POST to the FastAPI backend
3. **FastAPI Backend** passes the prompt to Gemini 2.5 Flash, which returns structured actions via function calling
4. Backend validates actions against allow-lists and returns JSON actions to the frontend
5. **AgentChat** dispatches a `CustomEvent('dashboard-action')` on the `window` object
6. **ActionListener.svelte** (inside the page context) catches the event and writes to Evidence.dev's `$inputs` store
7. **Evidence.dev** reactively re-executes SQL queries and re-renders charts/tables

**Key Design**: Evidence.dev's `<Dropdown>` components use a shared Svelte context store (`$inputs[name]`). The `ActionListener` writes directly to this store — the same mechanism the Dropdown uses internally — triggering instant reactive updates without page reloads or DOM manipulation.

## Directory Structure

```
/ai-data-agent
├── /backend
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic Settings (.env loader)
│   │   │   ├── constants.py         # Allow-list for actions, fields, pages
│   │   │   └── llm.py               # Gemini Vertex AI client + tool schema
│   │   ├── models/
│   │   │   └── actions.py           # Pydantic models (DashboardAction union)
│   │   ├── services/
│   │   │   ├── agent_service.py     # Validation + confirmation messages
│   │   │   └── websocket_manager.py # WebSocket connection broadcasting
│   │   └── main.py                  # FastAPI app (endpoints + CORS)
│   ├── requirements.txt
│   └── .env
├── /frontend
│   ├── /components
│   │   ├── AgentChat.svelte         # Chat widget + WebSocket + event dispatch
│   │   └── ActionListener.svelte    # Svelte context bridge → $inputs store
│   ├── /pages
│   │   ├── +layout.svelte           # Evidence layout + AgentChat mount
│   │   └── index.md                 # Dashboard with category/year filters
│   └── /sources
│       └── needful_things/          # DuckDB sample data
├── /docs
│   ├── architecture.png             # Architecture diagram (exported)
│   └── architecture.excalidraw      # Editable Excalidraw source
└── .gitignore
```

## Supported Actions (V1)

| Action | Description | Example Prompt |
|--------|-------------|----------------|
| `set_filters` | Apply filters to Dropdown inputs | "Filter for Clothing category" |
| `clear_filters` | Reset filters to wildcard | "Clear all filters" |
| `navigate` | Go to a different page | "Go to settings" |
| `export` | Download visible data as CSV | "Export data as CSV" |

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |
| Google Cloud CLI (`gcloud`) | latest |

## Setup

### 1. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

### 2. Configure Environment

Edit `backend/.env`:

```env
GCP_PROJECT_ID=my-gcp-project
GCP_REGION=us-central1
GEMINI_MODEL=gemini-2.5-flash
```

### 3. Install & Run the Backend

```bash
cd ai-data-agent/backend

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload
```

### 4. Install & Run the Evidence Frontend

```bash
cd ai-data-agent/frontend

npm install
npx evidence dev
```

The dashboard will be available at **http://localhost:3000**.

## Usage

1. Open the dashboard at `http://localhost:3000`.
2. Click the purple **chat bubble** in the bottom-right corner.
3. Type a command and press **Enter**.

### Example Prompts

| Prompt | What Happens |
|--------|-------------|
| `Filter for Clothing` | Sets `$inputs.category = "Clothing"`, chart re-renders |
| `Show 2020 data` | Sets `$inputs.year = 2020`, chart re-renders |
| `Clear all filters` | Resets inputs to `%`, shows all data |
| `Export as CSV` | Downloads visible table data as CSV |

## License

MIT
