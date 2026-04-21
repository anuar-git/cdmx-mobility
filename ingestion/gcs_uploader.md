# ingestion/gcs_uploader.py

## What it does

`GCSUploader` is the single GCS write primitive used by all ingestors. It wraps the `google-cloud-storage` client with one method:

```python
upload(data: bytes, gcs_path: str, content_type: str = "text/csv") -> str
```

- Writes `data` to `gs://{bucket_name}/{gcs_path}` with the specified content type.
- Returns the full `gs://` URI of the uploaded object (used for structured logging).

All GCS paths follow **Hive partitioning** conventions defined per ingestor:

| Ingestor | Path pattern | Content type |
|---|---|---|
| Metro affluence | `metro/affluence/ingestion_date=YYYY-MM-DD/{filename}.csv` | `text/csv` |
| EcoBici (dynamic feeds) | `ecobici/{feed}/ingestion_ts=YYYY-MM-DDTHH-MM/{feed}.json` | `application/json` |
| EcoBici (static feeds) | `ecobici/{feed}/ingestion_date=YYYY-MM-DD/{feed}.json` | `application/json` |
| Metrobús GTFS static | `metrobus/static/{feed}/ingestion_date=YYYY-MM-DD/{feed}.csv` | `text/csv` |
| Metrobús GTFS-RT (protobuf) | `metrobus/vehicle_positions_raw/ingestion_date=YYYY-MM-DD/vp_{epoch_ms}.pb` | `application/octet-stream` |
| Metrobús GTFS-RT (NDJSON) | `metrobus/vehicle_positions/ingestion_date=YYYY-MM-DD/vp_{epoch_ms}.ndjson` | `application/x-ndjson` |

## Tools used

- **[google-cloud-storage](https://cloud.google.com/python/docs/reference/storage/latest)** — `storage.Client()` using Application Default Credentials; `bucket.blob().upload_from_string()` for the write.

## How it ties with the rest of the project

- **[ingestion/metro/affluence.py](metro/affluence.py)**, **[ingestion/ecobici/gbfs.py](ecobici/gbfs.py)**, **[ingestion/metrobus/gtfs_static.py](metrobus/gtfs_static.py)**, **[ingestion/metrobus/gtfs_rt.py](metrobus/gtfs_rt.py)** — All four ingestors import and use `GCSUploader` as their only GCS write mechanism.
- **[infra/modules/storage/main.tf](../infra/modules/storage/main.tf)** — Provisions the `cdmx-mobility-data` bucket that this class writes to, including lifecycle rules for the paths above.
- **[infra/modules/bigquery/main.tf](../infra/modules/bigquery/main.tf)** — BigQuery external tables point to the same GCS paths that `GCSUploader` writes to.
- **[tests/ingestion/test_gcs_uploader.py](../tests/ingestion/test_gcs_uploader.py)** — Unit tests verifying the `gs://` URI format and blob path construction.
