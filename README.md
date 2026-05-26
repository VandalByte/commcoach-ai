# CommCoach AI

CommCoach AI is a small project that helps with basic interview preparation using simple AI-powered agents. It includes a backend service, a lightweight frontend, utilities for voice input/output, and storage for embeddings.

This README is a short guide to what the project contains and how to install and run it.

## Project structure

Top-level layout (important files and folders):

- `main.py` - simple project entry point (root).
- `backend/` - backend service and API
  - `backend/app/` - backend app package
  - `backend/core/` - configuration and settings
  - `backend/models/` - domain models and schemas
  - `backend/services/` - agents, interview logic, parsers, voice helpers
  - `backend/storage/` - vector store integration
- `frontend/` - web UI (Vite + React)
- `voice/` - simple CLI voice helpers for STT/TTS
- `utils/` - shared utility modules
- `data/` - local data (example: Chroma DB)
- `requirements.txt` - root Python dependencies
- `backend/requirements.txt` - backend-specific dependencies

## Requirements

- Python 3.10+ (recommended)
- Node.js + npm (for the frontend, optional if you only use the backend)

## Install (Windows)

1. Create and activate a Python virtual environment:

```
python -m venv .venv
.venv\Scripts\activate
```

2. Install root Python dependencies:

```
pip install -r requirements.txt
```

3. (Optional) Install backend-specific dependencies:

```
pip install -r backend/requirements.txt
```

4. Install frontend dependencies (optional):

```
cd frontend
npm install
```

## Run

Run the backend directly:

```
uvicorn backend.app.main:app --reload --port 8000
```

Run the frontend (from `frontend`):

```
cd frontend
npm run dev
```

Notes:

- The project contains a local Chroma store under `data/chroma/` for vector embeddings.
- Adjust environment variables or `config.toml` as needed for API keys or service configuration.

## License & Contact

This repository is a small personal project. For questions or help, open an issue or contact the maintainer.

Enjoy hacking on CommCoach AI!
