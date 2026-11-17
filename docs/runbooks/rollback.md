# Operational Runbook: Rollback Procedures

## Overview
This runbook details step-by-step procedures for safely rolling back the ARAA (Autonomous Research & Analysis Agent) platform during production incidents or failed deployments.

---

## 1. Quick Emergency Rollback (Docker & Kubernetes)

### Docker Compose
```bash
# 1. Stop current containers
docker compose down

# 2. Re-deploy previous stable tag
export ARAA_IMAGE_TAG="v0.1.0-stable"
docker compose up -d
```

### Kubernetes / Helm
```bash
# View deployment revision history
kubectl rollout history deployment/araa-api -n araa

# Roll back immediately to the previous revision
kubectl rollout undo deployment/araa-api -n araa

# Verify rollout status
kubectl rollout status deployment/araa-api -n araa
```

---

## 2. Database Migration Rollback (PostgreSQL / Alembic)
If a database schema migration introduced locks, performance degradation, or errors:

```bash
# 1. Identify current revision
alembic current

# 2. Downgrade one revision
alembic downgrade -1

# 3. Verify database integrity
python -m scripts.scaffold check_db
```

---

## 3. Worker Crash & Orphaned Run Recovery
If workers crashed during a deployment:
1. Dead worker leases will expire automatically after `lease_duration_seconds` (default: 60s).
2. The newly deployed `AgentWorker` pool automatically scans for zombie runs via `recover_zombies()`:
   ```bash
   python -c "from app.workers.run_worker import AgentWorker; import asyncio; w = AgentWorker(); asyncio.run(w.recover_zombies())"
   ```
3. Runs will resume execution idempotently without duplicating executed external side effects.

---

## 4. Post-Rollback Health Verification
Execute health probes to ensure system stability:
```bash
curl -f http://localhost:8000/health
curl -f http://localhost:8000/ready
```
