# Contributing to ChatGPT x Antigravity Bridge

Thank you for your interest in contributing to the project. This guide outlines how to set up your local development environment, run tests, and submit contributions.

---

## Code of Conduct & Principles
- Keep it pragmatic, technical, and lightweight.
- Preserve workspace boundary protection and security checks.
- Do not introduce dependencies without clear engineering justification.

---

## Getting Started

### 1. Fork & Clone
```bash
git clone https://github.com/aiengmohamedtayal-netizen/ChatGPT-Antigravity-Bridge.git
cd ChatGPT-Antigravity-Bridge
```

### 2. Create Virtual Environment
```bash
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On Linux / macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configuration
Copy `.env.example` to `.env` and adjust if needed:
```bash
cp .env.example .env
```

---

## Running Tests
Always ensure all tests pass before opening a PR:
```bash
python -m pytest tests/ -v
```

Tests run against an in-memory SQLite database using a zero-delay simulated provider by default, completing in under 2 seconds without requiring a local Antigravity installation.

---

## Development Workflow

1. Create a descriptive feature branch:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Make targeted, well-documented changes.
3. Add unit or integration tests under `tests/` covering new behavior.
4. Verify tests pass and no temporary files or secrets are staged.
5. Push your branch and open a Pull Request using the PR template.
