# Rocky — Free, Local-First Multi-Agent System on WSL with Groq API

Rocky is a highly optimized, outcome-anchored multi-agent system designed to run on consumer hardware with commercial-grade speed. By pairing **Windows Subsystem for Linux (WSL)** with the **Groq API** and local **Ollama** fallbacks, Rocky avoids the cognitive bottlenecks and slow swap latencies of local weights.

## Core Features

- **Decoupled Reasoning & Structured Formatting (§R.15)**: Bypasses model reasoning degradation by splitting text-based inference from Pydantic schema validation.
- **Two-Tiered Cache Alignment (§R.17)**: Matches Gemma3 and hosted Llama models prefix-caching requirements.
- **WSL Native Execution & RAM Disk (§R.16)**: Utilizes Linux native `/dev/shm` tmpfs RAM disk for fast model cache performance without unsigned Windows drivers.
- **Hermes Self-Learning Loop**: Programmatically validates successful outcomes before self-learning facts or staging skills.
- **Circuit Breaker Router**: Employs non-blocking failover worker mapping (CLOSED -> OPEN -> HALF_OPEN).

## Prerequisites

- **WSL (Ubuntu/Debian)** with Python 3.11+
- **Groq API Key** (set as environment variable `GROQ_API_KEY`)
- **Ollama** installed in WSL (for local model fallbacks)

## Getting Started

1. **Clone and Scaffold**:
   Set Rocky's root directory as your active workspace:
   `C:\Users\maitr\.gemini\antigravity\scratch\rocky` (maps to `/mnt/c/Users/maitr/.gemini/antigravity/scratch/rocky` in WSL).

2. **Environment Configuration**:
   Inside your WSL terminal, export your Groq API key:
   ```bash
   export GROQ_API_KEY="your_actual_groq_api_key_here"
   ```

3. **Install Dependencies**:
   ```bash
   pip install -e .
   ```

4. **Launch Rocky**:
   ```bash
   python rocky.py
   ```

## CLI Commands

| Command | Description |
|---|---|
| `/status` | View VRAM profiles, model statuses, and active circuit states |
| `/memory` | Query partitioned memory contents (user, system, project facts) |
| `/skills` | List validated and staging skills |
| `/undo` | Show UNDO_LOG.md and rollback hints |
| `/end-session` | Trigger self-reflection learning loops and commit changes to Git |
