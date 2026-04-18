"""
Chart Generator Plugin Handler
支援動作: bar | line | pie | scatter | heatmap
params: {title, labels, data, series_names, x_label, y_label}
依賴: matplotlib（backend 容器已含）
"""
import io
import logging
import uuid
from datetime import timedelta

logger = logging.getLogger(__name__)

_COLORS = ["#4a90d9", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22", "#3498db"]


async def run(action: str, params: dict, config: dict) -> dict:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return {"success": False, "error": "matplotlib 未安裝，請執行: pip install matplotlib"}

    chart_type = action or "bar"
    title      = params.get("title", "Chart")
    labels     = params.get("labels", [])
    data       = params.get("data", [])
    series_names = params.get("series_names", [])
    x_label    = params.get("x_label", "")
    y_label    = params.get("y_label", "")

    if not data:
        return {"success": False, "error": "缺少 data 參數"}

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except Exception:
        pass

    fig, ax = plt.subplots(figsize=(10, 6))

    try:
        _draw(ax, np, chart_type, labels, data, series_names)
    except Exception as e:
        plt.close(fig)
        return {"success": False, "error": f"繪圖失敗: {e}"}

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    if x_label:
        ax.set_xlabel(x_label)
    if y_label:
        ax.set_ylabel(y_label)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    # 嘗試上傳 MinIO，回傳 presigned URL
    try:
        from services.storage import get_minio_client
        from config import settings as app_settings

        client = get_minio_client()
        filename = f"charts/{uuid.uuid4()}.png"
        image_bytes = buf.getvalue()
        client.put_object(
            app_settings.MINIO_BUCKET,
            filename,
            io.BytesIO(image_bytes),
            len(image_bytes),
            content_type="image/png",
        )
        url = client.presigned_get_object(app_settings.MINIO_BUCKET, filename, expires=timedelta(hours=24))
        return {"success": True, "data": {"url": url, "filename": filename, "chart_type": chart_type}}
    except Exception as e:
        logger.warning("MinIO 上傳失敗，改用 base64: %s", e)

    # Fallback: base64
    import base64
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    return {
        "success": True,
        "data": {
            "base64": f"data:image/png;base64,{b64}",
            "chart_type": chart_type,
            "note": "MinIO 不可用，已回傳 base64 編碼圖片",
        },
    }


def _draw(ax, np, chart_type, labels, data, series_names):
    is_multi = data and isinstance(data[0], (list, tuple))

    if chart_type == "pie":
        vals = data if not is_multi else data[0]
        lbs = labels or [str(i) for i in range(len(vals))]
        ax.pie(vals, labels=lbs, autopct="%1.1f%%", colors=_COLORS[:len(vals)])
        ax.axis("equal")

    elif chart_type == "line":
        if is_multi:
            x = labels or list(range(len(data[0])))
            for i, series in enumerate(data):
                name = series_names[i] if i < len(series_names) else f"系列{i+1}"
                ax.plot(x, series, marker="o", color=_COLORS[i % len(_COLORS)], label=name)
            ax.legend()
        else:
            x = labels or list(range(len(data)))
            ax.plot(x, data, marker="o", color=_COLORS[0])

    elif chart_type == "scatter":
        x_vals = params_safe(ax, data, labels)
        ax.scatter(x_vals, data, color=_COLORS[0], alpha=0.7)

    else:  # bar
        if is_multi:
            n_groups = len(data[0])
            n_series = len(data)
            x = np.arange(n_groups)
            width = 0.8 / n_series
            for i, series in enumerate(data):
                name = series_names[i] if i < len(series_names) else f"系列{i+1}"
                ax.bar(x + i * width - 0.4 + width / 2, series, width,
                       color=_COLORS[i % len(_COLORS)], label=name)
            if labels:
                ax.set_xticks(x)
                ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.legend()
        else:
            x = labels or list(range(len(data)))
            ax.bar(x, data, color=_COLORS[0])
            if labels:
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha="right")


def params_safe(ax, data, labels):
    """scatter x axis"""
    return labels if labels else list(range(len(data)))
