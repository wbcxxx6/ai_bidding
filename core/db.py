import os
from datetime import datetime

import pymysql
from pymysql.cursors import DictCursor


MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "123456")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "bidding")
MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")


class CompatCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def execute(self, sql, params=None):
        return self._cursor.execute(sql.replace("?", "%s"), params)

    def executemany(self, sql, params=None):
        return self._cursor.executemany(sql.replace("?", "%s"), params)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        return self._cursor.close()


class CompatConnection:
    row_factory = None

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return CompatCursor(self._conn.cursor())

    def execute(self, sql, params=None):
        cursor = self.cursor()
        cursor.execute(sql, params)
        return cursor

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


def _connect(database=None):
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=database,
        charset=MYSQL_CHARSET,
        cursorclass=DictCursor,
        autocommit=False,
    )


def get_db():
    return CompatConnection(_connect(MYSQL_DATABASE))


def _execute_many(conn, statements):
    with conn.cursor() as cursor:
        for statement in statements:
            try:
                cursor.execute(statement)
            except pymysql.err.OperationalError as exc:
                if exc.args and exc.args[0] in (1060, 1061, 1068):
                    continue
                raise
    conn.commit()


def init_mysql():
    server = _connect()
    try:
        with server.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        server.commit()
    finally:
        server.close()

    conn = _connect(MYSQL_DATABASE)
    try:
        _execute_many(conn, SCHEMA_STATEMENTS)
        seed_defaults(conn)
    finally:
        conn.close()


def seed_defaults(conn):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT IGNORE INTO tenants (id, tenant_code, tenant_name, status, created_at, updated_at)
            VALUES (1, 'default', '默认租户', 'active', %s, %s)
            """,
            (now, now),
        )
        cursor.execute(
            """
            INSERT IGNORE INTO companies (id, tenant_id, company_name, status, created_at, updated_at)
            VALUES (1, 1, '默认企业', 'active', %s, %s)
            """,
            (now, now),
        )
        cursor.execute(
            """
            INSERT IGNORE INTO roles (id, tenant_id, role_code, role_name, created_at, updated_at)
            VALUES (1, 1, 'project_owner', '项目负责人', %s, %s)
            """,
            (now, now),
        )
        cursor.execute(
            """
            INSERT IGNORE INTO knowledge_bases
            (id, tenant_id, company_id, kb_name, kb_type, visibility_scope, status, created_by, created_at, updated_at)
            VALUES (1, 1, 1, '默认企业知识库', 'enterprise', 'tenant', 'active', NULL, %s, %s)
            """,
            (now, now),
        )
    conn.commit()


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_code VARCHAR(64) NOT NULL UNIQUE,
        tenant_name VARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        deleted_at DATETIME NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS companies (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        company_name VARCHAR(255) NOT NULL,
        unified_social_credit_code VARCHAR(64) NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        deleted_at DATETIME NULL,
        INDEX idx_company_tenant (tenant_id),
        CONSTRAINT fk_companies_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        fingerprint_id VARCHAR(255) UNIQUE NULL,
        username VARCHAR(128) NULL,
        display_name VARCHAR(128) NULL,
        email VARCHAR(255) NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        deleted_at DATETIME NULL,
        INDEX idx_users_tenant (tenant_id),
        CONSTRAINT fk_users_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS roles (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        role_code VARCHAR(64) NOT NULL,
        role_name VARCHAR(128) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uk_role_code (tenant_id, role_code),
        CONSTRAINT fk_roles_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS user_roles (
        user_id BIGINT UNSIGNED NOT NULL,
        role_id BIGINT UNSIGNED NOT NULL,
        tenant_id BIGINT UNSIGNED NOT NULL,
        created_at DATETIME NOT NULL,
        PRIMARY KEY (user_id, role_id),
        CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id) REFERENCES roles(id),
        CONSTRAINT fk_user_roles_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_projects (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        company_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_code VARCHAR(64) NOT NULL,
        project_name VARCHAR(500) NOT NULL,
        purchaser_name VARCHAR(255) NULL,
        agency_name VARCHAR(255) NULL,
        procurement_method VARCHAR(64) NULL,
        industry VARCHAR(128) NULL,
        region VARCHAR(128) NULL,
        budget_amount DECIMAL(18,2) NULL,
        bid_deadline DATETIME NULL,
        project_status VARCHAR(32) NOT NULL DEFAULT 'draft',
        owner_user_id BIGINT UNSIGNED NULL,
        analysis_data JSON NULL,
        directory_structure JSON NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        deleted_at DATETIME NULL,
        UNIQUE KEY uk_project_code (tenant_id, project_code),
        INDEX idx_project_status (tenant_id, project_status),
        CONSTRAINT fk_projects_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_projects_company FOREIGN KEY (company_id) REFERENCES companies(id),
        CONSTRAINT fk_projects_owner FOREIGN KEY (owner_user_id) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS project_members (
        project_id BIGINT UNSIGNED NOT NULL,
        tenant_id BIGINT UNSIGNED NOT NULL,
        user_id BIGINT UNSIGNED NOT NULL,
        project_role VARCHAR(64) NOT NULL,
        joined_at DATETIME NOT NULL,
        PRIMARY KEY (project_id, user_id),
        CONSTRAINT fk_project_members_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_project_members_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_project_members_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS project_facts (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        project_id BIGINT UNSIGNED NOT NULL,
        fact_key VARCHAR(128) NOT NULL,
        fact_label VARCHAR(128) NOT NULL,
        fact_value TEXT NOT NULL,
        normalized_value VARCHAR(1000) NULL,
        value_type VARCHAR(32) NOT NULL DEFAULT 'text',
        source_type VARCHAR(64) NOT NULL DEFAULT 'tender',
        source_ref_id BIGINT UNSIGNED NULL,
        confidence DECIMAL(5,4) NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'extracted',
        confirmed_by BIGINT UNSIGNED NULL,
        confirmed_at DATETIME NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uk_project_fact (project_id, fact_key),
        INDEX idx_project_facts_tenant (tenant_id),
        CONSTRAINT fk_project_facts_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_project_facts_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS document_files (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        company_id BIGINT UNSIGNED NULL,
        project_id BIGINT UNSIGNED NULL,
        owner_user_id BIGINT UNSIGNED NULL,
        file_category VARCHAR(64) NOT NULL,
        original_filename VARCHAR(500) NOT NULL,
        storage_bucket VARCHAR(128) NOT NULL DEFAULT 'local',
        storage_key VARCHAR(1000) NOT NULL,
        file_ext VARCHAR(32) NULL,
        mime_type VARCHAR(128) NULL,
        file_size BIGINT UNSIGNED NULL,
        sha256_hash CHAR(64) NULL,
        parse_status VARCHAR(32) NOT NULL DEFAULT 'pending',
        vector_status VARCHAR(32) NOT NULL DEFAULT 'pending',
        confidentiality_level VARCHAR(32) NOT NULL DEFAULT 'internal',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        deleted_at DATETIME NULL,
        INDEX idx_file_tenant_category (tenant_id, file_category),
        INDEX idx_file_project (project_id),
        INDEX idx_file_hash (tenant_id, sha256_hash),
        CONSTRAINT fk_files_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_files_company FOREIGN KEY (company_id) REFERENCES companies(id),
        CONSTRAINT fk_files_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_files_owner FOREIGN KEY (owner_user_id) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS document_versions (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        file_id BIGINT UNSIGNED NOT NULL,
        tenant_id BIGINT UNSIGNED NOT NULL,
        version_no INT NOT NULL,
        storage_bucket VARCHAR(128) NOT NULL DEFAULT 'local',
        storage_key VARCHAR(1000) NOT NULL,
        file_size BIGINT UNSIGNED NULL,
        sha256_hash CHAR(64) NULL,
        change_source VARCHAR(64) NOT NULL,
        created_by BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        UNIQUE KEY uk_file_version (file_id, version_no),
        CONSTRAINT fk_versions_file FOREIGN KEY (file_id) REFERENCES document_files(id),
        CONSTRAINT fk_versions_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS document_file_blobs (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        file_id BIGINT UNSIGNED NOT NULL,
        version_id BIGINT UNSIGNED NULL,
        content LONGBLOB NOT NULL,
        content_text LONGTEXT NULL,
        content_encoding VARCHAR(32) NULL,
        created_at DATETIME NOT NULL,
        INDEX idx_blob_file (file_id),
        INDEX idx_blob_version (version_id),
        CONSTRAINT fk_blobs_file FOREIGN KEY (file_id) REFERENCES document_files(id),
        CONSTRAINT fk_blobs_version FOREIGN KEY (version_id) REFERENCES document_versions(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_bases (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        company_id BIGINT UNSIGNED NULL,
        department_id BIGINT UNSIGNED NULL,
        kb_name VARCHAR(255) NOT NULL,
        kb_type VARCHAR(64) NOT NULL,
        description TEXT NULL,
        visibility_scope VARCHAR(32) NOT NULL DEFAULT 'tenant',
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        created_by BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        deleted_at DATETIME NULL,
        CONSTRAINT fk_kb_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_kb_company FOREIGN KEY (company_id) REFERENCES companies(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_documents (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        knowledge_base_id BIGINT UNSIGNED NOT NULL,
        file_id BIGINT UNSIGNED NOT NULL,
        doc_title VARCHAR(500) NOT NULL,
        doc_type VARCHAR(64) NOT NULL,
        industry VARCHAR(128) NULL,
        tags_json JSON NULL,
        source_project_name VARCHAR(255) NULL,
        source_customer_name VARCHAR(255) NULL,
        bid_result VARCHAR(32) NULL,
        reuse_policy VARCHAR(32) NOT NULL DEFAULT 'rewrite_required',
        review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
        approved_by BIGINT UNSIGNED NULL,
        approved_at DATETIME NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        deleted_at DATETIME NULL,
        INDEX idx_kdoc_kb (knowledge_base_id),
        INDEX idx_kdoc_type (tenant_id, doc_type),
        CONSTRAINT fk_kdoc_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_kdoc_kb FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id),
        CONSTRAINT fk_kdoc_file FOREIGN KEY (file_id) REFERENCES document_files(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS document_chunks (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        chunk_uid VARCHAR(128) UNIQUE NOT NULL,
        tenant_id BIGINT UNSIGNED NOT NULL,
        knowledge_base_id BIGINT UNSIGNED NULL,
        knowledge_document_id BIGINT UNSIGNED NULL,
        file_id BIGINT UNSIGNED NOT NULL,
        project_id BIGINT UNSIGNED NULL,
        doc_type VARCHAR(64) NOT NULL,
        section_path VARCHAR(1000) NULL,
        page_start INT NULL,
        page_end INT NULL,
        chunk_index INT NOT NULL,
        chunk_text MEDIUMTEXT NULL,
        chunk_summary TEXT NULL,
        token_count INT NULL,
        embedding_model VARCHAR(128) NULL,
        vector_collection VARCHAR(128) NOT NULL DEFAULT 'document_embeddings',
        vector_id VARCHAR(128) NULL,
        metadata_json JSON NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'indexed',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_chunk_tenant_type (tenant_id, doc_type),
        INDEX idx_chunk_file (file_id),
        INDEX idx_chunk_project (project_id),
        CONSTRAINT fk_chunks_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_chunks_file FOREIGN KEY (file_id) REFERENCES document_files(id),
        CONSTRAINT fk_chunks_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_chunks_kdoc FOREIGN KEY (knowledge_document_id) REFERENCES knowledge_documents(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_documents (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        project_id BIGINT UNSIGNED NOT NULL,
        document_title VARCHAR(500) NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'draft',
        current_version_id BIGINT UNSIGNED NULL,
        created_by BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        deleted_at DATETIME NULL,
        INDEX idx_bid_docs_project (project_id),
        CONSTRAINT fk_bid_docs_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_bid_docs_project FOREIGN KEY (project_id) REFERENCES bid_projects(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_document_versions (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        bid_document_id BIGINT UNSIGNED NOT NULL,
        version_no INT NOT NULL,
        file_id BIGINT UNSIGNED NULL,
        markdown_storage_key VARCHAR(1000) NULL,
        change_summary VARCHAR(500) NULL,
        created_by BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        UNIQUE KEY uk_bid_doc_version (bid_document_id, version_no),
        CONSTRAINT fk_bid_doc_versions_doc FOREIGN KEY (bid_document_id) REFERENCES bid_documents(id),
        CONSTRAINT fk_bid_doc_versions_file FOREIGN KEY (file_id) REFERENCES document_files(id),
        CONSTRAINT fk_bid_doc_versions_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_chapters (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        bid_document_id BIGINT UNSIGNED NOT NULL,
        project_id BIGINT UNSIGNED NOT NULL,
        parent_chapter_id BIGINT UNSIGNED NULL,
        chapter_title VARCHAR(500) NOT NULL,
        chapter_type VARCHAR(64) NOT NULL DEFAULT 'normal',
        sort_order INT NOT NULL DEFAULT 0,
        outline_json JSON NULL,
        current_version_id BIGINT UNSIGNED NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'draft',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_chapters_project (project_id),
        CONSTRAINT fk_chapters_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_chapters_doc FOREIGN KEY (bid_document_id) REFERENCES bid_documents(id),
        CONSTRAINT fk_chapters_project FOREIGN KEY (project_id) REFERENCES bid_projects(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS bid_chapter_versions (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        chapter_id BIGINT UNSIGNED NOT NULL,
        version_no INT NOT NULL,
        content LONGTEXT NULL,
        evidence_pack_id BIGINT UNSIGNED NULL,
        generation_task_id BIGINT UNSIGNED NULL,
        agent_run_id BIGINT UNSIGNED NULL,
        word_count INT NULL,
        review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
        change_source VARCHAR(64) NOT NULL DEFAULT 'system_generated',
        created_by BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        UNIQUE KEY uk_chapter_version (chapter_id, version_no),
        CONSTRAINT fk_chapter_versions_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_chapter_versions_chapter FOREIGN KEY (chapter_id) REFERENCES bid_chapters(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS generation_tasks (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        project_id BIGINT UNSIGNED NOT NULL,
        task_type VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        input_json JSON NULL,
        output_json JSON NULL,
        error_message TEXT NULL,
        started_at DATETIME NULL,
        finished_at DATETIME NULL,
        created_by BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_generation_project (project_id, status),
        CONSTRAINT fk_generation_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_generation_project FOREIGN KEY (project_id) REFERENCES bid_projects(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL,
        generation_task_id BIGINT UNSIGNED NULL,
        project_id BIGINT UNSIGNED NULL,
        agent_name VARCHAR(128) NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        input_json JSON NULL,
        output_json JSON NULL,
        error_message TEXT NULL,
        started_at DATETIME NULL,
        finished_at DATETIME NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_agent_task (generation_task_id),
        CONSTRAINT fk_agent_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_agent_task FOREIGN KEY (generation_task_id) REFERENCES generation_tasks(id),
        CONSTRAINT fk_agent_project FOREIGN KEY (project_id) REFERENCES bid_projects(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS model_call_logs (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NULL,
        generation_task_id BIGINT UNSIGNED NULL,
        provider_code VARCHAR(64) NOT NULL,
        model_name VARCHAR(128) NOT NULL,
        prompt_tokens INT NULL,
        completion_tokens INT NULL,
        latency_ms INT NULL,
        status VARCHAR(32) NOT NULL,
        error_message TEXT NULL,
        created_at DATETIME NOT NULL,
        INDEX idx_model_logs_project (project_id),
        CONSTRAINT fk_model_logs_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS rag_evidence_packs (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        bid_chapter_id BIGINT UNSIGNED NULL,
        query_text TEXT NULL,
        context_summary TEXT NULL,
        degraded TINYINT(1) NOT NULL DEFAULT 0,
        degraded_reason TEXT NULL,
        created_by_agent_run_id BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        INDEX idx_evidence_pack_project (project_id, bid_chapter_id),
        CONSTRAINT fk_evidence_pack_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_evidence_pack_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_evidence_pack_chapter FOREIGN KEY (bid_chapter_id) REFERENCES bid_chapters(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS rag_evidence_items (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        evidence_pack_id BIGINT UNSIGNED NOT NULL,
        source_type VARCHAR(64) NOT NULL,
        source_file_id BIGINT UNSIGNED NULL,
        chunk_id BIGINT UNSIGNED NULL,
        chunk_uid VARCHAR(128) NULL,
        source_title VARCHAR(500) NULL,
        evidence_text MEDIUMTEXT NOT NULL,
        similarity DECIMAL(10,6) NULL,
        usage_policy VARCHAR(32) NOT NULL DEFAULT 'reference',
        metadata_json JSON NULL,
        created_at DATETIME NOT NULL,
        INDEX idx_evidence_items_pack (evidence_pack_id),
        CONSTRAINT fk_evidence_items_pack FOREIGN KEY (evidence_pack_id) REFERENCES rag_evidence_packs(id),
        CONSTRAINT fk_evidence_items_file FOREIGN KEY (source_file_id) REFERENCES document_files(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS response_matrix_items (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        bid_document_id BIGINT UNSIGNED NULL,
        bid_chapter_id BIGINT UNSIGNED NULL,
        requirement_type VARCHAR(64) NOT NULL DEFAULT 'general',
        requirement_text TEXT NOT NULL,
        response_status VARCHAR(32) NOT NULL DEFAULT 'pending',
        evidence_text TEXT NULL,
        reviewer_note TEXT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_response_matrix_project (project_id, response_status),
        CONSTRAINT fk_response_matrix_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_response_matrix_doc FOREIGN KEY (bid_document_id) REFERENCES bid_documents(id),
        CONSTRAINT fk_response_matrix_chapter FOREIGN KEY (bid_chapter_id) REFERENCES bid_chapters(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS consistency_issues (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        bid_document_id BIGINT UNSIGNED NULL,
        bid_chapter_id BIGINT UNSIGNED NULL,
        issue_type VARCHAR(64) NOT NULL,
        severity VARCHAR(32) NOT NULL DEFAULT 'warning',
        issue_text TEXT NOT NULL,
        evidence_json JSON NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'open',
        created_by_agent_run_id BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_consistency_project (project_id, status),
        CONSTRAINT fk_consistency_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_consistency_doc FOREIGN KEY (bid_document_id) REFERENCES bid_documents(id),
        CONSTRAINT fk_consistency_chapter FOREIGN KEY (bid_chapter_id) REFERENCES bid_chapters(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS compliance_reports (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        bid_document_id BIGINT UNSIGNED NULL,
        report_type VARCHAR(64) NOT NULL DEFAULT 'full_review',
        summary TEXT NULL,
        report_json JSON NULL,
        risk_level VARCHAR(32) NOT NULL DEFAULT 'medium',
        created_by_agent_run_id BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_compliance_project (project_id, report_type),
        CONSTRAINT fk_compliance_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_compliance_doc FOREIGN KEY (bid_document_id) REFERENCES bid_documents(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS rewrite_tasks (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        bid_chapter_id BIGINT UNSIGNED NOT NULL,
        source_version_id BIGINT UNSIGNED NULL,
        target_version_id BIGINT UNSIGNED NULL,
        rewrite_scope VARCHAR(32) NOT NULL DEFAULT 'chapter',
        instruction TEXT NULL,
        patch_json JSON NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        created_by BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_rewrite_chapter (bid_chapter_id, status),
        INDEX idx_rewrite_project (project_id, created_at),
        CONSTRAINT fk_rewrite_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_rewrite_chapter FOREIGN KEY (bid_chapter_id) REFERENCES bid_chapters(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS research_tasks (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        task_type VARCHAR(64) NOT NULL DEFAULT 'deep_research',
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        query_json JSON NULL,
        strategy_json JSON NULL,
        error_message TEXT NULL,
        started_at DATETIME NULL,
        finished_at DATETIME NULL,
        created_by BIGINT UNSIGNED NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_research_task_project (project_id, status),
        CONSTRAINT fk_research_tasks_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_research_tasks_project FOREIGN KEY (project_id) REFERENCES bid_projects(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS research_reports (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        research_task_id BIGINT UNSIGNED NOT NULL,
        report_title VARCHAR(500) NOT NULL,
        report_json JSON NULL,
        summary LONGTEXT NULL,
        findings_json JSON NULL,
        risk_flags_json JSON NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_research_report_project (project_id),
        CONSTRAINT fk_research_reports_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_research_reports_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_research_reports_task FOREIGN KEY (research_task_id) REFERENCES research_tasks(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS research_sources (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        research_task_id BIGINT UNSIGNED NOT NULL,
        research_report_id BIGINT UNSIGNED NULL,
        source_type VARCHAR(64) NOT NULL,
        title VARCHAR(500) NOT NULL,
        source_url VARCHAR(700) NOT NULL,
        domain VARCHAR(255) NULL,
        publish_date DATE NULL,
        retrieved_at DATETIME NOT NULL,
        summary TEXT NULL,
        content_snapshot LONGTEXT NULL,
        credibility_score DECIMAL(5,4) NULL,
        reference_value TEXT NULL,
        is_confirmed TINYINT(1) NOT NULL DEFAULT 0,
        confirmed_by BIGINT UNSIGNED NULL,
        confirmed_at DATETIME NULL,
        file_id BIGINT UNSIGNED NULL,
        vector_status VARCHAR(32) NOT NULL DEFAULT 'pending',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE KEY uk_research_source_url (research_task_id, source_url),
        INDEX idx_research_source_project (project_id, source_type),
        CONSTRAINT fk_research_sources_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_research_sources_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_research_sources_task FOREIGN KEY (research_task_id) REFERENCES research_tasks(id),
        CONSTRAINT fk_research_sources_report FOREIGN KEY (research_report_id) REFERENCES research_reports(id),
        CONSTRAINT fk_research_sources_file FOREIGN KEY (file_id) REFERENCES document_files(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS project_terms (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        term VARCHAR(255) NOT NULL,
        aliases_json JSON NULL,
        forbidden_aliases_json JSON NULL,
        usage_note TEXT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_project_terms_project (project_id),
        CONSTRAINT fk_project_terms_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_project_terms_project FOREIGN KEY (project_id) REFERENCES bid_projects(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS confirmation_gates (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
        project_id BIGINT UNSIGNED NOT NULL,
        gate_type VARCHAR(64) NOT NULL,
        gate_status VARCHAR(32) NOT NULL DEFAULT 'pending',
        generation_task_id BIGINT UNSIGNED NULL,
        payload_json JSON NULL,
        confirmed_by BIGINT UNSIGNED NULL,
        confirmed_at DATETIME NULL,
        expires_at DATETIME NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        INDEX idx_confirmation_gates_project (project_id, gate_status),
        CONSTRAINT fk_confirmation_gates_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        CONSTRAINT fk_confirmation_gates_project FOREIGN KEY (project_id) REFERENCES bid_projects(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS bidding (
        id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT UNSIGNED NOT NULL,
        project_id BIGINT UNSIGNED NULL,
        file_id BIGINT UNSIGNED NULL,
        generated_file_id BIGINT UNSIGNED NULL,
        original_filename VARCHAR(500) NOT NULL,
        storage_path VARCHAR(1000) NOT NULL,
        document_key VARCHAR(128) UNIQUE NOT NULL,
        status VARCHAR(64) DEFAULT 'Uploaded',
        other_response_format LONGTEXT NULL,
        bid_document VARCHAR(1000) NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_bidding_user (user_id),
        CONSTRAINT fk_bidding_user FOREIGN KEY (user_id) REFERENCES users(id),
        CONSTRAINT fk_bidding_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
        CONSTRAINT fk_bidding_file FOREIGN KEY (file_id) REFERENCES document_files(id),
        CONSTRAINT fk_bidding_generated_file FOREIGN KEY (generated_file_id) REFERENCES document_files(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS model_settings (
        id TINYINT PRIMARY KEY,
        active_provider VARCHAR(64) NOT NULL,
        model VARCHAR(128) NOT NULL,
        api_key TEXT NULL,
        base_url VARCHAR(500) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "ALTER TABLE knowledge_documents ADD INDEX idx_kdoc_review (tenant_id, review_status)",
    "ALTER TABLE document_chunks ADD INDEX idx_chunk_kb (knowledge_base_id)",
    "ALTER TABLE document_chunks ADD INDEX idx_chunk_kdoc (knowledge_document_id)",
    "ALTER TABLE document_versions ADD COLUMN blob_id BIGINT UNSIGNED NULL",
    "ALTER TABLE bid_document_versions ADD COLUMN file_version_id BIGINT UNSIGNED NULL",
    "ALTER TABLE bid_document_versions ADD COLUMN blob_id BIGINT UNSIGNED NULL",
    "ALTER TABLE bid_chapter_versions ADD COLUMN generation_task_id BIGINT UNSIGNED NULL",
    "ALTER TABLE bid_chapter_versions ADD COLUMN agent_run_id BIGINT UNSIGNED NULL",
    "ALTER TABLE bid_chapter_versions ADD COLUMN word_count INT NULL",
    "ALTER TABLE bid_chapter_versions ADD COLUMN review_status VARCHAR(32) NOT NULL DEFAULT 'pending'",
    "ALTER TABLE bidding ADD COLUMN file_id BIGINT UNSIGNED NULL",
    "ALTER TABLE bidding ADD COLUMN generated_file_id BIGINT UNSIGNED NULL",
    "ALTER TABLE rewrite_tasks ADD COLUMN selected_text LONGTEXT NULL",
    "ALTER TABLE rewrite_tasks ADD COLUMN context_hash VARCHAR(64) NULL",
]
