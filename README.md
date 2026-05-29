# Shaman Digital Twin

![Image of a flowchart of the software architecture](SoftwareArchitectureDiagram.png)

# Docs

- Architecture overview: `ARCHITECTURE.md`
- Audio workflow inputs: `docs/audio_workflow_inputs.md`

# Development 💻

Requirements: Python 3.11+ and Node 18+.

```bash
cd frontend
npm install
npm run dev
cd ..
```

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```
