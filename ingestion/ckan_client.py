import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger()


class CKANClient:
    def __init__(self, base_url: str, timeout: int, max_retries: int) -> None:
        self._base_url = base_url.rstrip("/")
        # Split timeout: connect must succeed quickly; reads can take longer
        # because CKAN package_show on large datasets can take 60-90 s.
        self._timeout = httpx.Timeout(connect=10.0, read=float(timeout), write=10.0, pool=5.0)
        self._max_retries = max_retries

    def get_resources(self, dataset_id: str) -> list[dict]:
        return self._get_resources(dataset_id)

    def download_resource(self, resource_url: str) -> bytes:
        return self._download_resource(resource_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
    def _get_resources(self, dataset_id: str) -> list[dict]:
        url = f"{self._base_url}/package_show"
        log.info("ckan_get_resources", url=url, dataset_id=dataset_id)
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(url, params={"id": dataset_id})
            response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            raise RuntimeError(f"CKAN error: {data.get('error')}")
        return data["result"]["resources"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
    def _download_resource(self, resource_url: str) -> bytes:
        log.info("ckan_download_resource", url=resource_url)
        with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
            response = client.get(resource_url)
            response.raise_for_status()
        return response.content
