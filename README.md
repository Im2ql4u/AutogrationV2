# Autogration V2 workspace

This workspace holds the Autogration application, frontend, infrastructure,
research, and local developer tooling. The application folders are separate
clones of the AkerBP repositories (with their own remotes) and are ignored here;
this repository tracks the research, studies, handoffs and workspace settings.

## Layout

- `autogration/` - backend, node client, shared Python packages, and local services (clone)
- `autogration_frontend/` - React and Vite frontend (clone)
- `autogration-infrastructure/` - Terraform infrastructure (copy, not tracked)
- `research/` - architecture, product, and performance research
- `studies/` - study projects that drive Autogration, e.g. `studies/alvheim-tiein`
- `results-workbench/` - local results viewer (Streamlit)
- `handoff/` - status, open questions and work log of the Alvheim study, for review
- `ISSUES.md` - the Alvheim study's issue log; `REPORT.md`, `compare.md`, `comparison.md`
  are the model owner's handoff files with errata
- `.vscode/` - full-stack tasks, launch configurations, and workspace settings

Open `AutogrationV2.code-workspace` in VS Code. The **Full Stack: Start All** task
starts local services, applies database migrations, and launches the backend,
frontend, and node client. Individual install, start, and debug tasks are also
available from **Tasks: Run Task** and **Run and Debug**.

Local environments, dependencies, runtime storage, secrets, and Terraform state
are intentionally excluded from version control. Create local configuration from
the example files supplied by each application rather than committing credentials.

## Validation

```powershell
npm.cmd --prefix .\autogration_frontend\frontend ci --ignore-scripts
npm.cmd --prefix .\autogration_frontend\frontend run build
uv --directory .\autogration sync --frozen
uv --directory .\autogration run pytest -q
docker compose -f .\autogration\docker-compose.yml config --quiet
```