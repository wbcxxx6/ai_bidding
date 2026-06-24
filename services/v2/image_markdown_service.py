def build_image_plan_markdown(image_plans, *, existing_markdown=""):
    additions = []
    for index, plan in enumerate(image_plans or [], start=1):
        plan_id = plan.get("id")
        if not plan_id:
            continue
        marker = f"image-plan://{plan_id}"
        if marker in (existing_markdown or ""):
            continue
        caption = (plan.get("caption") or f"章节配图 {index}").strip()
        caption = caption.replace("[", "【").replace("]", "】")
        additions.append(f"![{caption}]({marker})")
    return "\n\n".join(additions)


def append_image_plan_placeholders(markdown, image_plans):
    content = (markdown or "").rstrip()
    addition_text = build_image_plan_markdown(image_plans, existing_markdown=content)
    if not addition_text:
        return content
    if content:
        return f"{content}\n\n{addition_text}"
    return addition_text
