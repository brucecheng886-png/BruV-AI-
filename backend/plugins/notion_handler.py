"""
Notion Plugin Handler
支援動作: read_page | search | create_page
config 需要: notion_token（透過 auth_header 傳入）
"""
import logging
import httpx

logger = logging.getLogger(__name__)
NOTION_API = "https://api.notion.com/v1"


async def run(action: str, params: dict, config: dict) -> dict:
    token = config.get("notion_token", "")
    if not token:
        return {"success": False, "error": "缺少 notion_token，請在插件設定中填寫 Notion Integration Token"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if action == "read_page":
                return await _read_page(client, headers, params)
            elif action == "search":
                return await _search(client, headers, params)
            elif action == "create_page":
                return await _create_page(client, headers, params)
            elif action == "list_database":
                return await _list_database(client, headers, params)
            else:
                return {"success": False, "error": f"不支援的動作: {action}，可用: read_page / search / create_page / list_database"}
    except Exception as e:
        logger.error("Notion handler error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


async def _read_page(client, headers, params):
    page_id = params.get("page_id", "").replace("-", "")
    if not page_id:
        return {"success": False, "error": "缺少 page_id"}

    resp = await client.get(f"{NOTION_API}/pages/{page_id}", headers=headers)
    if not resp.is_success:
        return {"success": False, "error": f"Notion API {resp.status_code}: {resp.text[:200]}"}

    blocks_resp = await client.get(f"{NOTION_API}/blocks/{page_id}/children", headers=headers)
    page = resp.json()
    blocks = blocks_resp.json() if blocks_resp.is_success else {"results": []}

    # 取標題
    title = ""
    for val in page.get("properties", {}).values():
        if val.get("type") == "title":
            title = "".join(t.get("plain_text", "") for t in val.get("title", []))
            break

    # 取段落文字
    content_parts = []
    for block in blocks.get("results", []):
        btype = block.get("type", "")
        bdata = block.get(btype, {})
        text = "".join(t.get("plain_text", "") for t in bdata.get("rich_text", []))
        if text:
            content_parts.append(text)

    return {
        "success": True,
        "data": {
            "title": title,
            "content": "\n".join(content_parts),
            "url": page.get("url", ""),
        },
    }


async def _search(client, headers, params):
    query = params.get("query", "")
    resp = await client.post(
        f"{NOTION_API}/search",
        headers=headers,
        json={"query": query, "page_size": 8},
    )
    if not resp.is_success:
        return {"success": False, "error": f"Notion API {resp.status_code}"}

    items = []
    for r in resp.json().get("results", []):
        title = ""
        for val in r.get("properties", {}).values():
            if val.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in val.get("title", []))
                break
        items.append({"id": r.get("id", ""), "title": title, "url": r.get("url", ""), "type": r.get("object", "")})

    return {"success": True, "data": items}


async def _create_page(client, headers, params):
    parent_id = params.get("parent_id", "")
    title = params.get("title", "新頁面")
    content = params.get("content", "")

    body: dict = {
        "parent": {"page_id": parent_id} if parent_id else {"workspace": True},
        "properties": {"title": {"title": [{"text": {"content": title}}]}},
        "children": [],
    }
    for para in (content.split("\n") if content else [])[:20]:
        if para.strip():
            body["children"].append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": para[:2000]}}]},
            })

    resp = await client.post(f"{NOTION_API}/pages", headers=headers, json=body)
    if not resp.is_success:
        return {"success": False, "error": f"Notion API {resp.status_code}: {resp.text[:200]}"}

    page = resp.json()
    return {"success": True, "data": {"id": page.get("id"), "url": page.get("url"), "title": title}}


async def _list_database(client, headers, params):
    """列舉 Notion 資料庫中所有頁面（cursor-based 分頁，每頁 100 筆）"""
    database_id = params.get("database_id", "").replace("-", "")
    if not database_id:
        return {"success": False, "error": "缺少 database_id"}

    pages = []
    cursor = None

    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor

        resp = await client.post(
            f"{NOTION_API}/databases/{database_id}/query",
            headers=headers,
            json=body,
        )
        if not resp.is_success:
            return {"success": False, "error": f"Notion API {resp.status_code}: {resp.text[:200]}"}

        data = resp.json()
        for page in data.get("results", []):
            # 取標題
            title = ""
            for val in page.get("properties", {}).values():
                if val.get("type") == "title":
                    title = "".join(t.get("plain_text", "") for t in val.get("title", []))
                    break

            # 扁平化所有 properties 為文字（供攝取用）
            props_text_parts = []
            props_raw = {}
            for prop_name, prop_val in page.get("properties", {}).items():
                ptype = prop_val.get("type", "")
                text_val = ""
                if ptype == "title":
                    text_val = "".join(t.get("plain_text", "") for t in prop_val.get("title", []))
                elif ptype == "rich_text":
                    text_val = "".join(t.get("plain_text", "") for t in prop_val.get("rich_text", []))
                elif ptype == "select":
                    sel = prop_val.get("select") or {}
                    text_val = sel.get("name", "")
                elif ptype == "multi_select":
                    text_val = ", ".join(s.get("name", "") for s in prop_val.get("multi_select", []))
                elif ptype == "date":
                    date_data = prop_val.get("date") or {}
                    text_val = date_data.get("start", "")
                elif ptype == "number":
                    num = prop_val.get("number")
                    text_val = str(num) if num is not None else ""
                elif ptype == "checkbox":
                    text_val = "是" if prop_val.get("checkbox") else "否"
                elif ptype == "url":
                    text_val = prop_val.get("url", "") or ""
                elif ptype == "email":
                    text_val = prop_val.get("email", "") or ""
                elif ptype == "phone_number":
                    text_val = prop_val.get("phone_number", "") or ""
                if text_val:
                    props_text_parts.append(f"{prop_name}: {text_val}")
                    props_raw[prop_name] = text_val

            pages.append({
                "page_id":         page.get("id", ""),
                "title":           title,
                "last_edited_time": page.get("last_edited_time", ""),
                "url":             page.get("url", ""),
                "content_text":    "\n".join(props_text_parts),
                "properties":      props_raw,
            })

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return {"success": True, "pages": pages, "total": len(pages)}
