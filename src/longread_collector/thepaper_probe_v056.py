"""Temporary PR-only probe for The Paper's current public list API.

This module is intentionally read-only. It does not use Firecrawl, write Sheets,
or touch production caches. Remove it after the request contract is identified.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

ENDPOINT = "https://api.thepaper.cn/contentapi/nodeCont/getByNodeIdPortal"
TARGET_IDS = {"33664738", "33660139"}
NODE_IDS = (25462, 25448)

PAYLOAD_FACTORIES = (
    lambda node, page: {"nodeId": node, "pageNum": page, "pageSize": 20},
    lambda node, page: {"nodeId": str(node), "pageNum": page, "pageSize": 20},
    lambda node, page: {"nodeId": node, "pageNo": page, "pageSize": 20},
    lambda node, page: {"nodeId": node, "page": page, "size": 20},
    lambda node, page: {"nodeId": node, "pageIndex": page, "pageSize": 20},
    lambda node, page: {"nodeId": node, "start": (page - 1) * 20, "limit": 20},
    lambda node, page: {"nodeId": node, "offset": (page - 1) * 20, "limit": 20},
    lambda node, page: {
        "nodeId": node,
        "pageNum": page,
        "pageSize": 20,
        "excludeContIds": [],
    },
)


def _compact(value: Any, limit: int = 1200) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text[:limit]


async def main() -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.thepaper.cn",
        "Referer": "https://www.thepaper.cn/",
    }
    records: list[dict[str, Any]] = []
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
    async with httpx.AsyncClient(headers=headers, timeout=20, limits=limits) as client:
        for node_id in NODE_IDS:
            for page in range(1, 5):
                for index, factory in enumerate(PAYLOAD_FACTORIES, start=1):
                    payload = factory(node_id, page)
                    for encoding in ("json", "form"):
                        record: dict[str, Any] = {
                            "node_id": node_id,
                            "page": page,
                            "variant": index,
                            "encoding": encoding,
                            "payload": payload,
                        }
                        try:
                            kwargs = {encoding: payload}
                            response = await client.post(ENDPOINT, **kwargs)
                            body = response.text
                            record.update(
                                {
                                    "status": response.status_code,
                                    "content_type": response.headers.get(
                                        "content-type", ""
                                    ),
                                    "length": len(body),
                                    "target_hits": sorted(
                                        target for target in TARGET_IDS if target in body
                                    ),
                                }
                            )
                            try:
                                parsed = response.json()
                                record["json_preview"] = _compact(parsed)
                            except ValueError:
                                record["text_preview"] = body[:1200]
                        except Exception as exc:
                            record.update(
                                {
                                    "error_type": type(exc).__name__,
                                    "error_message": str(exc)[:500],
                                }
                            )
                        records.append(record)

    useful = [
        record
        for record in records
        if record.get("target_hits")
        or int(record.get("length") or 0) > 200
        or record.get("status") not in {400, 404, 405, 415, 422}
    ]
    result = {
        "endpoint": ENDPOINT,
        "attempts": len(records),
        "useful_attempts": useful,
        "target_ids": sorted(TARGET_IDS),
    }
    path = Path("artifacts/thepaper-api-probe-v056.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
