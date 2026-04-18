"""
RSS Reader Plugin Handler
讀取 RSS/Atom Feed 並回傳最新文章列表
config: {}（無需設定）
params: {url: "https://...", limit: 10}
"""
import logging
import httpx
import re
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()[:500]


async def run(action: str, params: dict, config: dict) -> dict:
    url   = params.get("url", "")
    limit = min(int(params.get("limit", 10)), 20)

    if not url:
        return {"success": False, "error": "缺少 url 參數（RSS Feed URL）"}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "AI-KB-RSS-Reader/1.0"})
            resp.raise_for_status()
    except Exception as e:
        return {"success": False, "error": f"無法取得 RSS Feed: {e}"}

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        return {"success": False, "error": f"RSS 解析失敗: {e}"}

    items = []

    # RSS 2.0
    for item in root.findall(".//item")[:limit]:
        items.append({
            "title":   item.findtext("title", "").strip(),
            "link":    item.findtext("link", "").strip(),
            "summary": _strip_html(item.findtext("description", "")),
            "pub_date": item.findtext("pubDate", ""),
        })

    # Atom
    if not items:
        for entry in root.findall(".//atom:entry", _NS)[:limit]:
            link = ""
            link_el = entry.find("atom:link", _NS)
            if link_el is not None:
                link = link_el.get("href", "")
            items.append({
                "title":   (entry.findtext("atom:title", "", _NS) or "").strip(),
                "link":    link,
                "summary": _strip_html(entry.findtext("atom:summary", "", _NS)),
                "pub_date": entry.findtext("atom:updated", "", _NS),
            })

    if not items:
        return {"success": False, "error": "未能從 Feed 解析出任何文章"}

    return {"success": True, "data": {"source": url, "count": len(items), "items": items}}
