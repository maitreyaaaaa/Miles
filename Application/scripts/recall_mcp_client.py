"""
Recall.ai MCP Client for interacting with the Recall MCP server over HTTP.
Supports tools/list, tools/call, resources/list, and resources/read.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

RECALL_MCP_DEFAULT_URL = "https://ap-northeast-1.recall.ai/mcp"

class RecallMcpClient:
    def __init__(self, token: Optional[str] = None, base_url: str = RECALL_MCP_DEFAULT_URL):
        self.base_url = base_url.rstrip("/")
        self.token = token or os.getenv("RECALL_MCP_API_KEY") or os.getenv("RECALL_AI_API_KEY") or ""
        self._request_id = 0

    @property
    def headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def rpc_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.base_url, json=payload, headers=self.headers)
            if resp.status_code == 401:
                raise PermissionError("Recall.ai MCP 401 Unauthorized: Invalid or missing token.")
            if resp.status_code != 200:
                raise RuntimeError(f"Recall.ai MCP Error ({resp.status_code}): {resp.text}")
            
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"Recall.ai MCP RPC Error: {data['error']}")
            return data.get("result", {})

    async def initialize(self) -> Dict[str, Any]:
        return await self.rpc_call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "miles-ai-agent", "version": "1.0.0"},
            },
        )

    async def list_tools(self) -> List[Dict[str, Any]]:
        res = await self.rpc_call("tools/list")
        return res.get("tools", [])

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        res = await self.rpc_call("tools/call", {"name": name, "arguments": arguments or {}})
        return res

    async def list_resources(self) -> List[Dict[str, Any]]:
        res = await self.rpc_call("resources/list")
        return res.get("resources", [])

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        res = await self.rpc_call("resources/read", {"uri": uri})
        return res

    async def get_info(self) -> Dict[str, Any]:
        return await self.call_tool("get_info")

if __name__ == "__main__":
    import asyncio
    async def main():
        token = sys.argv[1] if len(sys.argv) > 1 else os.getenv("RECALL_MCP_API_KEY", "")
        client = RecallMcpClient(token=token)
        print("Testing Recall MCP connection...")
        try:
            init_res = await client.initialize()
            print("Initialized:", init_res)
            info = await client.get_info()
            print("Workspace Info:", info)
            guide = await client.read_resource("recall://guides/onboarding")
            print("Onboarding Guide:", str(guide)[:300])
        except Exception as e:
            print("Error:", e)
    asyncio.run(main())
