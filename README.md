# Shaman Digital Twin
**To see the finalized work all you have to do in download and run Shaman Digital Twin_0.1.0_x64-setup.exe on the Pre-release one https://github.com/kyleksaiki/digital_twin_mvp/releases**



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

# Human Visual Detection (YOLO) 👁

The Human Visual Detection page uses Ultralytics YOLO (`yolo11n.pt`, nano COCO
model) to find people in uploaded images. The first detection request downloads
the model weights (~5 MB) and therefore requires network access on the backend.
The weights file is gitignored (`*.pt`). If `ultralytics` is not installed, the
rest of the app runs normally and only this page reports the missing dependency.
