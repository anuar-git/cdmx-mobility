import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class GBFSClient:
    def __init__(self, base_url: str, timeout: int, max_retries: int, api_key: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._api_key = api_key

    def fetch(self, feed_name: str) -> dict:
        return self._fetch(feed_name)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
    def _fetch(self, feed_name: str) -> dict:
        url = f"{self._base_url}/{feed_name}.json"
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
        return response.json()
