# Shaman Digital Twin

![Image of a flowchart of the software architecture](SoftwareArchitectureDiagram.png)


# Digital Twin UI + Mock API

This repository contains a Vite React frontend and a FastAPI backend scaffold with mock endpoints.

The goal is to provide an end-to-end flow where the React UI populates fields and graphs from API responses (mock data for now).

# Testing 💻

Last tested using Python 3.14, npm 11.6.2, and Node.js v22.16.0!

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
uvicorn app.main:app --reload --port 8000
```
