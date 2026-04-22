# infra/modules/storage/main.tf

## What it does

Provisions the GCS bucket `cdmx-mobility-data` — the raw data landing zone for all ingestors. Also creates placeholder `.keep` objects to establish visible "folder" structure in the GCS console.

## Resources

### `google_storage_bucket.data`

- **Storage class:** STANDARD (default; cost-optimized classes applied via lifecycle rules).
- **Versioning:** enabled — protects against accidental overwrites.
- **Uniform bucket-level access:** enabled — no ACLs, IAM-only access control.
- **`force_destroy = false`** — prevents accidental deletion of the bucket via `terraform destroy`.

### Lifecycle rules

| Prefix | Age (days) | Action |
|---|---|---|
| `raw/` | 90 | Move to COLDLINE |
| `staging/` | 7 | Delete |
| `metrobus/vehicle_positions_raw/` | 30 | Move to NEARLINE |

The `metrobus/vehicle_positions_raw/` rule handles the high-volume protobuf archive (~2,880 `.pb` files/day) cost-efficiently — NEARLINE is cheaper for infrequently accessed data while staying quickly retrievable.

### Placeholder objects

Three zero-content objects (`raw/.keep`, `staging/.keep`, `curated/.keep`) establish the top-level zone structure visibly in GCS console.

## Outputs

| Output | Value |
|---|---|
| `bucket_name` | The bucket name (passed to `module.bigquery` and `module.cloudrun`) |

## How it ties with the rest of the project

- **[infra/main.tf](../../main.tf)** — Instantiates this module; passes `bucket_name` to `module.bigquery`, `module.iam`, and `module.cloudrun`.
- **[ingestion/gcs_uploader.py](../../../ingestion/gcs_uploader.py)** — Writes to this bucket using `GCSUploader`.
- **[infra/modules/bigquery/main.tf](../bigquery/main.tf)** — External tables reference GCS paths inside this bucket.
- **[infra/modules/iam/main.tf](../iam/main.tf)** — Grants `roles/storage.objectAdmin` on this specific bucket to the pipeline service account.
