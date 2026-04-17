import os
import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI
import hashlib
from pathlib import Path

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
# 初始化阿里云百炼客户端
def init_ali_client():
    """初始化阿里云百炼OpenAI兼容客户端"""
    return OpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

# 读取文件内容
def read_file_content(file_path):
    """读取文件内容，支持文本、docx、pdf。"""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".docx":
        import mammoth
        with open(file_path, "rb") as f:
            return mammoth.extract_raw_text(f).value
    if suffix == ".pdf":
        import PyPDF2
        text = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text.append(page.extract_text() or "")
        return "\n".join(text)

    # 编码尝试顺序：优先utf-8系列，再扩展中文字符集，最后兼容所有字节
    encodings = ['utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'latin-1']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue  # 尝试下一种编码
        except Exception as e:
            raise Exception(f"读取文件失败: {str(e)}")
    
    # 如果所有编码都尝试失败
    raise Exception(f"无法解析文件编码，已尝试编码: {encodings}")


# 初始化Chroma客户端
def init_chroma_client(persist_directory="./chroma_db"):
    """初始化Chroma客户端并返回集合"""
    client = chromadb.PersistentClient(path=persist_directory)
    # 创建或获取集合
    collection = client.get_or_create_collection(name="document_embeddings")
    return collection

# 文本分片处理（新增函数）
def split_text(text, max_length=8000):
    """
    将长文本分割成符合模型长度要求的分片
    max_length设置为8000，预留一定空间避免超出8192限制
    """
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + max_length
        # 避免在单词中间分割（简单处理）
        if end < text_length:
            # 找到最近的换行或空格
            split_pos = text.rfind('\n', start, end)
            if split_pos == -1:
                split_pos = text.rfind(' ', start, end)
            if split_pos != -1:
                end = split_pos
        
        chunk = text[start:end].strip()
        if chunk:  # 只添加非空分片
            chunks.append(chunk)
        
        start = end
    
    return chunks

# 修改向量化函数，支持批量处理分片

def get_embeddings(client, texts, batch_size=10):
    """
    批量生成向量，处理分片后的文本
    支持自动分批，确保不超过模型的批量限制
    """
    all_embeddings = []
    # 按批次处理
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i+batch_size]
        response = client.embeddings.create(
            model="text-embedding-v3",
            input=batch_texts
        )
        # 提取当前批次的向量并添加到结果列表
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
    
    return all_embeddings

# 修改主函数，支持长文本分片存储
def file_to_chroma(file_path, collection=None):
    """
    将指定文件向量化并存储到Chroma向量数据库
    支持长文本自动分片
    """
    # 初始化客户端
    ali_client = init_ali_client()
    if not collection:
        collection = init_chroma_client()
    
    # 读取文件内容
    content = read_file_content(file_path)
    file_name = os.path.basename(file_path)
    
    # 长文本分片
    chunks = split_text(content)
    if not chunks:
        raise Exception("文件内容为空或无法分割")
    
    # 批量生成向量
    embeddings = get_embeddings(ali_client, chunks)
    
    # 生成唯一ID（文件名+分片索引+内容哈希）
    doc_ids = []
    metadatas = []
    for i, chunk in enumerate(chunks):
        content_hash = hashlib.md5(chunk.encode()).hexdigest()
        doc_id = f"file_{file_name}_chunk_{i}_{content_hash}"
        doc_ids.append(doc_id)
        metadatas.append({
            "file_name": file_name,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "hash": content_hash
        })
    
    # 存储到Chroma
    collection.add(
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=doc_ids
    )
    
    return {
        "status": "success",
        "file_name": file_name,
        "total_chunks": len(chunks),
        "message": f"文件已成功分片向量化并存储到Chroma，共{len(chunks)}个分片"
    }
def query_chroma(query_content, limit=3, collection=None):
    """
    从Chroma向量数据库中查询与输入内容相似的文档
    
    参数:
        query_content: 要查询的内容，可为字符串或字符串列表
        limit: 返回结果的数量，默认3条
        collection: 可选，已存在的Chroma集合对象
        
    返回:
        包含相似文档的查询结果，如果是多查询则返回列表
    """
    # 初始化客户端
    ali_client = init_ali_client()
    if not collection:
        collection = init_chroma_client()
    
    # 处理单条查询和多条查询的情况
    is_single_query = not isinstance(query_content, list)
    if is_single_query:
        query_contents = [query_content]
    else:
        query_contents = query_content
    
    # 生成查询向量 - 现在支持批量生成
    query_embeddings = get_embeddings(ali_client, query_contents)
    
    # 执行查询
    results = collection.query(
        query_embeddings=query_embeddings,
        n_results=limit,
        include=["documents", "metadatas", "distances"]
    )
    
    # 格式化结果
    formatted_results = []
    for query_idx in range(len(results["ids"])):
        query_result = []
        for doc_idx in range(len(results["ids"][query_idx])):
            query_result.append({
                "document_id": results["ids"][query_idx][doc_idx],
                "file_name": results["metadatas"][query_idx][doc_idx]["file_name"],
                "content": results["documents"][query_idx][doc_idx],
                "similarity": 1 - results["distances"][query_idx][doc_idx],  # 转换为相似度分数（0-1）
                "distance": results["distances"][query_idx][doc_idx]  # 原始距离值
            })
        
        formatted_results.append({
            "status": "success",
            "query": query_contents[query_idx],
            "results_count": len(query_result),
            "results": query_result
        })
    
    # 如果是单查询，直接返回单个结果，否则返回结果列表
    return formatted_results[0] if is_single_query else formatted_results


# 本地维护入口
if __name__ == "__main__":
    # 确保环境变量中设置了API密钥
    if not os.getenv("DASHSCOPE_API_KEY"):
        raise EnvironmentError("请设置环境变量DASHSCOPE_API_KEY")
    
    # 处理指定文件并写入企业知识库
    # file_result = file_to_chroma("enterprise_knowledge.txt")
    # print("文件处理结果:", file_result)
    
    # 查询企业知识库相似内容
    query_result = query_chroma("需要查询的内容")
    print("\n查询结果:")
    for i, item in enumerate(query_result["results"], 1):
        print(f"\n结果 {i}:")
        print(f"文件名: {item['file_name']}")
        print(f"相似度: {item['similarity']:.4f}")
        print(f"内容片段: {item['content'][:200]}...")  # 只显示前200字符
    
