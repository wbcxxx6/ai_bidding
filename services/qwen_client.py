from services.model_router import model_router


def call_llm_api(
    messages,
    model=None,
    response_format=None,
    timeout=120,
    task_type=None,
    generation_task_id=None,
    project_id=None,
    retries=None,
):
    return model_router.chat(
        messages,
        model=model,
        response_format=response_format,
        timeout=timeout,
        task_type=task_type,
        generation_task_id=generation_task_id,
        project_id=project_id,
        retries=retries,
    )


def call_dashscope_api(
    messages,
    model=None,
    task_type=None,
    generation_task_id=None,
    project_id=None,
    timeout=120,
    retries=None,
):
    """Backward-compatible wrapper used by existing routes."""
    return call_llm_api(
        messages,
        model=model,
        response_format={"type": "json_object"},
        timeout=timeout,
        task_type=task_type,
        generation_task_id=generation_task_id,
        project_id=project_id,
        retries=retries,
    )


def generate_bid_section(section_title, section_content, tender_content, *, generation_task_id=None, project_id=None):
    prompt = f"""你是一位具有十年以上经验的资深投标文件撰写专家。请根据以下信息撰写投标文件正文章节。

重要边界：
- 如果招标文件已给出固定模板正文的章节，不应调用本生成任务；本任务只用于招标文件未规定正文、需要自行撰写的章节。
- 章节一级标题和顺序由系统锁定，请不要改写章节标题的含义。

【撰写规范】
1. 结构要求：
   - 本章必须包含至少 3 个二级节（用 ### 标记）
   - 每个二级节下必须包含至少 3 个三级小节（用 #### 标记）
   - 必须使用到三级标题，不能只写二级标题或普通段落
   - 每个三级小节正文不少于 1500 字，重要小节应达到 1800-2200 字
   - 章节整体结构示例：
     ## 章节标题
     ### 二级节标题一
     #### 三级小节 1.1
     （正文内容不少于 1500 字）
     #### 三级小节 1.2
     （正文内容不少于 1500 字）
     #### 三级小节 1.3
     （正文内容不少于 1500 字）
     ### 二级节标题二
     #### 三级小节 2.1
     ...

2. 语言风格：
   - 使用正式、严谨、专业的投标文件语言
   - 使用"本公司"、"投标人"指代己方，"采购人"、"招标人"指代对方
   - 禁止口语化表达、禁止"我们"、"你们"
   - 禁止模糊表述如"如有需要"、"可以考虑"、"大概"

3. 内容要求：
   - 每个要点必须展开论述，给出具体措施、方法、流程或标准
   - 技术方案章节应包含：总体设计思路、技术架构、关键技术、实施方案、质量保障
   - 服务方案章节应包含：服务体系、服务内容、服务流程、服务标准、应急预案
   - 管理方案章节应包含：组织架构、管理制度、人员配置、培训计划、考核机制
   - 可适当使用表格展示对比、清单、计划等结构化信息

4. 格式要求：
   - 使用 Markdown 标题（##、###、####）标记层级
   - 表格使用标准 Markdown 语法，单元格内容为纯文本，不得包含 **加粗** 等标记
   - 正文段落之间空一行
   - 列表使用 1. 2. 3. 或 - 标记
   - 技术方案、实施方案、系统架构类章节可包含 1 个结构化流程图
   - 流程图必须使用 ```flowchart-json 代码块输出 JSON，不得输出 Mermaid
   - flowchart-json 示例：
     ```flowchart-json
     {{"title":"项目实施流程图","nodes":["需求分析","方案设计","系统开发","测试验收","上线运行"],"edges":[{{"from":"N1","to":"N2"}},{{"from":"N2","to":"N3"}},{{"from":"N3","to":"N4"}},{{"from":"N4","to":"N5"}}]}}
     ```
   - 每个流程图前必须有一行说明文字，如"本项目技术架构如下图所示："

5. 禁止事项：
   - 不得编造企业名称、资质证书、项目案例、人员信息、合同金额
   - 不得使用代码块（```）包裹正文；代码块仅允许用于 flowchart-json 结构化流程图
   - 表格内不得出现 Markdown 格式标记

6. 篇幅要求：
   - 每个三级小节正文不少于 1500 字
   - 本章节至少包含 9 个三级小节，总字数不少于 13500 字
   - 技术方案、实施方案、服务方案类章节总字数不少于 15000 字
   - 内容必须充实具体，禁止空泛概括，每个要点必须展开详细论述

【章节标题】
## {section_title}

【章节要求与描述】
{section_content}

【参考资料与项目背景】
{tender_content if tender_content else '（无额外参考资料，请基于章节描述和专业知识撰写）'}

请直接输出本章完整正文（从 ### 二级节标题开始，必须包含 ### 和 #### 两级标题），不要输出任何解释、说明或总结。
"""
    response = call_llm_api(
        [{"role": "user", "content": prompt}],
        task_type="generate_chapter",
        generation_task_id=generation_task_id,
        project_id=project_id,
        timeout=120,
    )
    return response["output"]["choices"][0]["message"]["content"]
