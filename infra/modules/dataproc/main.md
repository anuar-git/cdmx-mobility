# infra/modules/dataproc/main.tf

## What it does

Provisions a Dataproc **Workflow Template** for ephemeral PySpark cluster jobs. The workflow template creates a managed cluster on demand, runs the specified PySpark job, and tears down the cluster automatically — no persistent cluster costs.

## Resources

### `google_dataproc_workflow_template.spark_job`

**Template name:** `cdmx-spark-job`

**Cluster config (`cdmx-ephemeral`):**

| Component | Config |
|---|---|
| Zone | `us-central1-a` |
| Service account | `cdmx-pipeline-sa` |
| Master | 1× `n2-standard-2`, 50 GB standard disk |
| Workers | 2× `n2-standard-2`, 50 GB standard disk |
| Image | Dataproc `2.2-debian12` |
| Zero-worker clusters | Disabled |

**Job step:**

A single PySpark job step (`spark-job`) pointing to `gs://cdmx-mobility-data/code/placeholder.py`. This is a placeholder — the actual Spark job code in `spark_jobs/` is not yet deployed.

**Timeout:** 3600s (1 hour).

## Status

This is a **placeholder**. The Dataproc workflow template is provisioned to reserve the infrastructure pattern, but the PySpark jobs in [`spark_jobs/`](../../../spark_jobs/) are not yet implemented or deployed.

## How it ties with the rest of the project

- **[infra/modules/iam/main.tf](../iam/main.tf)** — `cdmx-pipeline-sa` has `roles/dataproc.worker`, required for the ephemeral cluster nodes.
- **[spark_jobs/](../../../spark_jobs/)** — Future PySpark job code. When ready, the `main_python_file_uri` here should point to the uploaded job file.
- **[infra/main.tf](../../main.tf)** — Passes `project_id`, `region`, and `service_account_email` (from `module.iam`) into this module.
