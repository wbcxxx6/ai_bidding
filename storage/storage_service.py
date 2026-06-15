import hashlib
import logging
import mimetypes
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pymysql

from core.db import get_db


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}
MYSQL_PACKET_ERROR_CODES = {1153, 2006, 2013}


class StorageError(Exception):
    pass


class FileTypeNotAllowed(StorageError):
    pass


class BlobTooLarge(StorageError):
    pass


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def normalize_ext(filename):
    return Path(filename or "").suffix.lower()


def validate_filename(filename):
    ext = normalize_ext(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise FileTypeNotAllowed("Unsupported file type. Allowed: pdf, doc, docx, txt, md.")
    return ext


def decode_text(content_bytes):
    for encoding in ["utf-8", "utf-8-sig", "gb18030", "gbk", "latin-1"]:
        try:
            return content_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, None


def mysql_packet_message():
    return (
        "File content is too large for current MySQL max_allowed_packet. "
        "Increase MySQL max_allowed_packet or upload a smaller file."
    )


def translate_mysql_error(exc):
    if isinstance(exc, (pymysql.err.OperationalError, pymysql.err.InternalError)) and exc.args:
        if exc.args[0] in MYSQL_PACKET_ERROR_CODES:
            raise BlobTooLarge(mysql_packet_message()) from exc
    raise exc


@dataclass
class StoredFile:
    file_id: int
    version_id: int
    blob_id: int
    storage_key: str
    file_size: int
    sha256_hash: str
    mime_type: str | None


class MySQLBlobStorage:
    bucket = "mysql"

    def create_file(
        self,
        *,
        content_bytes,
        original_filename,
        file_category,
        owner_user_id=None,
        tenant_id=1,
        company_id=1,
        project_id=None,
        content_text=None,
        content_encoding=None,
        parse_status="pending",
        vector_status="pending",
        change_source="upload",
        allow_generated_ext=False,
    ):
        ext = normalize_ext(original_filename)
        if not allow_generated_ext:
            validate_filename(original_filename)
        mime_type = mimetypes.guess_type(original_filename)[0]
        sha256_hash = hashlib.sha256(content_bytes).hexdigest()
        file_size = len(content_bytes)
        if content_text is None and ext in {".txt", ".md"}:
            content_text, content_encoding = decode_text(content_bytes)

        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO document_files
                (tenant_id, company_id, project_id, owner_user_id, file_category, original_filename,
                 storage_bucket, storage_key, file_ext, mime_type, file_size, sha256_hash,
                 parse_status, vector_status, confidentiality_level, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'mysql', '', ?, ?, ?, ?, ?, ?, 'internal', ?, ?)
                """,
                (
                    tenant_id,
                    company_id,
                    project_id,
                    owner_user_id,
                    file_category,
                    original_filename,
                    ext,
                    mime_type,
                    file_size,
                    sha256_hash,
                    parse_status,
                    vector_status,
                    now(),
                    now(),
                ),
            )
            file_id = cursor.lastrowid
            storage_key = self.storage_key(file_id, 1)
            cursor.execute("UPDATE document_files SET storage_key=? WHERE id=?", (storage_key, file_id))
            version_id, blob_id = self._insert_version_and_blob(
                cursor,
                file_id=file_id,
                tenant_id=tenant_id,
                version_no=1,
                storage_key=storage_key,
                content_bytes=content_bytes,
                file_size=file_size,
                sha256_hash=sha256_hash,
                change_source=change_source,
                created_by=owner_user_id,
                content_text=content_text,
                content_encoding=content_encoding,
            )
            conn.commit()
            return StoredFile(file_id, version_id, blob_id, storage_key, file_size, sha256_hash, mime_type)
        except Exception as exc:
            conn.rollback()
            translate_mysql_error(exc)
        finally:
            conn.close()

    def add_version(
        self,
        *,
        file_id,
        content_bytes,
        change_source,
        created_by=None,
        content_text=None,
        content_encoding=None,
    ):
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM document_files WHERE id=?", (file_id,))
            file_row = cursor.fetchone()
            if not file_row:
                raise StorageError("File not found.")
            cursor.execute("SELECT COALESCE(MAX(version_no), 0) AS max_version FROM document_versions WHERE file_id=?", (file_id,))
            latest = cursor.fetchone()
            version_no = int(latest["max_version"]) + 1
            sha256_hash = hashlib.sha256(content_bytes).hexdigest()
            file_size = len(content_bytes)
            storage_key = self.storage_key(file_id, version_no)
            version_id, blob_id = self._insert_version_and_blob(
                cursor,
                file_id=file_id,
                tenant_id=file_row["tenant_id"],
                version_no=version_no,
                storage_key=storage_key,
                content_bytes=content_bytes,
                file_size=file_size,
                sha256_hash=sha256_hash,
                change_source=change_source,
                created_by=created_by,
                content_text=content_text,
                content_encoding=content_encoding,
            )
            cursor.execute(
                """
                UPDATE document_files
                SET storage_bucket='mysql', storage_key=?, file_size=?, sha256_hash=?, updated_at=?
                WHERE id=?
                """,
                (storage_key, file_size, sha256_hash, now(), file_id),
            )
            conn.commit()
            return {
                "file_id": file_id,
                "version_no": version_no,
                "version_id": version_id,
                "blob_id": blob_id,
                "storage_key": storage_key,
            }
        except Exception as exc:
            conn.rollback()
            translate_mysql_error(exc)
        finally:
            conn.close()

    def _insert_version_and_blob(
        self,
        cursor,
        *,
        file_id,
        tenant_id,
        version_no,
        storage_key,
        content_bytes,
        file_size,
        sha256_hash,
        change_source,
        created_by,
        content_text,
        content_encoding,
    ):
        cursor.execute(
            """
            INSERT INTO document_versions
            (file_id, tenant_id, version_no, storage_bucket, storage_key, file_size,
             sha256_hash, change_source, created_by, created_at)
            VALUES (?, ?, ?, 'mysql', ?, ?, ?, ?, ?, ?)
            """,
            (file_id, tenant_id, version_no, storage_key, file_size, sha256_hash, change_source, created_by, now()),
        )
        version_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO document_file_blobs
            (file_id, version_id, content, content_text, content_encoding, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_id, version_id, content_bytes, content_text, content_encoding, now()),
        )
        blob_id = cursor.lastrowid
        cursor.execute("UPDATE document_versions SET blob_id=? WHERE id=?", (blob_id, version_id))
        return version_id, blob_id

    def get_latest(self, file_id):
        return self.get_version(file_id=file_id, version_no=None)

    def get_version(self, *, file_id, version_no=None):
        params = [file_id]
        version_filter = ""
        if version_no is not None:
            version_filter = "AND v.version_no = ?"
            params.append(version_no)
        row = None
        conn = get_db()
        try:
            row = conn.execute(
                f"""
                SELECT f.*, v.id AS version_id, v.version_no, b.id AS blob_id,
                       b.content, b.content_text, b.content_encoding
                FROM document_files f
                JOIN document_versions v ON v.file_id = f.id
                JOIN document_file_blobs b ON b.version_id = v.id
                WHERE f.id = ? {version_filter}
                ORDER BY v.version_no DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise StorageError("File blob not found.")
        return row

    def find_latest_by_filename(self, filename):
        conn = get_db()
        try:
            row = conn.execute(
                """
                SELECT id FROM document_files
                WHERE original_filename = ? AND storage_bucket = 'mysql'
                ORDER BY id DESC
                LIMIT 1
                """,
                (filename,),
            ).fetchone()
        finally:
            conn.close()
        return self.get_latest(row["id"]) if row else None

    @staticmethod
    def storage_key(file_id, version_no):
        return f"mysql://document_files/{file_id}/versions/{version_no}"


class LocalStorage(MySQLBlobStorage):
    bucket = "local"

    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir or os.getenv("LOCAL_STORAGE_DIR", ".runtime/local_storage")).resolve()

    def create_file(self, **kwargs):
        stored = super().create_file(**kwargs)
        content_bytes = kwargs["content_bytes"]
        local_path = self._local_path(stored.file_id, 1, kwargs["original_filename"])
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content_bytes)
        self._mark_local(stored.file_id, stored.version_id, str(local_path))
        return stored

    def add_version(self, **kwargs):
        version = super().add_version(**kwargs)
        file_row = self.get_latest(kwargs["file_id"])
        local_path = self._local_path(kwargs["file_id"], version["version_no"], file_row["original_filename"])
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(kwargs["content_bytes"])
        self._mark_local(kwargs["file_id"], version["version_id"], str(local_path))
        version["storage_key"] = f"local://{local_path}"
        return version

    def get_version(self, *, file_id, version_no=None):
        row = super().get_version(file_id=file_id, version_no=version_no)
        storage_key = row.get("storage_key") or ""
        if storage_key.startswith("local://"):
            local_path = Path(storage_key.removeprefix("local://"))
            if local_path.exists():
                row["content"] = local_path.read_bytes()
        return row

    def _mark_local(self, file_id, version_id, local_path):
        storage_key = f"local://{local_path}"
        conn = get_db()
        try:
            conn.execute(
                "UPDATE document_files SET storage_bucket='local', storage_key=?, updated_at=? WHERE id=?",
                (storage_key, now(), file_id),
            )
            conn.execute(
                "UPDATE document_versions SET storage_bucket='local', storage_key=? WHERE id=?",
                (storage_key, version_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _local_path(self, file_id, version_no, filename):
        safe_name = Path(filename or "file").name
        return self.base_dir / str(file_id) / f"v{version_no}_{safe_name}"


class ObjectStoragePlaceholder(MySQLBlobStorage):
    def create_file(self, **kwargs):
        raise StorageError("Object storage backend is not configured yet.")

    def add_version(self, **kwargs):
        raise StorageError("Object storage backend is not configured yet.")


class StorageRouter:
    def __init__(self):
        self.backends = {
            "mysql_blob": MySQLBlobStorage(),
            "mysql": MySQLBlobStorage(),
            "local": LocalStorage(),
            "minio": ObjectStoragePlaceholder(),
            "oss": ObjectStoragePlaceholder(),
        }
        self.logger = logging.getLogger(__name__)

    def active_backend_name(self):
        return os.getenv("STORAGE_BACKEND", "mysql_blob").lower()

    def active_backend(self):
        backend_name = self.active_backend_name()
        backend = self.backends.get(backend_name)
        if backend:
            return backend_name, backend
        self.logger.warning("unknown storage backend=%s; fallback_used=true fallback_backend=mysql_blob", backend_name)
        return "mysql_blob", self.backends["mysql_blob"]

    def create_file(self, **kwargs):
        backend_name, backend = self.active_backend()
        try:
            stored = backend.create_file(**kwargs)
            self.logger.info("storage create_file backend=%s file_id=%s fallback_used=false", backend_name, stored.file_id)
            return stored
        except Exception:
            if backend_name == "mysql_blob":
                raise
            self.logger.exception("storage create_file failed backend=%s fallback_used=true fallback_backend=mysql_blob", backend_name)
            return self.backends["mysql_blob"].create_file(**kwargs)

    def add_version(self, **kwargs):
        backend_name, backend = self.active_backend()
        try:
            version = backend.add_version(**kwargs)
            self.logger.info("storage add_version backend=%s file_id=%s fallback_used=false", backend_name, kwargs.get("file_id"))
            return version
        except Exception:
            if backend_name == "mysql_blob":
                raise
            self.logger.exception("storage add_version failed backend=%s fallback_used=true fallback_backend=mysql_blob", backend_name)
            return self.backends["mysql_blob"].add_version(**kwargs)

    def get_latest(self, file_id):
        return self.get_version(file_id=file_id, version_no=None)

    def get_version(self, *, file_id, version_no=None):
        row = self.backends["mysql_blob"].get_version(file_id=file_id, version_no=version_no)
        bucket = (row.get("storage_bucket") or "mysql").lower()
        if bucket == "local":
            try:
                return self.backends["local"].get_version(file_id=file_id, version_no=version_no)
            except Exception:
                self.logger.exception("local read failed file_id=%s degraded_reason=local_missing fallback_used=true", file_id)
        return row

    def find_latest_by_filename(self, filename):
        return self.backends["mysql_blob"].find_latest_by_filename(filename)

    @staticmethod
    def storage_key(file_id, version_no):
        return MySQLBlobStorage.storage_key(file_id, version_no)


storage_service = StorageRouter()
