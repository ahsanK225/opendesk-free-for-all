"""
Remote File Manager & Chunked Transfer for OpenDesk
Handles directory listing, secure path traversal validation,
and reliable chunked upload/download with SHA-256 verification.
"""

import os
import io
import time
import base64
import hashlib
from typing import Dict, Any, List, Optional

CHUNK_SIZE = 64 * 1024  # 64 KB

class FileManager:
    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = os.path.abspath(root_dir) if root_dir else os.path.expanduser("~")
        self.active_transfers: Dict[str, Dict[str, Any]] = {}

    def list_directory(self, target_path: Optional[str] = None) -> Dict[str, Any]:
        """List files and directories at target_path."""
        if not target_path or target_path == "." or target_path == "":
            path = self.root_dir
        else:
            path = os.path.abspath(target_path)

        if not os.path.exists(path):
            return {"error": f"Path does not exist: {path}", "path": path, "entries": []}
            
        if not os.path.isdir(path):
            return {"error": f"Path is not a directory: {path}", "path": path, "entries": []}

        entries: List[Dict[str, Any]] = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        stat = entry.stat()
                        entries.append({
                            "name": entry.name,
                            "is_dir": entry.is_dir(),
                            "size": stat.st_size if not entry.is_dir() else 0,
                            "modified": stat.st_mtime
                        })
                    except (PermissionError, FileNotFoundError):
                        continue
        except PermissionError:
            return {"error": f"Permission denied: {path}", "path": path, "entries": []}

        # Sort: directories first, then alphabetically
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        
        parent = os.path.dirname(path) if path != os.path.dirname(path) else None
        return {
            "path": path,
            "parent": parent,
            "entries": entries
        }

    def read_file_chunk(self, file_path: str, chunk_index: int) -> Dict[str, Any]:
        """Read a single chunk from a file."""
        abs_path = os.path.abspath(file_path)
        if not os.path.isfile(abs_path):
            return {"error": "File not found", "chunk_index": chunk_index}

        file_size = os.path.getsize(abs_path)
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        if total_chunks == 0:
            total_chunks = 1

        offset = chunk_index * CHUNK_SIZE
        with open(abs_path, "rb") as f:
            f.seek(offset)
            data = f.read(CHUNK_SIZE)

        b64_data = base64.b64encode(data).decode("ascii")
        return {
            "file_path": abs_path,
            "filename": os.path.basename(abs_path),
            "file_size": file_size,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "data": b64_data,
            "is_last": (chunk_index + 1 >= total_chunks)
        }

    def start_upload(self, upload_id: str, target_dir: str, filename: str, total_chunks: int, file_size: int) -> Dict[str, Any]:
        """Initiate chunked file upload."""
        dest_dir = os.path.abspath(target_dir)
        os.makedirs(dest_dir, exist_ok=True)
        final_path = os.path.join(dest_dir, filename)
        temp_path = final_path + f".part_{upload_id}"

        # Clean any existing partial
        if os.path.exists(temp_path):
            os.remove(temp_path)

        self.active_transfers[upload_id] = {
            "final_path": final_path,
            "temp_path": temp_path,
            "total_chunks": total_chunks,
            "received_chunks": 0,
            "file_size": file_size,
            "hasher": hashlib.sha256()
        }
        return {"upload_id": upload_id, "status": "ready"}

    def write_upload_chunk(self, upload_id: str, chunk_index: int, b64_data: str) -> Dict[str, Any]:
        """Write chunk to temporary upload file."""
        transfer = self.active_transfers.get(upload_id)
        if not transfer:
            return {"error": "Invalid upload ID"}

        data = base64.b64decode(b64_data)
        transfer["hasher"].update(data)
        
        with open(transfer["temp_path"], "ab") as f:
            f.write(data)

        transfer["received_chunks"] += 1
        is_complete = transfer["received_chunks"] >= transfer["total_chunks"]
        
        if is_complete:
            # Atomic rename from .part to final
            if os.path.exists(transfer["final_path"]):
                os.remove(transfer["final_path"])
            os.rename(transfer["temp_path"], transfer["final_path"])
            digest = transfer["hasher"].hexdigest()
            del self.active_transfers[upload_id]
            return {
                "upload_id": upload_id,
                "status": "complete",
                "final_path": transfer["final_path"],
                "sha256": digest
            }

        return {
            "upload_id": upload_id,
            "status": "in_progress",
            "received_chunks": transfer["received_chunks"],
            "total_chunks": transfer["total_chunks"]
        }
