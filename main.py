from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
import uuid
import json

# 加载环境变量
load_dotenv()

app = Flask(__name__)
CORS(app)

# 配置
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['GENERATED_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['GENERATED_FOLDER'], exist_ok=True)

# 数据库初始化
def init_db():
    conn = sqlite3.connect('bidding.db')
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建招投标文件表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bidding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            document_key TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT '已上传',
            other_response_format TEXT,
            bid_document TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

# 初始化数据库
init_db()

import routes
import users

# 注册蓝图
app.register_blueprint(routes.bp, url_prefix='/api/bidding')
app.register_blueprint(users.bp, url_prefix='/api/users')

@app.route('/api/outputs/<path:filename>')
def output_file(filename):
    file_path = os.path.join(app.config['GENERATED_FOLDER'], filename)
    print(f"输出文件访问: {file_path}, Exists: {os.path.exists(file_path)}")
    return send_from_directory(app.config['GENERATED_FOLDER'], filename)

@app.route('/')
@app.route('/bidding')
def bidding_workbench():
    return send_from_directory('.', 'bidding_workbench.html')

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3012))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode) 
