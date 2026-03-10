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

# 操作向量数据库的函数
from file_to_chroma import file_to_chroma, query_chroma
# 创建蓝图
bp = Blueprint('bidding', __name__)

# 环境变量
ONLYOFFICE_JWT_SECRET = os.getenv('ONLYOFFICE_JWT_SECRET', 'fsdftertrt34768586sfhjsdhfjhhjfsuhaiubue')
BACKEND_URL_FOR_DOCKER = os.getenv('BACKEND_URL_FOR_DOCKER', 'host.docker.internal:3000')
APP_HOST = os.getenv('APP_HOST', 'localhost:3000')

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
        
        # 保存合并后的文档
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
    """上传招标文件"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded.'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400
    
    user_id = request.form.get('userId')
    if not user_id:
        return jsonify({'error': 'User ID is required for upload.'}), 400
    
    try:
        # 获取原始文件名
        original_filename = file.filename
        
        # 生成安全的存储文件名（用于文件系统）
        safe_filename = secure_filename(original_filename)
        unique_filename = f"{uuid.uuid4()}-{safe_filename}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        
        # 保存文件
        file.save(file_path)
        file_to_chroma(file_path)
        # 生成文档密钥
        document_key = str(uuid.uuid4())
        
        # 保存到数据库（使用原始文件名）
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bidding (user_id, original_filename, storage_path, document_key, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, original_filename, file_path, document_key, 'Uploaded'))
        
        bidding_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 生成OnlyOffice配置
        backend_url = BACKEND_URL_FOR_DOCKER or APP_HOST or 'localhost:3000'
        file_url = f"http://{backend_url}/api/outputs/{unique_filename}"
        callback_url = f"http://{backend_url}/api/bidding/save-callback"

        payload_object = {
            'document': {
                'fileType': 'docx',
                'key': document_key,
                'title': original_filename,
                'url': file_url,
            },
            'documentType': 'word',
            'editorConfig': {
                'callbackUrl': callback_url,
                'mode': 'edit',
                'user': {
                    'id': 'user-1',
                    'name': 'Reviewer'
                },
                'customization': {
                    'forcesave': True,
                },
            },
        }
        
        # 生成JWT令牌
        token = jwt.encode(payload_object, ONLYOFFICE_JWT_SECRET, algorithm='HS256')
        editor_config_with_token = {**payload_object, 'token': token}
        
        return jsonify({
            'message': 'File uploaded, editor config generated.',
            'biddingId': bidding_id,
            'editorConfig': editor_config_with_token,
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Server error during file upload: {str(e)}'}), 500
    
@bp.route('/save-callback', methods=['POST'])
def save_callback():
    """OnlyOffice保存回调"""
    try:
        body = request.get_json()
        print(f'[INFO] Save callback received: {json.dumps(body, indent=2)}')
        
        if body.get('status') in [2, 6]:  # 2=ready for save, 6=must-save
            download_url = body.get('url')
            document_key = body.get('key')
            
            if not download_url:
                print(f'[WARN] No download URL provided for key {document_key}')
                return jsonify({'error': 0})
            
            # 获取招标信息
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM bidding WHERE document_key = ?', (document_key,))
            bidding = cursor.fetchone()
            
            if not bidding:
                print(f'[ERROR] Bidding with key {document_key} not found')
                return jsonify({'error': 0})
            
            # 下载并保存文件
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            with open(bidding['storage_path'], 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f'[INFO] Document {bidding["original_filename"]} updated successfully')
            conn.close()
        
        return jsonify({'error': 0})
        
    except Exception as e:
        print(f'[ERROR] Save callback failed: {str(e)}')
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
        http_data = response['output']['text']

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
        http_data = response['output']['text']

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
    analysis_data = data.get('analysisData')
    directory_structure = data.get('directoryStructure')
    if not all([bidding_id,analysis_data,directory_structure]):
        return jsonify({'error': 'Incomplete analysis request'}), 400


    #分析提示
    bidding_requirements = analysis_data.get('bidding_name') #必须包含的文件和材料。
    bidding_summary = analysis_data.get('bidding_summary') #对招标书内容的总结，包括服务内容、服务期限与服务地点以及质量标准等。
    bidding_meta = analysis_data.get('bidding_meta') #招标书中具体的实质性要求内容和评分标准。
    chapter_design_prompt = (
    f"你是一个资深的投标文件目录结构设计专家，请根据以下信息，整理出最终的标书章节结构：\n\n"
    f"必须包含的文件和材料：{bidding_requirements}\n"
    f"招标书内容总结：{bidding_summary}\n"
    f"招标书具体要求和评分标准：{bidding_meta}\n"
    f"投标书章节大纲：{directory_structure}\n\n"
    "基于以上招标文件要求和行业经验，请补充章节的子节目录，确保投标文件完整且符合要求。"
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
}
'''
    "字段说明：\n"
    "1、title：章节标题。\n"
    "2、type：章节类型，normal表示文本章节，table表示表格章节。如果章节标题是xxx表、xxx函、xxx清单、封面等，就是table类型。\n"
    "3、content：如果是table章节，则需要填写原本章节内容。\n"
    "4、sections：二级标题。\n"
    "5、subsections：三级标题，最少5-7点三级标题。\n"
    "6、describe：三级标题内容的描述。\n"

    )
    try:
        response = call_dashscope_api([
            {'role': 'user', 'content': chapter_design_prompt}
        ])
        http_data = response['output']['text']

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
        print(f'[ERROR] Chapter-design failed for bidding {bidding_id}: {str(e)}')
        return jsonify({'error': '章节生成失败，请稍后重试。'}), 500
    



@bp.route('/generate-bid-document', methods=['POST'])
def generate_bid_document():
    """生成完整投标书文件"""
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
        
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bidding WHERE id = ?', (bidding_id,))
        bidding = cursor.fetchone()
        conn.close()
        if not bidding:
            return jsonify({'error': '招标书不存在'}), 404
        
        tender_name = Path(bidding['original_filename']).stem
        markdown_file = Path("outputs") / tender_name / f"{tender_name}_完整投标文件.md"
        if markdown_file.exists():
            logging.info("已存在生成的 Markdown 文件，直接调用转换函数。")
            try:
                convert_md_to_word(markdown_file)
            except Exception as e:
                logging.error(f"convert_md_to_word 失败: {e}", exc_info=True)
                return jsonify({'error': '已存在 Markdown，但转换为 Word 失败'}), 500
            return jsonify({'message': '已存在 Markdown，已生成 Word', 'markdown': str(markdown_file)}), 200

        
        # 读取文件内容
        bid_content = read_tender_file(bidding_id) 


        if bid_content is None:
            logging.error(f"无法读取招标文件。")
            return
        
        # 用于记录保存顺序的章节名列表（merge_sections 需要）
        saved_section_names = []
        
        # 提取章节设计
        for chapter in chapter_design.get('chapters', []):
            c_type = (chapter.get('type') or "normal").strip().lower()
            c_title = chapter.get('title', "")
            c_content = chapter.get('content', "")
            if c_type == 'table':
                if c_content:
                    save_bid_section(c_content, c_title, "outputs", tender_name)
                    saved_section_names.append(c_title)
                    logging.info(f"保存章节 '{c_title}'。")
                else:
                    logging.warning(f"章节 '{c_title}' 标注为 table，但 content 为空，跳过保存。")
            
            elif c_type == 'normal':
                sections = chapter.get('sections', [])
                tasks = []  # 用来存储 future 和标题
                with ThreadPoolExecutor(max_workers=8) as executor:
                    for section in sections:
                        subsections = section.get('subsections', [])
                        for subsection in subsections:
                            sub_title = subsection.get('title', '')
                            sub_content = subsection.get('describe', '')
                            vector_context = query_chroma(sub_content)
                            if not sub_title or not sub_content:
                                logging.warning(f"跳过无效的 subsection（title 或 describe 为空）：chapter={c_title}, section={section.get('title')}")
                                continue

                            future = executor.submit(generate_bid_section, sub_title, sub_content, vector_context)
                            tasks.append((future, sub_title))
                    for future, sub_title in tasks:
                        try:
                            generated_content = future.result()
                            # 保存为章节文件（文件名使用小节标题）
                            save_bid_section(generated_content, sub_title, "outputs", tender_name)
                            saved_section_names.append(sub_title)
                        except Exception as e:
                            logging.error(f"调用 generate_bid_section 生成 '{sub_title}' 失败: {e}")
            else:
                logging.warning(f"未知的 chapter type '{c_type}'，跳过：{c_title}")

        merged_md_path = merge_sections("outputs", tender_name, saved_section_names)
        if not merged_md_path:
            logging.error("合并章节生成 Markdown 失败。")
            return jsonify({'error': '合并章节失败'}), 500        
        

    
        try:
            convert_md_to_word(merged_md_path)
        except Exception as e:
            logging.error(f"Markdown 转 Word 失败: {e}")
            return jsonify({'error': 'Markdown 转 Word 失败'}), 500

        return jsonify({'message': '投标文件已生成', 'markdown': str(merged_md_path)}), 201

    except Exception as e:
        logging.error(f"生成投标书过程出错: {e}")
        return jsonify({'error': f'生成投标书失败: {str(e)}'}), 500

