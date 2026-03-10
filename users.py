from flask import Blueprint, request, jsonify
import sqlite3
import json

# 创建蓝图
bp = Blueprint('users', __name__)

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect('bidding.db')
    conn.row_factory = sqlite3.Row
    return conn

@bp.route('/identify', methods=['POST'])
def identify_user():
    """用户识别"""
    data = request.get_json()
    fingerprint_id = data.get('fingerprintId')
    
    if not fingerprint_id:
        return jsonify({'error': 'Fingerprint ID is required.'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # 查找现有用户
        cursor.execute('SELECT * FROM users WHERE fingerprint_id = ?', (fingerprint_id,))
        user = cursor.fetchone()
        
        if user:
            # 用户已存在
            conn.close()
            return jsonify({'userId': user['id'], 'isNew': False})
        else:  
            return jsonify("用户不存在"), 404
            
    except Exception as e:
        print(f'[ERROR] User identification failed: {str(e)}')
        return jsonify({'error': 'Failed to identify or create user.'}), 500

