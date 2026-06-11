# Shaman Digital Twin

![Image of a flowchart of the software architecture](SoftwareArchitectureDiagram.png)

# Docs

- Architecture overview: `ARCHITECTURE.md`
- Audio workflow inputs: `docs/audio_workflow_inputs.md`

# Development with Docker 🐋

If you're on windows/mac, make sure Docker Desktop is running Docker Engine.

```bash
# Build and launch both frontend and backend services
docker compose up --build

```

# Development 💻

Note: Python 3.11-3.13 is required for BirdNET because of Tensorflow, so for now the BirdNET stage is being bypassed.


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
uvicorn app.main:app --port 8000
```
