"""Temporary PR-only probe for The Paper's current public cursor API.

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
TARGET_BY_NODE = {
    25462: "33664738",
    25448: "33660139",
}


def _item_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "contId": str(item.get("contId", "")),
        "name": str(item.get("name", ""))[:160],
        "pubTime": item.get("pubTime"),
        "pubTimeNew": item.get("pubTimeNew"),
        "pubTimeLong": item.get("pubTimeLong"),
        "publishTime": item.get("publishTime"),
        "link": item.get("link"),
    }


async def probe_node(client: httpx.AsyncClient, node_id: int) -> dict[str, Any]:
    target = TARGET_BY_NODE[node_id]
    pages: list[dict[str, Any]] = []
    cursor: int | None = None
    seen_cursors: set[int] = set()
    target_item: dict[str, Any] | None = None

    for page in range(1, 13):
        payload: dict[str, Any] = {"nodeId": node_id, "pageSize": 20}
        if cursor is not None:
            payload["startTime"] = cursor
        try:
            response = await client.post(ENDPOINT, json=payload)
            body = response.text
            page_record: dict[str, Any] = {
                "page": page,
                "payload": payload,
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "length": len(body),
                "target_in_body": target in body,
            }
            try:
                parsed = response.json()
            except ValueError:
                page_record["text_preview"] = body[:800]
                pages.append(page_record)
                break

            data = parsed.get("data") if isinstance(parsed, dict) else None
            items = data.get("list", []) if isinstance(data, dict) else []
            next_cursor = data.get("startTime") if isinstance(data, dict) else None
            page_record.update(
                {
                    "code": parsed.get("code") if isinstance(parsed, dict) else None,
                    "hasNext": data.get("hasNext") if isinstance(data, dict) else None,
                    "startTime": next_cursor,
                    "items_count": len(items),
                    "first_item": _item_summary(items[0]) if items else None,
                    "last_item": _item_summary(items[-1]) if items else None,
                    "target_hits": [
                        _item_summary(item)
                        for item in items
                        if str(item.get("contId", "")) == target
                    ],
                }
            )
            pages.append(page_record)
            if page_record["target_hits"]:
                target_item = page_record["target_hits"][0]
                break
            if not data or not data.get("hasNext") or not next_cursor:
                break
            next_cursor = int(next_cursor)
            if next_cursor in seen_cursors or next_cursor == cursor:
                page_record["stopped_reason"] = "repeated_cursor"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        except Exception as exc:
            pages.append(
                {
                    "page": page,
                    "payload": payload,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                }
            )
            break
        await asyncio.sleep(0.5)

    return {
        "node_id": node_id,
        "target_id": target,
        "target_found": target_item is not None,
        "target_item": target_item,
        "pages": pages,
    }


async def main() -> None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.thepaper.cn",
        "Referer": "https://www.thepaper.cn/",
    }
    limits = httpx.Limits(max_connections=2, max_keepalive_connections=2)
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(headers=headers, timeout=20, limits=limits) as client:
        for node_id in TARGET_BY_NODE:
            results.append(await probe_node(client, node_id))
            await asyncio.sleep(2.0)

    result = {
        "endpoint": ENDPOINT,
        "nodes": results,
        "targets_found": sum(node["target_found"] for node in results),
        "targets_total": len(results),
    }
    path = Path("artifacts/thepaper-api-probe-v056.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
