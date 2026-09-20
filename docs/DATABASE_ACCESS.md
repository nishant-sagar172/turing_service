# Connecting to the Production Database

The production PostgreSQL database runs inside Docker on the GCP VM
(`turing`). It is **not** exposed to the internet — access is only
possible through an SSH tunnel.

---

## Prerequisites

- **gcloud CLI** installed and authenticated (`gcloud auth login`)
- **SSH access** to the `turing` VM (GCP IAM permissions)
- **pgAdmin** (or any Postgres client — DBeaver, DataGrip, psql, etc.)

---

## Step 1: Open an SSH tunnel

Run this on your **local machine** (keep the terminal open):

```bash
gcloud compute ssh turing --zone=asia-south2-b -- -L 5433:127.0.0.1:5432 -N
```

This forwards your local port `5433` to the VM's internal postgres port
`5432` through an encrypted SSH connection.

> **Note:** If you get a zone error, find the correct zone with:
> ```bash
> gcloud compute instances list --filter="name=turing"
> ```

---

## Step 2: Connect pgAdmin

Create a new server in pgAdmin with these settings:

| Field | Value |
|---|---|
| **Name** | Turing Prod (anything you like) |
| **Host** | `localhost` |
| **Port** | `5433` |
| **Maintenance database** | `turing_db` |
| **Username** | `turing` |
| **Password** | *(the TURING_PG_PASSWORD from .env.prod)* |

Click **Save**. You should see `turing_db` with all the tables.

---

## Step 3: Done

Browse schemas, run queries, export data — everything works as if
postgres were running locally. The tunnel encrypts all traffic.

**To disconnect:** close the terminal running the SSH tunnel, or press
`Ctrl+C`.

---

## Other clients

### psql (command line)

With the tunnel open:

```bash
psql -h localhost -p 5433 -U turing -d turing_db
```

### DBeaver / DataGrip

Same connection details as pgAdmin above:
`localhost:5433`, database `turing_db`, user `turing`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Connection refused` on 5433 | Make sure the SSH tunnel terminal is still open |
| `Permission denied (publickey)` | Run `gcloud auth login` and try again |
| `bind: Address already in use` | Another tunnel is running on 5433. Kill it or use a different local port: `-L 5434:127.0.0.1:5432` |
| Tunnel connects but pgAdmin times out | On the VM, check postgres is running: `docker ps \| grep postgres` |

---

## Security

- Postgres is bound to `127.0.0.1` on the VM — it is **never** reachable
  from the internet, even with GCP firewall rules.
- All access goes through GCP IAM (SSH) — only users with VM access can
  connect.
- No extra firewall rules are needed.
