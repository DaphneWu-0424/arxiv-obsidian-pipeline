from unittest.mock import patch
import requests
from requests.exceptions import ReadTimeout

from arxiv_client import ArxivClient


FAKE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678v1</id>
    <updated>2026-03-28T00:00:00Z</updated>
    <published>2026-03-27T00:00:00Z</published>
    <title>Test Paper Title</title>
    <summary>Test abstract here.</summary>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
"""


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=self
            )


def make_side_effect():
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        n = calls["count"]

        if n == 1:
            raise ReadTimeout("simulated timeout")

        if n in (2, 3):
            return FakeResponse(status_code=429, text="Too Many Requests")

        return FakeResponse(status_code=200, text=FAKE_XML)

    return fake_get, calls


def test_fetch_batch_chunk_retry_then_success():
    client = ArxivClient(
        timeout=1,
        min_interval_seconds=0,
        max_retries=4,
        backoff_seconds=0,
    )

    fake_get, calls = make_side_effect()

    with patch.object(client.session, "get", side_effect=fake_get):
        with patch("arxiv_client.time.sleep", return_value=None):
            papers = client._fetch_batch_chunk(["1234.5678"])

    assert calls["count"] == 4
    assert len(papers) == 1
    assert papers[0]["arxiv_id"] == "1234.5678"
    assert papers[0]["arxiv_id_raw"] == "1234.5678v1"
    assert papers[0]["title"] == "Test Paper Title"
    assert papers[0]["authors"] == ["Alice", "Bob"]
    assert papers[0]["categories"] == ["cs.AI"]


if __name__ == "__main__":
    test_fetch_batch_chunk_retry_then_success()
    print("测试通过：retry + 429 + timeout + parse 全部正常")