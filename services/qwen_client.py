from services.model_router import model_router


def call_llm_api(messages, model=None, response_format=None, timeout=120, task_type=None, generation_task_id=None, project_id=None):
    return model_router.chat(
        messages,
        model=model,
        response_format=response_format,
        timeout=timeout,
        task_type=task_type,
        generation_task_id=generation_task_id,
        project_id=project_id,
    )


def call_dashscope_api(messages, model=None, task_type=None, generation_task_id=None, project_id=None):
    """Backward-compatible wrapper used by existing routes."""
    return call_llm_api(
        messages,
        model=model,
        response_format={"type": "json_object"},
        task_type=task_type,
        generation_task_id=generation_task_id,
        project_id=project_id,
    )


def generate_bid_section(section_title, section_content, tender_content, *, generation_task_id=None, project_id=None):
    prompt = f"""你是一位具有十年以上经验的资深投标文件撰写专家。请根据以下信息撰写投标文件正文章节。

【撰写规范】
1. 结构要求：
   - 本章必须包含至少 3 个二级节（用 ### 标记）
   - 每个二级节下必须包含至少 2-3 个三级小节（用 #### 标记）
   - 每个三级小节正文不少于 500 字，重要小节应达到 800-1000 字
   - 章节整体结构示例：
     ## 章节标题
     ### 二级节标题一
     #### 三级小节 1.1
     （正文内容 500-1000 字）
     #### 三级小节 1.2
     （正文内容 500-1000 字）
     #### 三级小节 1.3
     （正文内容 500-1000 字）
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
   - 技术方案、实施方案、系统架构类章节中，必须包含 1-2 个 Mermaid 流程图
   - Mermaid 图使用 ```mermaid 代码块包裹，图表类型可选 flowchart TD、sequenceDiagram、gantt
   - Mermaid 图示例：
     ```mermaid
     flowchart TD
         A[需求分析] --> B[方案设计]
         B --> C[系统开发]
         C --> D[测试验收]
         D --> E[上线运行]
     ```
   - 每个 Mermaid 图前必须有一行说明文字，如"本项目技术架构如下图所示："

5. 禁止事项：
   - 不得编造企业名称、资质证书、项目案例、人员信息、合同金额
   - 不得使用代码块（```）包裹正文
   - 表格内不得出现 Markdown 格式标记

6. 篇幅要求：
   - 每个三级小节正文不少于 500 字
   - 本章节总字数不少于 3000 字
   - 技术方案、实施方案、服务方案类章节总字数不少于 4000 字
   - 内容必须充实具体，禁止空泛概括，每个要点必须展开详细论述

【章节标题】
## {section_title}

【章节要求与描述】
{section_content}

【参考资料与项目背景】
{tender_content if tender_content else '（无额外参考资料，请基于章节描述和专业知识撰写）'}

请直接输出本章完整正文（从 ### 二级节标题开始），不要输出任何解释、说明或总结。
"""
    response = call_llm_api(
        [{"role": "user", "content": prompt}],
        task_type="generate_chapter",
        generation_task_id=generation_task_id,
        project_id=project_id,
        timeout=120,
    )
    return response["output"]["choices"][0]["message"]["content"]
