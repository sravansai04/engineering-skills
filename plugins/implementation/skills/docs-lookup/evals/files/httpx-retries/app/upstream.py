import httpx

BASE_URL = "https://inventory.internal.example"


def make_client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=10.0)


def stock_level(client: httpx.Client, sku: str) -> int:
    resp = client.get(f"/stock/{sku}")
    resp.raise_for_status()
    return resp.json()["available"]
