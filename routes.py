import logging
from flask import Blueprint, request, jsonify, current_app
import os
import sqlite3
import uuid
import json
import jwt
import requests
from datetime import datetime
from pathlib import Path
import mammoth
from unidecode import unidecode
import re
from werkzeug.utils import secure_filename
import codecs
import PyPDF2
from qwen_client import call_dashscope_api, generate_bid_section
from md_to_word import convert_md_to_word
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import shutil
from datetime import timedelta

# 操作向量数据库的函数
from file_to_chroma import file_to_chroma, query_chroma
# 创建蓝图
bp = Blueprint('bidding', __name__)

# 临时的内存存储，用于在 upload -> pre-analysis -> chapter-analysis 之间传递小量状态
# 结构: { bidding_id: { 'biddingId': int, 'analysisData': dict|None, 'directoryStructure': dict|None } }
temp_analysis_store = {}
_temp_store_lock = threading.Lock()

# 环境变量
ONLYOFFICE_JWT_SECRET = os.getenv('ONLYOFFICE_JWT_SECRET', 'fsdftertrt34768586sfhjsdhfjhhjfsuhaiubue')
BACKEND_URL_FOR_DOCKER = os.getenv('BACKEND_URL_FOR_DOCKER', 'host.docker.internal:3012')
APP_HOST = os.getenv('APP_HOST', 'localhost:3012')

def _with_http_scheme(base_url):
    base_url = (base_url or '').strip().rstrip('/')
    if not base_url:
        return ''
    if base_url.startswith(('http://', 'https://')):
        return base_url
    return f'http://{base_url}'

def get_backend_public_base_url():
    """Return the backend URL reachable by the OnlyOffice document server."""
    return _with_http_scheme(
        os.getenv('APP_PUBLIC_BASE_URL')
        or os.getenv('BACKEND_URL_FOR_DOCKER')
        or BACKEND_URL_FOR_DOCKER
        or APP_HOST
    )

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect('bidding.db')
    conn.row_factory = sqlite3.Row
    return conn

def read_tender_file(bidding_id):
    """读取招标文件"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bidding WHERE id = ?', (bidding_id,))
        bidding = cursor.fetchone()
        conn.close()
        if not bidding:
            return jsonify({'error': '招标书不存在'}), 404
        file_path = Path(bidding['storage_path'])
        if file_path.suffix.lower() == '.pdf':
            return _read_pdf(file_path)
        else:
            with open(bidding['storage_path'], 'rb') as f:
                result = mammoth.extract_raw_text(f)
            return result.value
    except Exception as e:
        return jsonify({'error': f'读取文件失败: {str(e)}'}), 500

def _read_pdf(file_path):
    """读取PDF文件"""
    text = ""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return jsonify({'error': f'读取文件失败: {str(e)}'}), 500
    
def save_bid_section(content, section_name, output_dir, tender_name):
    '''保存投标文件小节'''
    output_path = Path(output_dir) / tender_name / f"{section_name}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
    except Exception as e:
            logging.error(f"保存章节 {section_name} 时出错: {e}")

def merge_sections(output_dir, tender_name, sections):
        """合并所有章节内容为一个完整的文档"""
        sections_dir = Path(output_dir) / tender_name
        if not sections_dir.exists():
            logging.error(f"目录 {sections_dir} 不存在！")
            return
        
        # 获取所有章节文件
        section_files = list(sections_dir.glob("*.txt"))
        if not section_files:
            logging.error(f"在 {sections_dir} 目录下未找到章节文件！")
            return
        
        # 创建合并后的文档
        merged_content = ["# 投标文件\n\n"] + [
            f"## {section_name}\n\n{content}\n\n"
            for section_name in sections
            if (section_file := sections_dir / f"{section_name}.txt").exists()
            for content in [section_file.read_text(encoding='utf-8')]
        ]
        output_file = sections_dir / f"{tender_name}_完整投标文件.md"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(merged_content))
            logging.info(f"已生成完整投标文件：{output_file}")
            return output_file
        except Exception as e:
            logging.error(f"保存合并文件时出错: {e}")
            return None    

@bp.route('/upload', methods=['POST'])
def upload_bidding():
    """上传招标文件 —— 仅保存文件并写入 DB，不生成 OnlyOffice 配置"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400

    user_id = request.form.get('userId')
    if not user_id:
        return jsonify({'error': 'User ID is required for upload.'}), 400

    try:
        original_filename = file.filename
        safe_filename = secure_filename(original_filename)
        unique_filename = f"{uuid.uuid4()}-{safe_filename}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)

        # 保存文件到 uploads 目录
        file.save(file_path)

        # 保持现有的向量化流程（同步或可改为异步）
        try:
            file_to_chroma(file_path)
        except Exception:
            logging.exception("file_to_chroma failed for %s", file_path)

        # 生成 document_key 并写入 DB
        document_key = str(uuid.uuid4())
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bidding (user_id, original_filename, storage_path, document_key, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, original_filename, file_path, document_key, 'Uploaded'))
        bidding_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # 在内存临时存储中记录初始条目，analysisData 和 directoryStructure 先为空
        try:
            with _temp_store_lock:
                temp_analysis_store[bidding_id] = {
                    'biddingId': bidding_id,
                    'analysisData': None,
                    'directoryStructure': None,
                }
        except Exception:
            logging.exception('初始化 temp_analysis_store 失败')

        # 返回 minimal 信息（前端随后调用 /generate-bid-document）
        return jsonify({
            'message': 'File uploaded successfully.',
            'biddingId': bidding_id,
            'originalFilename': original_filename
        }), 201

    except Exception as e:
        logging.exception("upload_bidding failed")
        return jsonify({'error': f'Server error during file upload: {str(e)}'}), 500
    
@bp.route('/save-callback', methods=['POST'])
def save_callback():
    """OnlyOffice 保存回调"""
    try:
        body = request.get_json(force=True)
        logging.info(f'[INFO] Save callback received: {json.dumps(body, indent=2, ensure_ascii=False)}')

        # OnlyOffice status 2 = readyForSave, 6 = mustSave
        if body.get('status') in [2, 6]:
            download_url = body.get('url')
            document_key = body.get('key')

            if not download_url:
                logging.warning(f'No download URL provided for key {document_key}')
                return jsonify({'error': 0})

            conn = get_db()
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM bidding WHERE document_key = ?', (document_key,))
                bidding = cursor.fetchone()

                if not bidding:
                    logging.error(f'Bidding with key {document_key} not found')
                    return jsonify({'error': 0})

                target_path = bidding['bid_document'] or bidding['storage_path']
                Path(target_path).parent.mkdir(parents=True, exist_ok=True)

                resp = requests.get(download_url, stream=True, timeout=60)
                resp.raise_for_status()
                with open(target_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                # 更新 DB 状态为 Edited，并保存 bid_document 路径
                cursor.execute('UPDATE bidding SET status=?, bid_document=? WHERE id=?',
                               ('Edited', target_path, bidding['id']))
                conn.commit()
                logging.info(f'Document {bidding["original_filename"]} updated successfully at {target_path}')
            finally:
                conn.close()

        # OnlyOffice 要求返回 { "error": 0 }
        return jsonify({'error': 0})

    except Exception as e:
        logging.exception('save-callback failed')
        return jsonify({'error': 0})
    
@bp.route('/pre-analysis_bid', methods=['POST'])
def pre_analysis_bid():
    """预处理招标文件"""
    data = request.get_json()
    bidding_id = data.get('biddingId')
    if not bidding_id:
        return jsonify({'error': 'Missing biddingId'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bidding WHERE id = ?', (bidding_id,))
        bidding = cursor.fetchone()
        conn.close()
        if not bidding:
            return jsonify({'error': '招标书不存在'}), 404
        # 读取文件内容
        bid_content = read_tender_file(bidding_id)

        pre_analysis_prompt =  f'''
        你是一个资深的招投标文件分析师，请根据以下招标书内容，提炼出完整信息，并严格按照下面的JSON格式返回你的分析结果，不要有任何多余的解释，只返回以下json内容。
        {{
            "bidding_requirements":"...",
            "bidding_summary":"...",
            "bidding_meta":"..."
        }}
        "bidding_requirements": 必须包含的文件和材料。
        "bidding_summary":对招标书内容的总结，包括服务内容、服务期限与服务地点以及质量标准等。
        "bidding_meta":招标书中具体的实质性要求内容和评分标准。
        招标书内容如下:
        ---
        {bid_content}
        ---
        '''
        response = call_dashscope_api([
            {'role': 'user', 'content': pre_analysis_prompt}
        ])
        # print(f'[INFO] Pre-analysis response: {response}')
        # 兼容不同返回结构
        try:
            http_data = response['output']['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError):
            return jsonify({'error': 'API响应格式错误'}), 500

        # 解析JSON响应
        clean_json = re.sub(r'<think>.*?</think>', '', http_data, flags=re.DOTALL).strip()
        json_match = re.search(r'```json\n(.*?)\n```', clean_json, re.DOTALL)

        try:
            if json_match:
                analysis_result = json.loads(json_match.group(1))
            else:
                clean_json = clean_json.replace('```json', '').replace('```', '').strip()
                analysis_result = json.loads(clean_json)
            # 将 pre-analysis 的结果写入临时存储（如果存在对应的 bidding_id）
            try:
                with _temp_store_lock:
                    if bidding_id in temp_analysis_store:
                        temp_analysis_store[bidding_id]['analysisData'] = analysis_result
                    else:
                        temp_analysis_store[bidding_id] = {
                            'biddingId': bidding_id,
                            'analysisData': analysis_result,
                            'directoryStructure': None,
                        }
            except Exception:
                logging.exception('写入 temp_analysis_store.analysisData 失败')
        except Exception as e:
            print(f'[ERROR] JSON解析失败: {str(e)}')
            return jsonify({'error': 'API返回内容解析失败'}), 500
        return jsonify(analysis_result)

    except Exception as e:
        print(f'[ERROR] Pre-analysis failed for bidding {bidding_id}: {str(e)}')
        return jsonify({'error': '预分析失败，请稍后重试。'}), 500        

@bp.route('/chapter-analysis_bid', methods=['POST'])
def chapter_analysis_bid():
    """招标文件章节分析"""
    data = request.get_json()
    
    bidding_id = data.get('biddingId')
    if not bidding_id:
        return jsonify({'error': 'Missing biddingId'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bidding WHERE id = ?', (bidding_id,))
        bidding = cursor.fetchone()
        conn.close()
        if not bidding:
            return jsonify({'error': '招标书不存在'}), 404
        # 读取文件内容
        bid_content = read_tender_file(bidding_id)
        post_analysis_prompt = f'''
        你是一个资深的招投标文件结构分析师，请根据以下招标书内容，输出投标书其他响应文件的格式章节内容（除封面章节），并严格按照下面的JSON格式返回你的分析结果，不要有任何多余的解释。
        {{
            "chapter_format":"..."
        }}
        "chapter_format":招标书中的其他响应文件格式，如果有表格内容，请用Markdown表格的形式返回。
        招标书内容如下:
        ---
        {bid_content}
        ---
        '''
        response = call_dashscope_api([
                {'role': 'user', 'content': post_analysis_prompt}
            ])
        try:
             http_data = response['output']['choices'][0]['message']['content']
             temp_analysis_store[bidding_id]['directoryStructure'] = http_data
        except (KeyError, IndexError, TypeError):
             return jsonify({'error': 'API响应格式错误'}), 500


        #解析JSON响应
        clean_json = re.sub(r'<think>.*?</think>', '', http_data, flags=re.DOTALL).strip()
        json_match = re.search(r'```json\n(.*?)\n```', clean_json, re.DOTALL)

        if json_match:
            analysis_result = json.loads(json_match.group(1))
        else:
            clean_json = clean_json.replace('```json', '').replace('```', '').strip()
            analysis_result = json.loads(clean_json)
        return jsonify(analysis_result)

    except Exception as e:
        print(f'[ERROR] Chapter-analysis failed for bidding {bidding_id}: {str(e)}')
        return jsonify({'error': '章节提取分析失败，请稍后重试。'}), 500
    
@bp.route('/chapter-design', methods=['POST'])
def chapter_design():
    """投标文件章节设计"""
    data = request.get_json()
    bidding_id = data.get('biddingId') 
    logging.info(f"temp_analysis_store: {temp_analysis_store}")
    print(f"temp_analysis_store: {temp_analysis_store}")
    # 获取分析结果和目录结构
    analysis_data = temp_analysis_store.get(bidding_id, {}).get('analysisData')
    directory_structure = temp_analysis_store.get(bidding_id, {}).get('directoryStructure')

    if not all([bidding_id, analysis_data, directory_structure]):
        return jsonify({'error': 'Incomplete analysis request'}), 400

    # 提取招标书信息
    bidding_requirements = analysis_data.get('bidding_requirements', '')
    bidding_summary = analysis_data.get('bidding_summary', '')
    bidding_meta = analysis_data.get('bidding_meta', '')

    # 构建提示词
    chapter_design_prompt = (
        f"你是一个资深的投标文件目录结构设计专家，请根据以下信息，整理出最终的标书章节结构：\n\n"
        f"必须包含的文件和材料：{bidding_requirements}\n"
        f"招标书内容总结：{bidding_summary}\n"
        f"招标书具体要求和评分标准：{bidding_meta}\n"
        f"投标书章节大纲：{directory_structure}\n\n"
        "基于以上招标文件要求和行业经验，请补充章节的子节目录，确保投标文件完整且符合要求。\n"
        "要求：\n"
        "1、输出的投标书章节结构必须遵循目录结构，并包含所有必要的子章节。\n"
        "2、章节大纲中某一章如果是xxx表、xxx函、xxx清单、封面等，则该章下不需要再细分子节，返回原本的章节内容。\n"
        "3、输出必须是有效的JSON格式，格式如下：\n"
        '''{
  "chapters": [
    {
      "title": "",
      "type": "normal|table",
      "content": "",
      "sections": [
        {
          "title": "",
          "subsections": [
            {
              "title": "",
              "describe": ""
            }
          ]
        }
      ]
    }
  ]
}'''
        "字段说明：\n"
        "title：章节标题。\n"
        "type：章节类型，normal表示文本章节，table表示表格章节。\n"
        "content：table章节需填写原本章节内容。\n"
        "sections：二级标题。\n"
        "subsections：三级标题，最少5-7点三级标题。\n"
        "describe：三级标题内容的描述。\n"
    )

    try:
        # 调用 LLM API
        response = call_dashscope_api([
            {'role': 'user', 'content': chapter_design_prompt}
        ])
        print(f'[INFO] response: {response}')

        # 获取返回内容
        try:
            http_data = response['output']['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError):
            return jsonify({'error': 'API响应格式错误'}), 500

        # 解析 JSON 响应并清理控制字符
        clean_json = re.sub(r'<think>.*?</think>', '', http_data, flags=re.DOTALL).strip()
        json_match = re.search(r'```json\s*(.*?)\s*```', clean_json, re.DOTALL)
        json_text = json_match.group(1) if json_match else clean_json

        # 清理非法控制字符
        json_text = re.sub(r'[\x00-\x1F\x7F]', '', json_text)
        json_text = json_text.replace('\r', '').replace('\t', '').strip()
        json_text = json_text.rstrip(", \n")

        try:
            analysis_result = json.loads(json_text)
        except json.JSONDecodeError as e:
            print("------ JSON Parse Error ------")
            print(f"Error: {e}")
            print("Raw text snippet:")
            print(json_text[:2000])
            return jsonify({'error': f'JSON解析失败: {str(e)}'}), 500

        return jsonify(analysis_result)

    except Exception as e:
        print(f'[ERROR] Chapter-design failed for bidding {bidding_id}: {str(e)}')
        return jsonify({'error': '章节生成失败，请稍后重试。'}), 500

    



@bp.route('/generate-bid-document', methods=['POST'])
def generate_bid_document():
    """生成完整投标书文件，并在生成 .docx 后构造 OnlyOffice editorConfig 返回"""
    data = request.get_json()
    bidding_id = data.get('biddingId')
    chapter_design = data.get('chapterDesign')
    if not bidding_id:
        return jsonify({'error': 'Missing biddingId'}), 400
    if not chapter_design:
        return jsonify({'error': 'Missing chapterDesign'}), 400

    # 如果前端传的是字符串形式的 JSON，尝试解析
    if isinstance(chapter_design, str):
        try:
            chapter_design = json.loads(chapter_design)
        except Exception as e:
            logging.error(f"chapterDesign JSON 解析失败: {e}")
            return jsonify({'error': 'chapterDesign JSON 解析失败'}), 400
    if isinstance(chapter_design, dict) and 'chapters' in chapter_design:
        chapter_design = chapter_design['chapters']
    if not isinstance(chapter_design, list):
        return jsonify({'error': 'chapterDesign 格式错误，应为章节数组或包含 chapters 的对象'}), 400

    try:
        # 读取 bidding 记录
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bidding WHERE id = ?', (bidding_id,))
        bidding = cursor.fetchone()
        conn.close()
        if not bidding:
            return jsonify({'error': '招标书不存在'}), 404

        tender_name = Path(bidding['original_filename']).stem
        # 如果已经生成 markdown，直接转换
        markdown_file = Path("outputs") / tender_name / f"{tender_name}_完整投标文件.md"
        if markdown_file.exists():
            logging.info("已存在生成的 Markdown 文件，直接调用转换函数。")
            try:
                generated_docx_path = convert_md_to_word(markdown_file)
            except Exception as e:
                logging.exception("convert_md_to_word failed for existing md")
                return jsonify({'error': '已存在 Markdown，但转换为 Word 失败'}), 500

            if not generated_docx_path or not Path(generated_docx_path).exists():
                logging.error(f"convert_md_to_word 未返回有效路径或文件不存在: {generated_docx_path}")
                return jsonify({'error': '已生成 Markdown，但 docx 未找到'}), 500

            generated_docx_path = Path(generated_docx_path)

            # 继续到下面的步骤（复制到 GENERATED_FOLDER、构造 editorConfig 等）
        else:
            # 按原逻辑生成章节内容并合并为 markdown
            # 用你原来的生成逻辑（这里为最小改动保留）
            saved_section_names = []
            for chapter in chapter_design:
                c_type = (chapter.get('type') or "normal").strip().lower()
                c_title = chapter.get('title', "")
                c_content = chapter.get('content', "")
                if c_type == 'table':
                    if c_content:
                        save_bid_section(c_content, c_title, "outputs", tender_name)
                        saved_section_names.append(c_title)
                elif c_type == 'normal':
                    sections = chapter.get('sections', [])
                    tasks = []
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        for section in sections:
                            subsections = section.get('subsections', [])
                            for subsection in subsections:
                                sub_title = subsection.get('title', '')
                                sub_content = subsection.get('describe', '')
                                vector_context = query_chroma(sub_content)
                                if not sub_title or not sub_content:
                                    logging.warning(f"跳过无效的 subsection：{sub_title}")
                                    continue
                                future = executor.submit(generate_bid_section, sub_title, sub_content, vector_context)
                                tasks.append((future, sub_title))
                        for future, sub_title in tasks:
                            try:
                                generated_content = future.result()
                                save_bid_section(generated_content, sub_title, "outputs", tender_name)
                                saved_section_names.append(sub_title)
                            except Exception:
                                logging.exception("generate_bid_section failed for %s", sub_title)
                else:
                    logging.warning(f"未知的 chapter type '{c_type}'，跳过：{c_title}")

            merged_md_path = merge_sections("outputs", tender_name, saved_section_names)
            if not merged_md_path:
                logging.error("合并章节生成 Markdown 失败。")
                return jsonify({'error': '合并章节失败'}), 500

            try:
                generated_docx_path = convert_md_to_word(merged_md_path)
            except Exception:
                logging.exception("convert_md_to_word failed")
                return jsonify({'error': 'Markdown 转 Word 失败'}), 500

            if not generated_docx_path or not Path(generated_docx_path).exists():
                logging.error(f"convert_md_to_word 未返回有效路径或文件不存在: {generated_docx_path}")
                return jsonify({'error': '生成的 docx 文件不存在'}), 500

            generated_docx_path = Path(generated_docx_path)

        # === 下面开始：把生成的 docx 放到 GENERATED_FOLDER 并构造 OnlyOffice editorConfig（内联实现） ===
        

        gen_folder = Path(current_app.config.get('GENERATED_FOLDER', 'outputs'))
        gen_folder.mkdir(parents=True, exist_ok=True)

        safe_name = secure_filename(generated_docx_path.name)
        target = gen_folder / safe_name
        if generated_docx_path.resolve() != target.resolve():
            shutil.copy2(str(generated_docx_path), str(target))

        backend_url = get_backend_public_base_url()
        file_url = f"{backend_url}/api/outputs/{target.name}"
        callback_url = f"{backend_url}/api/bidding/save-callback"

        # document key（用于 OnlyOffice 缓存），使用 DB 中已有的或者新生成
        doc_key = bidding[4]

        payload = {
            'document': {
                'fileType': 'docx',
                'key': doc_key,
                'title': bidding['original_filename'],
                'url': file_url,
            },
            'documentType': 'word',
            'editorConfig': {
                'callbackUrl': callback_url,
                'mode': 'edit',
                'user': {
                    'id': f"user-{bidding['user_id']}",
                    'name': 'Reviewer'
                },
                'customization': {'forcesave': True}
            }
        }

        # 生成JWT令牌
        token = jwt.encode(payload, ONLYOFFICE_JWT_SECRET, algorithm='HS256')
        editor_config_with_token = {**payload, 'token': token}
        

        # 更新 DB：记录生成的 docx 路径与 document_key、状态
        conn = get_db()
        cur = conn.cursor()
        cur.execute('UPDATE bidding SET bid_document=?, document_key=?, status=? WHERE id=?',
                    (str(target), doc_key, 'Generated', bidding['id']))
        conn.commit()
        conn.close()

        # 返回 editorConfig 给前端，前端用此配置初始化 OnlyOffice
        return jsonify({
            'message': '投标文件已生成',
            'markdown': str(markdown_file if markdown_file.exists() else merged_md_path),
            'editorConfig': editor_config_with_token,
            'fileUrl': file_url,
            'downloadUrl': f"/api/outputs/{target.name}"
        }), 201

    except Exception as e:
        logging.exception(f"生成投标书过程出错: {e}")
        return jsonify({'error': f'生成投标书失败: {str(e)}'}), 500
