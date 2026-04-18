"""
Plugin Registry — 統一調度所有內建插件 + 插件目錄定義

所有內建插件在此登記，registry.dispatch() 是統一入口。
PLUGIN_CATALOG 供前端顯示插件目錄。
"""
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# ── Handler Map ──────────────────────────────────────────────────────────────
# key: builtin_key, value: async run(action, params, config) -> dict

_REGISTRY: dict[str, Callable] = {}


def _ensure_loaded():
    if _REGISTRY:
        return
    from plugins.notion_handler     import run as notion_run
    from plugins.chart_handler      import run as chart_run
    from plugins.calculator_handler import run as calc_run
    from plugins.email_handler      import run as email_run
    from plugins.rss_handler        import run as rss_run
    from plugins.weather_handler    import run as weather_run

    _REGISTRY.update({
        "notion":     notion_run,
        "chart":      chart_run,
        "calculator": calc_run,
        "email":      email_run,
        "rss":        rss_run,
        "weather":    weather_run,
    })


async def dispatch(builtin_key: str, action: str, params: dict, config: dict) -> dict:
    """統一調度入口"""
    _ensure_loaded()
    handler = _REGISTRY.get(builtin_key)
    if handler is None:
        return {"success": False, "error": f"未知的內建插件 key: {builtin_key}"}
    try:
        return await handler(action, params, config)
    except Exception as e:
        logger.error("Plugin '%s' exception: %s", builtin_key, e, exc_info=True)
        return {"success": False, "error": str(e)}


# ── Plugin Catalog（供前端展示） ─────────────────────────────────────────────
PLUGIN_CATALOG = [
    {
        "key": "notion",
        "name": "Notion 同步",
        "description": "讀取、搜尋、建立 Notion 頁面，讓 AI 直接存取你的 Notion 知識庫",
        "icon": "📝",
        "category": "productivity",
        "category_label": "生產力",
        "actions": ["read_page", "search", "create_page"],
        "config_fields": [
            {
                "key": "notion_token",
                "label": "Notion Integration Token",
                "type": "password",
                "help": "至 https://www.notion.so/my-integrations 建立 Integration 後取得 Secret",
            },
        ],
        "ai_description": (
            "讀取或搜尋 Notion 頁面，或在 Notion 建立新頁面。"
            "輸入 JSON: {\"action\": \"read_page\"|\"search\"|\"create_page\", "
            "\"page_id\": \"xxx\", \"query\": \"xxx\", \"title\": \"xxx\", \"content\": \"xxx\"}"
        ),
        "planned": False,
    },
    {
        "key": "chart",
        "name": "數據圖產出",
        "description": "根據數據生成長條圖、折線圖、圓餅圖、散點圖，儲存至 MinIO 並回傳圖片連結",
        "icon": "📊",
        "category": "data",
        "category_label": "數據分析",
        "actions": ["bar", "line", "pie", "scatter"],
        "config_fields": [],
        "ai_description": (
            "根據數據生成圖表。"
            "輸入 JSON: {\"action\": \"bar\"|\"line\"|\"pie\"|\"scatter\", "
            "\"title\": \"標題\", \"labels\": [...], \"data\": [...], "
            "\"x_label\": \"X軸\", \"y_label\": \"Y軸\"}"
        ),
        "planned": False,
    },
    {
        "key": "calculator",
        "name": "數學計算器",
        "description": "安全的數學計算，支援 sin/cos/sqrt/log 等函式，AI 推理時自動使用",
        "icon": "🔢",
        "category": "utility",
        "category_label": "工具",
        "actions": ["eval"],
        "config_fields": [],
        "ai_description": (
            "執行數學計算（安全 AST 白名單）。"
            "輸入 JSON: {\"expression\": \"sqrt(16) + 2**3\"}"
        ),
        "planned": False,
    },
    {
        "key": "email",
        "name": "Email 發送",
        "description": "透過 SMTP 發送電子郵件，支援 TLS/STARTTLS（Gmail / Outlook / 自架 SMTP）",
        "icon": "✉️",
        "category": "productivity",
        "category_label": "生產力",
        "actions": ["send"],
        "config_fields": [
            {"key": "smtp_host",     "label": "SMTP Host",       "type": "text",     "placeholder": "smtp.gmail.com"},
            {"key": "smtp_port",     "label": "SMTP Port",       "type": "number",   "placeholder": "587"},
            {"key": "smtp_user",     "label": "帳號（Email）",   "type": "text"},
            {"key": "smtp_password", "label": "密碼 / App 密碼", "type": "password"},
            {"key": "sender_email",  "label": "寄件人（選填）",  "type": "text"},
        ],
        "ai_description": (
            "發送電子郵件。"
            "輸入 JSON: {\"to\": \"user@example.com\", \"subject\": \"主旨\", \"body\": \"內容\"}"
        ),
        "planned": False,
    },
    {
        "key": "rss",
        "name": "RSS 訂閱閱讀器",
        "description": "讀取 RSS/Atom Feed，取得最新文章清單，讓 AI 追蹤資訊來源",
        "icon": "📡",
        "category": "data",
        "category_label": "數據分析",
        "actions": ["fetch"],
        "config_fields": [],
        "ai_description": (
            "讀取 RSS 訂閱源取得最新文章。"
            "輸入 JSON: {\"url\": \"https://feeds.bbci.co.uk/news/rss.xml\", \"limit\": 10}"
        ),
        "planned": False,
    },
    {
        "key": "weather",
        "name": "天氣查詢",
        "description": "查詢全球即時天氣與 7 天預報（免費 Open-Meteo API，無需金鑰）",
        "icon": "🌤️",
        "category": "utility",
        "category_label": "工具",
        "actions": ["current"],
        "config_fields": [],
        "ai_description": (
            "查詢城市天氣與預報（免費，無需 API Key）。"
            "輸入 JSON: {\"city\": \"Taipei\", \"days\": 3} "
            "或 {\"latitude\": 25.05, \"longitude\": 121.53, \"days\": 1}"
        ),
        "planned": False,
    },
    # ── 規劃中 ──
    {
        "key": "google_sheets",
        "name": "Google Sheets",
        "description": "讀取 / 寫入 Google 試算表（需 Google Service Account）",
        "icon": "📋",
        "category": "productivity",
        "category_label": "生產力",
        "actions": ["read", "write", "append"],
        "config_fields": [
            {"key": "service_account_json", "label": "Service Account JSON", "type": "textarea"},
        ],
        "ai_description": "讀取或寫入 Google Sheets。",
        "planned": True,
    },
    {
        "key": "slack",
        "name": "Slack 通知",
        "description": "發送 Slack 訊息到指定頻道（需 Bot Token）",
        "icon": "💬",
        "category": "productivity",
        "category_label": "生產力",
        "actions": ["send"],
        "config_fields": [
            {"key": "bot_token", "label": "Bot Token", "type": "password", "placeholder": "xoxb-..."},
        ],
        "ai_description": "發送 Slack 訊息。輸入 JSON: {\"channel\": \"#general\", \"message\": \"...\"}",
        "planned": True,
    },
    {
        "key": "github",
        "name": "GitHub 搜尋",
        "description": "搜尋 GitHub Repositories / Issues / Code，取得程式碼片段",
        "icon": "🐙",
        "category": "dev",
        "category_label": "開發工具",
        "actions": ["search_repo", "search_code", "get_file"],
        "config_fields": [
            {"key": "github_token", "label": "GitHub Personal Access Token", "type": "password"},
        ],
        "ai_description": "搜尋 GitHub 代碼或 Repository。",
        "planned": True,
    },
    {
        "key": "pdf_generator",
        "name": "PDF 報告產出",
        "description": "將 Markdown / HTML 內容轉換成 PDF 報告並儲存至 MinIO",
        "icon": "📄",
        "category": "data",
        "category_label": "數據分析",
        "actions": ["generate"],
        "config_fields": [],
        "ai_description": "將內容轉換為 PDF 報告。輸入 JSON: {\"title\": \"...\", \"content\": \"Markdown content\"}",
        "planned": True,
    },
    {
        "key": "viz3d",
        "name": "3D 知識圖譜",
        "description": "以 Three.js 3D force-directed graph 視覺化知識庫本體論關係（前端渲染）",
        "icon": "🌐",
        "category": "visualization",
        "category_label": "視覺化",
        "actions": ["render"],
        "config_fields": [],
        "ai_description": "觸發前端 3D 知識圖譜視圖。",
        "planned": True,
    },
    {
        "key": "translation",
        "name": "多語言翻譯",
        "description": "使用 LibreTranslate（自架免費）或 DeepL API 翻譯文字",
        "icon": "🌐",
        "category": "utility",
        "category_label": "工具",
        "actions": ["translate"],
        "config_fields": [
            {"key": "provider",  "label": "Provider", "type": "select",   "options": ["libretranslate", "deepl"]},
            {"key": "api_key",   "label": "API Key",  "type": "password", "placeholder": "DeepL / LibreTranslate key（若自架可留空）"},
            {"key": "api_url",   "label": "API URL",  "type": "text",     "placeholder": "http://localhost:5000（LibreTranslate 自架）"},
        ],
        "ai_description": "翻譯文字。輸入 JSON: {\"text\": \"...\", \"target\": \"zh\", \"source\": \"en\"}",
        "planned": True,
    },
]
