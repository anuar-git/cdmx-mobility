from google.cloud import storage


class GCSUploader:
    def __init__(self, bucket_name: str) -> None:
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def upload(self, data: bytes, gcs_path: str, content_type: str = "text/csv") -> str:
        blob = self._bucket.blob(gcs_path)
        blob.upload_from_string(data, content_type=content_type)
        return f"gs://{self._bucket.name}/{gcs_path}"

    def exists(self, gcs_path: str) -> bool:
        return self._bucket.blob(gcs_path).exists()
