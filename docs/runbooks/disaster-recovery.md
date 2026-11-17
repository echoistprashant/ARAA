# Operational Runbook: Disaster Recovery & Data Restoration

## 1. Objectives & RTO/RPO Targets
- **Recovery Time Objective (RTO):** < 15 minutes to full API availability.
- **Recovery Point Objective (RPO):** < 5 minutes of checkpointed research runs.

---

## 2. Infrastructure Backup Architecture
- **PostgreSQL Database:**
  - WAL (Write-Ahead Logging) archiving with daily base backups.
  - Snapshot copies stored across availability zones.
- **Redis Cache:**
  - AOF (Append-Only File) enabled with `appendfsync everysec`.
  - Ephemeral cache; can be reconstructed on failure without data loss.

---

## 3. PostgreSQL Restoration Procedure
```bash
# 1. Stop write traffic by putting API in maintenance mode
kubectl scale deployment/araa-api --replicas=0 -n araa

# 2. Restore database dump
pg_restore -U araa_user -d araa_prod -h postgres_host -v /backups/araa_backup_latest.dump

# 3. Verify pgvector extension
psql -U araa_user -d araa_prod -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

# 4. Scale API pods back up
kubectl scale deployment/araa-api --replicas=3 -n araa
```

---

## 4. Incident Response Checklist
1. [ ] Acknowledge incident in monitoring channel.
2. [ ] Isolate degraded worker pods to prevent cascading retries.
3. [ ] Verify PostgreSQL connection pool health and available disk space.
4. [ ] Initiate rollback or database restore as prescribed above.
5. [ ] Execute smoke test suite: `python scripts/run_eval.py`.
6. [ ] Broadcast resolution and conduct blameless post-mortem.
