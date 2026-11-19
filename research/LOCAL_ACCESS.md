# Local Access And Reference Inspection

This document describes a safe local connection path for the Autogration V2
research workspace. It is intentionally read-only with respect to runs, results,
assumptions, and CDF. It does not copy credentials into this repository.

## Workspace

Open [AutogrationV2.code-workspace](../AutogrationV2.code-workspace) in VS Code.
It contains:

- this research repository;
- the Autogration backend and node client repository;
- the Autogration frontend repository; and
- the Autogration infrastructure repository.

Each remains its own Git repository. Do not move source code or create Git
submodules merely to make cross-repository work easier.

## Git Status

This repository uses `main` and tracks:

```text
origin: https://github.com/Im2ql4u/AutogrationV2
```

The initial commit is published. Local research changes remain uncommitted until
they are reviewed and intentionally committed.

## Existing Read-Only Data Access

The backend already exposes data needed for broad reference-corpus inspection:

| Need | Local backend endpoint |
| --- | --- |
| List runs | `GET /api/v1/runs/?limit=...` |
| Inspect task metadata | `GET /api/v1/tasks/?task_id=...` |
| Download full data exchange bundle | `GET /api/v1/runs/{task_id}` |
| Download results as JSON | `GET /api/v1/runs/{task_id}/results` |
| Download results as Parquet | `GET /api/v1/runs/{task_id}/results/parquet` |
| Download applied assumptions | `GET /api/v1/runs/{task_id}/assumptions` |
| Inspect task logs | `GET /api/v1/tasks/{task_id}/logs` |
| List CDF assets through the backend | `GET /api/v1/assets/` |

The data-exchange bundle is the preferred starting artifact for offline
analysis because it carries the registered model context, applied assumptions,
and result together.

## Read-Only Client

Use [scripts/inspect-autogration.ps1](../scripts/inspect-autogration.ps1). It
only makes HTTP `GET` requests and writes optional downloads under `artifacts/`,
which is ignored by Git.

Some Windows environments block local PowerShell scripts by default. Before
using this client, enable a bypass for the current terminal session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
```

This does not change the machine-wide execution policy.

```powershell
# Check that the local backend is reachable.
.\scripts\inspect-autogration.ps1 -Mode Status

# List recent runs.
.\scripts\inspect-autogration.ps1 -Mode Runs -Limit 25

# Inspect one task's metadata and logs.
.\scripts\inspect-autogration.ps1 -Mode Task -TaskId <task-id>
.\scripts\inspect-autogration.ps1 -Mode Logs -TaskId <task-id>

# Download one complete run, its assumptions, or Parquet results.
.\scripts\inspect-autogration.ps1 -Mode Bundle -TaskId <task-id>
.\scripts\inspect-autogration.ps1 -Mode Assumptions -TaskId <task-id>
.\scripts\inspect-autogration.ps1 -Mode ResultsParquet -TaskId <task-id>

# Check CDF connectivity through the existing backend-owned CDF client.
.\scripts\inspect-autogration.ps1 -Mode CdfAssets
```

Set `AUTOGRATION_API_URL` or pass `-ApiBaseUrl` when the backend is not running
at `http://localhost:5201/api/v1`.

## Local Stack

The expected local path is:

```text
Frontend Vite server :5174
  -> /api proxy
Backend FastAPI/Socket.IO :5201
  -> PostgreSQL :5432, Azurite, local file/archive services
```

The backend workspace dependencies have been synchronized with `uv sync
--frozen`. The frontend already has a Vite setup that proxies to the backend
target declared in its local environment configuration.

Before a live inspection session, start the stack through the existing
Autogration launch configuration or its local-development instructions. The
backend launch configuration starts Azurite and PostgreSQL as prerequisites.
The frontend development server is started from the frontend repository with:

```powershell
npm.cmd run dev
```

## Current Readiness Constraints

At the time this document was created:

- Docker is installed, but the Docker Desktop Linux engine returned an API error.
  PostgreSQL and Azurite cannot be started until that is repaired.
- No expected local listener was active for the backend, frontend, PostgreSQL,
  or Azurite.
- The current shell did not expose the CDF OAuth settings required by the backend
  CDF client.

The CDF client used by the backend requires configured values for the CDF project
and cluster, Azure tenant, client ID, and client secret. Enter or obtain those
through the approved local secret-management path directly on the machine. Do
not paste them into chat, commit them, or copy them into this repository.

## CDF Boundary

The existing backend owns a Cognite SDK client and already exports completed
simulation results to CDF. The `CdfAssets` command tests that approved backend
path through the read-only asset-list endpoint.

There is not yet a general backend endpoint for reading arbitrary CDF results or
ensembles back into the research workspace. Direct CDF querying should therefore
be treated as a future **read-only CDF adapter** that reuses the backend's
approved authentication/configuration boundary. It should:

- expose only scoped read operations at first;
- record the CDF dataset, asset, ensemble, and task reference for every result;
- avoid copying OAuth credentials into analysis scripts; and
- distinguish CDF-exported records from locally retained task evidence.

Until that adapter exists, use the local task/run endpoints for full bundles and
use CDF through the existing backend path to verify exported asset availability.

## Reference-Corpus Caveats

Historic runs are useful evidence, not automatically a clean analysis or ML
dataset. Before comparing them, classify model version/provenance, assumptions,
result schema, task quality, and retention state.

In particular, task logs have a 90-day retention policy, task execution files
may be cleaned after completion, and CDF is an external archive with its own
lifecycle. The final result bundle, assumption set, registered model relationship,
and task metadata should be captured together whenever a run is promoted into a
reference corpus.