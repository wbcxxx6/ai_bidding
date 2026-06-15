import os
import re
from datetime import datetime

import requests


DASHSCOPE_ASYNC_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
DEFAULT_WAN_IMAGE_MODEL = os.getenv("WAN_IMAGE_MODEL", "wan2.7-t2i")
OFFICIAL_WAN_IMAGE_MODEL = "wan2.6-t2i"
FORBIDDEN_IMAGE_KEYWORDS = [
    "营业执照",
    "身份证",
    "资质证书",
    "证书",
    "合同",
    "发票",
    "报价单",
    "投标函",
    "授权书",
    "承诺函",
    "公章",
    "签字",
    "扫描件",
]
PRODUCT_KEYWORDS = ["风扇", "风机", "设备", "产品", "模块", "主机", "传感器", "摄像机", "网关", "终端"]
SPEC_RE = re.compile(
    r"(?:(?:\d+(?:\.\d+)?\s*(?:mm|cm|m|V|W|A|RPM|rpm|Hz|kW|KW|kg|℃|°C|%))|(?:IP\d{2})|(?:[A-Z]{1,4}-?\d{2,6}))"
)


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _api_key():
    key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("BAILIAN_API_KEY")
    if not key:
        raise ValueError("DASHSCOPE_API_KEY is required for Wan image generation.")
    return key


def _headers():
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }


def _compact_text(text, limit=900):
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def _extract_specs(text):
    specs = []
    for match in SPEC_RE.findall(text or ""):
        value = re.sub(r"\s+", "", match)
        if value and value not in specs:
            specs.append(value)
    return specs[:12]


def _extract_subject(text):
    if "风扇" in text or "风机" in text:
        return "散热风扇"
    for keyword in PRODUCT_KEYWORDS:
        if keyword in text:
            return keyword
    return "章节配图"


def _image_type_for_subject(subject):
    if subject == "章节配图":
        return "process_diagram"
    return "product_image"


def _assert_generation_allowed(text):
    matched = [keyword for keyword in FORBIDDEN_IMAGE_KEYWORDS if keyword in (text or "")]
    if matched:
        raise ValueError(f"该内容涉及不可由 AI 生成的证明/签章类材料：{', '.join(matched[:3])}")


def build_section_image_prompt(section_text, *, chapter_title=None, image_type=None):
    text = _compact_text(section_text)
    if not text:
        raise ValueError("sectionText is required.")
    _assert_generation_allowed(text)

    subject = _extract_subject(text)
    specs = _extract_specs(text)
    resolved_image_type = image_type or _image_type_for_subject(subject)
    spec_text = "，".join(specs) if specs else "按正文描述体现关键结构和规格"
    title_prefix = f"{chapter_title}：" if chapter_title else ""
    prompt = (
        f"{title_prefix}为投标文件生成一张正式、清晰、可用于Word排版的{subject}图片。"
        f"画面主体为{subject}，需要体现规格参数：{spec_text}。"
        "风格为真实产品摄影或干净的产品规格示意图，白色或浅灰背景，结构清晰，比例准确，"
        "避免出现品牌商标、价格、合同章、签名、公章、证书编号和不可核实文字。"
        f"参考正文：{text}"
    )
    negative_prompt = "水印，Logo，品牌商标，价格，合同章，公章，签名，证书，身份证，模糊，畸形文字，乱码"
    return {
        "subject": subject,
        "imageType": resolved_image_type,
        "prompt": prompt,
        "negativePrompt": negative_prompt,
        "specs": specs,
        "sourceText": text,
    }


def create_wan_image_task(
    *,
    prompt,
    negative_prompt=None,
    model=None,
    size="1024*1024",
    n=1,
    prompt_extend=True,
    watermark=False,
    timeout=60,
):
    payload = {
        "model": model or DEFAULT_WAN_IMAGE_MODEL,
        "input": {"prompt": prompt},
        "parameters": {
            "size": size,
            "n": n,
            "prompt_extend": bool(prompt_extend),
            "watermark": bool(watermark),
        },
    }
    if negative_prompt:
        payload["input"]["negative_prompt"] = negative_prompt

    response = requests.post(DASHSCOPE_ASYNC_URL, headers=_headers(), json=payload, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    output = body.get("output") or {}
    task_id = output.get("task_id")
    if not task_id:
        raise ValueError(body.get("message") or "DashScope did not return task_id.")
    return {
        "taskId": task_id,
        "taskStatus": output.get("task_status"),
        "requestId": body.get("request_id"),
        "model": payload["model"],
        "payload": payload,
        "raw": body,
    }


def query_wan_image_task(task_id, *, timeout=30):
    if not task_id:
        raise ValueError("taskId is required.")
    response = requests.get(DASHSCOPE_TASK_URL.format(task_id=task_id), headers={"Authorization": f"Bearer {_api_key()}"}, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    output = body.get("output") or {}
    return {
        "taskId": output.get("task_id") or task_id,
        "taskStatus": output.get("task_status"),
        "results": output.get("results") or [],
        "requestId": body.get("request_id"),
        "usage": body.get("usage") or {},
        "raw": body,
    }


def sync_generated_asset_result(asset_id, task_result):
    from services.v2.image_asset_service import get_image_asset, update_image_asset_metadata

    asset = get_image_asset(asset_id)
    if not asset:
        raise ValueError("image asset not found.")
    metadata = asset.get("metadata") or {}
    results = task_result.get("results") or []
    urls = [item.get("url") for item in results if item.get("url")]
    metadata.update(
        {
            "taskStatus": task_result.get("taskStatus"),
            "requestId": task_result.get("requestId") or metadata.get("requestId"),
            "results": results,
            "resultUrls": urls,
            "syncedAt": now(),
            "urlExpiresInHours": 24,
        }
    )
    review_status = "ready" if task_result.get("taskStatus") == "SUCCEEDED" and urls else None
    return update_image_asset_metadata(asset_id, metadata, review_status=review_status, allowed_for_bid=False)


def create_section_image_generation(data):
    from services.v2.image_asset_service import create_image_asset

    prompt_data = build_section_image_prompt(
        data.get("sectionText") or data.get("section_text") or "",
        chapter_title=data.get("chapterTitle") or data.get("chapter_title"),
        image_type=data.get("imageType") or data.get("image_type"),
    )
    task = create_wan_image_task(
        prompt=prompt_data["prompt"],
        negative_prompt=prompt_data["negativePrompt"],
        model=data.get("model") or DEFAULT_WAN_IMAGE_MODEL,
        size=data.get("size") or "1024*1024",
        n=int(data.get("n") or 1),
        prompt_extend=data.get("promptExtend", data.get("prompt_extend", True)),
        watermark=data.get("watermark", False),
    )
    metadata = {
        "provider": "dashscope",
        "model": task["model"],
        "taskId": task["taskId"],
        "requestId": task.get("requestId"),
        "taskStatus": task.get("taskStatus"),
        "officialReferenceModel": OFFICIAL_WAN_IMAGE_MODEL,
        "prompt": prompt_data["prompt"],
        "negativePrompt": prompt_data["negativePrompt"],
        "sourceText": prompt_data["sourceText"],
        "specs": prompt_data["specs"],
        "createdAt": now(),
    }
    asset = create_image_asset(
        {
            "projectId": data.get("projectId") or data.get("project_id"),
            "companyId": data.get("companyId") or data.get("company_id"),
            "assetTitle": data.get("assetTitle")
            or data.get("asset_title")
            or f"{prompt_data['subject']}AI生成图",
            "imageType": prompt_data["imageType"],
            "caption": data.get("caption") or f"{prompt_data['subject']}示意图",
            "searchableText": " ".join(
                [
                    prompt_data["subject"],
                    prompt_data["imageType"],
                    " ".join(prompt_data["specs"]),
                    prompt_data["sourceText"],
                ]
            ),
            "tags": [prompt_data["subject"], "AI生成", *prompt_data["specs"]],
            "sourceType": "ai_generated",
            "synthetic": True,
            "allowedForBid": False,
            "reviewStatus": "pending",
            "metadata": metadata,
            "userId": data.get("userId") or data.get("created_by"),
        }
    )
    return {"task": task, "prompt": prompt_data, "asset": asset}
