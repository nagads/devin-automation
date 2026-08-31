# Devin Automation for Apache Superset Bug Remediation

An event-driven automation system that uses the Devin API to automatically fix bugs in Apache Superset. The system monitors GitHub issues, triggers Devin to create fixes, and tracks progress through an observability dashboard.

> **Tested with:** Podman 5.8.3 on Windows 11 (WSL2)

## Overview

This project demonstrates how Devin can be used as an autonomous coding agent to handle engineering toil - specifically, fixing bugs from a project's backlog without manual intervention.

### What It Does

1. **Setup**: Clones open bug issues (without existing PRs) from `apache/superset` to your fork
2. **Poll/Run**: Automatically picks up pending issues and triggers Devin to fix them
3. **Observe**: Dashboard shows real-time progress, success rates, and PR links
4. **Teardown**: Resets everything for the next demo run

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              SYSTEM                                      │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                        DOCKER COMPOSE                          │     │
│  │                                                                │     │
│  │  ┌──────────────────────────────────────────────────────────┐ │     │
│  │  │                    ORCHESTRATOR                          │ │     │
│  │  │                    (FastAPI + Python)                    │ │     │
│  │  │                                                          │ │     │
│  │  │  ENDPOINTS:                                              │ │     │
│  │  │  ├── GET  /                    → Web UI Dashboard        │ │     │
│  │  │  ├── POST /api/setup           → Clone issues from upstream│     │
│  │  │  ├── POST /api/run             → Trigger Devin processing │ │     │
│  │  │  ├── POST /api/teardown        → Reset for next demo     │ │     │
│  │  │  ├── GET  /api/status          → Current state (JSON)    │ │     │
│  │  │  └── GET  /api/sessions/{id}   → Devin session details   │ │     │
│  │  │                                                          │ │     │
│  │  │  BACKGROUND:                                             │ │     │
│  │  │  └── Scheduler (polls every N minutes)                   │ │     │
│  │  └──────────────────────────────────────────────────────────┘ │     │
│  │                              │                                 │     │
│  │                              ▼                                 │     │
│  │  ┌──────────────────────────────────────────────────────────┐ │     │
│  │  │                    DATABASE (SQLite)                     │ │     │
│  │  │  ├── issues (tracking cloned issues and their status)   │ │     │
│  │  │  ├── sessions (Devin session tracking)                  │ │     │
│  │  │  └── activity_log (audit trail)                         │ │     │
│  │  └──────────────────────────────────────────────────────────┘ │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                              │                                          │
│              ┌───────────────┼───────────────┐                          │
│              ▼               ▼               ▼                          │
│      ┌────────────┐   ┌────────────┐   ┌────────────┐                  │
│      │ YOUR FORK  │   │ DEVIN API  │   │  UPSTREAM  │                  │
│      │ (GitHub)   │   │            │   │  (GitHub)  │                  │
│      │            │   │ - Create   │   │            │                  │
│      │ - Issues   │   │ - Monitor  │   │ - Source   │                  │
│      │ - PRs      │   │ - Status   │   │   issues   │                  │
│      └────────────┘   └────────────┘   └────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- Docker/Podman (for containerized deployment)
- GitHub Personal Access Token (with repo permissions)
- Devin API Key (PAT) and Organization ID
- A fork of `apache/superset` in your GitHub account (with Issues enabled)

## Quick Start

### Option 1: Podman (Recommended - No License Required)

```bash
# 1. Clone this repository
git clone https://github.com/your-username/devin-automation.git
cd devin-automation

# 2. Copy environment template and fill in your credentials
cp .env.example .env
# Edit .env with your GITHUB_TOKEN, DEVIN_API_KEY, DEVIN_ORG_ID, FORK_REPO

# 3. Initialize and start Podman machine (first time only)
podman machine init
podman machine start

# 4. Start the system
# On Linux:
podman-compose up --build

# On Windows/macOS:
podman-compose -f docker-compose.windows.yml up --build

# 5. Open dashboard
open http://localhost:8000
```

### Option 2: Docker

```bash
# 1. Clone this repository
git clone https://github.com/your-username/devin-automation.git
cd devin-automation

# 2. Copy environment template and fill in your credentials
cp .env.example .env
# Edit .env with your GITHUB_TOKEN, DEVIN_API_KEY, DEVIN_ORG_ID, FORK_REPO

# 3. Start the system
docker-compose up --build

# 4. Open dashboard
open http://localhost:8000
```

### Option 3: Local Development

```bash
# 1. Clone this repository
git clone https://github.com/your-username/devin-automation.git
cd devin-automation

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template and fill in your credentials
cp .env.example .env
# Edit .env with your GITHUB_TOKEN, DEVIN_API_KEY, DEVIN_ORG_ID, FORK_REPO

# 5. Run the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Open dashboard
open http://localhost:8000
```

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `GITHUB_TOKEN` | GitHub Personal Access Token | Yes | - |
| `DEVIN_API_KEY` | Devin API Key (PAT) | Yes | - |
| `DEVIN_ORG_ID` | Devin Organization ID (for v3 API) | Yes | - |
| `FORK_REPO` | Your fork (e.g., `your-username/superset`) | Yes | - |
| `UPSTREAM_REPO` | Source repo | No | `apache/superset` |
| `POLL_INTERVAL_MINUTES` | How often to poll for pending issues | No | `5` |
| `MAX_ISSUES_PER_POLL` | Max issues to process per poll cycle | No | `5` |
| `MAX_CONCURRENT_SESSIONS` | Max simultaneous Devin sessions | No | `3` |
| `MAX_ISSUES_TO_CLONE` | Max issues to clone during setup | No | `20` |

### Issue Selection Criteria

During **Setup**, issues are selected from upstream based on:
- State: `open`
- Label: `#bug`
- No linked Pull Request
- Limit: `MAX_ISSUES_TO_CLONE` (default 20)

During **Polling**, issues are picked from your fork based on:
- Label: `devin-pending`
- Limit: `min(MAX_ISSUES_PER_POLL, MAX_CONCURRENT_SESSIONS - active_sessions)`

## API Endpoints

### Dashboard
- `GET /` - Web UI with controls and real-time status

### Control Endpoints
- `POST /api/setup` - Clone issues from upstream to your fork
- `POST /api/run` - Manually trigger issue processing
- `POST /api/teardown` - Reset fork for next demo

### Status Endpoints
- `GET /api/status` - Current system status (JSON)
- `GET /api/sessions` - List all Devin sessions
- `GET /api/sessions/{id}` - Get specific session details
- `GET /api/issues` - List all tracked issues

## Demo Flow

### 1. Setup
Click "Setup" button or call:
```bash
curl -X POST http://localhost:8000/api/setup
```
This clones open bug issues from `apache/superset` to your fork.

### 2. Run
Either wait for automatic polling, or click "Run Now" / call:
```bash
curl -X POST http://localhost:8000/api/run
```
Devin picks up pending issues and creates PRs.

### 3. Observe
Watch the dashboard for:
- Issues being processed
- Devin sessions starting/completing
- PRs being created
- Success/failure metrics

### 4. Validate
- View PRs in your GitHub fork
- Check CI status
- Merge PRs to prove quality

### 5. Teardown
Click "Teardown" button or call:
```bash
curl -X POST http://localhost:8000/api/teardown
```
This resets Devin's work for the next demo run:
- Closes Devin's PRs
- Deletes Devin's feature branches
- Resets issue labels back to `devin-pending`
- Clears session data (keeps issue records)

**Note:** Issues are NOT deleted. They remain in your fork so you can run multiple demos without re-cloning from upstream.

## Observability Dashboard

The web UI provides:

### Controls
- **Setup** - Initialize by cloning issues
- **Run Now** - Manually trigger processing
- **Teardown** - Reset for next demo

### Metrics
- Issues Pending / In Progress / Completed
- PRs Created / Merged
- Success Rate
- Average Time to Fix

### Activity Log
- Real-time feed of system events
- Links to GitHub issues and PRs
- Devin session status updates

## Project Structure

```
devin-automation/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── models.py            # Database models
│   ├── database.py          # Database setup and session management
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── api.py           # API endpoints
│   │   └── dashboard.py     # Dashboard routes
│   ├── services/
│   │   ├── __init__.py
│   │   ├── github_service.py    # GitHub API integration
│   │   ├── devin_service.py     # Devin API integration
│   │   ├── orchestrator.py      # Main orchestration logic
│   │   └── scheduler.py         # Background polling scheduler
│   ├── templates/
│   │   └── dashboard.html   # Web UI template
│   └── static/
│       └── style.css        # Dashboard styles
├── tests/
│   ├── __init__.py
│   ├── test_github_service.py
│   ├── test_devin_service.py
│   └── test_orchestrator.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## How It Works

### Setup Phase
1. Query `apache/superset` for open issues with `#bug` label and no linked PR
2. For each issue (up to `MAX_ISSUES_TO_CLONE`):
   - Create a copy in your fork
   - Add labels: `cloned`, `devin-pending`
   - Store in local database
3. Return summary of cloned issues

### Processing Phase (Poll/Run)
1. Check available capacity: `MAX_CONCURRENT_SESSIONS - active_sessions`
2. Query fork for issues with `devin-pending` label
3. For each issue (up to capacity and `MAX_ISSUES_PER_POLL`):
   - Update label to `devin-working`
   - Create Devin session via API with prompt containing:
     - Issue title and description
     - Repository URL (your fork)
     - Instructions to fix and create PR
   - Store session ID in database
4. Monitor active sessions:
   - Poll Devin API for status updates
   - When complete, update issue label to `devin-done`
   - Record PR URL if created

### Teardown Phase
1. Close all open PRs created by Devin
2. Delete Devin's feature branches
3. Reset issue labels: `devin-working`/`devin-done`/`devin-failed` → `devin-pending`
4. Clear Devin session records (keep issue records)
5. Ready to run again with same issues

## Devin Prompt Template

When triggering Devin, the system uses this prompt structure:

```
Fix the following bug in the repository {fork_repo}:

## Issue Title
{issue_title}

## Issue Description
{issue_body}

## Instructions
1. Clone the repository
2. Analyze the issue and identify the root cause
3. Implement a fix following the project's coding standards
4. Write or update tests if applicable
5. Create a pull request with:
   - Clear title referencing the issue
   - Description of the fix
   - Any relevant notes for reviewers

Repository: https://github.com/{fork_repo}
Branch to target: main
```

## Troubleshooting

### Common Issues

**"GitHub rate limit exceeded"**
- Use a token with higher rate limits
- Reduce `POLL_INTERVAL_MINUTES`

**"Devin session failed"**
- Check Devin API key is valid
- Review session logs via `/api/sessions/{id}`
- Some issues may be too complex for automated fixing

**"Setup found no issues"**
- Upstream may not have bugs without PRs at this time
- Check `apache/superset` issues manually
- Adjust label filter if needed

### Viewing Logs

You can monitor what the system is doing in real-time by tailing the container logs.

#### Follow all logs (real-time):
```bash
# Podman
podman logs -f devin-automation

# Docker Compose
docker-compose logs -f
```

#### View recent logs:
```bash
# Last 50 lines
podman logs --tail 50 devin-automation

# Last 100 lines
podman logs --tail 100 devin-automation
```

#### What to look for during each action:

**Setup logs:**
```
INFO - Starting setup: cloning issues from upstream
INFO - Cloned issue #43576 to fork as #1
INFO - Cloned issue #43574 to fork as #2
...
INFO - Setup complete. Cloned 6 issues.
```

**Run logs:**
```
INFO - Starting run: processing pending issues
INFO - Processing issue #1: Guest embedded dashboard...
INFO - Updated labels on issue #1
INFO - HTTP Request: POST https://api.devin.ai/.../sessions "HTTP/1.1 200 OK"
INFO - Created Devin session 20927773c3e047f3b5459f1a339b8cde for issue #1
...
INFO - Run complete. Processed 3 issues.
```

**Session completion logs:**
```
INFO - Devin session 20927773c3e047f3b5459f1a339b8cde completed successfully
INFO - Updated labels on issue #1
```

**Teardown logs:**
```
INFO - Starting teardown - resetting Devin's work only
INFO - Closed PR #8
INFO - Deleted branch: devin/1788151924-fix-guest-scalar-column
INFO - Updated labels on issue #1
...
INFO - Teardown complete. Reset 6 issues to pending. Closed 6 PRs.
```

#### Scheduler/Polling logs:
```
INFO - Scheduler: Starting poll cycle
INFO - HTTP Request: GET https://api.devin.ai/.../sessions/... "HTTP/1.1 200 OK"
INFO - Scheduler: Poll complete - {'status': 'skipped', 'message': 'At capacity: 3 active sessions'}
```

## License

MIT License - See LICENSE file for details.

## Acknowledgments

- [Apache Superset](https://github.com/apache/superset) - The target repository
- [Devin](https://devin.ai/) - The AI coding agent
- Built for the Cognition AI take-home assignment
