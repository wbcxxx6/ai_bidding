from flask import Blueprint, request, jsonify, current_app
import os
import sqlite3
import requests
from datetime import datetime
from unidecode import unidecode
from werkzeug.utils import secure_filename
import logging

# 通义千问API配置
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
DASHSCOPE_MODEL = os.getenv('DASHSCOPE_MODEL', 'qwen-turbo-latest')
AI_PROVIDER = os.getenv('AI_PROVIDER', 'dashscope')


def call_dashscope_api(messages, model=None, json_mode=True):
    if not DASHSCOPE_API_KEY:
        raise Exception("DASHSCOPE_API_KEY is not set")
    url = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation'
    headers = {
        'Authorization': f'Bearer {DASHSCOPE_API_KEY}',
        'Content-Type': 'application/json'
    }

    data = {
        'model': model or DASHSCOPE_MODEL,
        'input': {
            'messages': messages
        }
    }
    if json_mode:
        data['parameters'] = {'result_format': 'json_object'}
    else:
        data['parameters'] = {'result_format': 'message'}
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        error_message = f"Dashscope API Error: Status Code: {response.status_code}, Response Body: {response.text}"
        logging.error(error_message)
        print(error_message)
    response.raise_for_status()
    return response.json()

def generate_bid_section(section_title, section_content, tender_content):
    """按小节生成投标文件内容"""
    prompt = f'''
    你是湖北恩施水利配套制造企业的专业投标书撰写专家，熟悉三峡集团及水利工程供应链项目的投标要求。企业业务聚焦涡片、螺母、紧固件、金属结构件、设备配套加工、质量检验、交付保障和现场服务。请结合企业制造能力、质量管理、内网资料库和招标文件要求，直接输出专业、严谨、可落地的正文内容。
    请根据以下小节标题、小节描述并参考招标书相关内容，生成投标书某一小节的完整内容。如果小节需要表格描述，请用Markdown格式生成表格。
    需要填写的表格内容请参考招标书原文中进行填写。
    仅输出小节正文内容，禁止包含任何自然语言解释或额外文。字数要求1000-1500字。
    小节标题: {section_title}
    小节描述: {section_content}
    招标书相关内容: {tender_content}
'''
    response = call_dashscope_api([
                {'role': 'user','content': prompt}
            ], json_mode=False)
    content = response['output']['choices'][0]['message']['content']
    return content
