/**
 * OpenDesk File Transfer Controller
 * Handles remote folder navigation, chunked downloads, and uploads.
 */

class FileTransferManager {
  constructor(sendCallback) {
    this.send = sendCallback;
    this.currentPath = "";
    this.parentPath = null;
    
    // Download state
    this.activeDownload = null; // { path, filename, chunks, totalSize, totalChunks }
    
    // Upload state
    this.activeUpload = null; // { file, uploadId, targetDir, totalChunks, chunkSize }
  }

  requestList(path) {
    this.send({
      type: "file_list_req",
      payload: { path: path || this.currentPath || "" }
    });
  }

  handleListResponse(payload) {
    this.currentPath = payload.path || "";
    this.parentPath = payload.parent || null;

    const pathInput = document.getElementById("currentPathInput");
    if (pathInput) pathInput.value = this.currentPath;

    const body = document.getElementById("fileListBody");
    if (!body) return;
    body.innerHTML = "";

    const entries = payload.entries || [];
    if (entries.length === 0) {
      body.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 20px;">Empty folder</td></tr>`;
      return;
    }

    for (const item of entries) {
      const tr = document.createElement("tr");
      const icon = item.is_dir ? "📁" : "📄";
      const sizeStr = item.is_dir ? "-" : this._formatSize(item.size);

      tr.innerHTML = `
        <td>
          <span class="file-item-name" data-name="${item.name}" data-isdir="${item.is_dir}">
            ${icon} ${item.name}
          </span>
        </td>
        <td style="font-family: var(--font-mono); color: var(--text-muted);">${sizeStr}</td>
        <td>
          ${item.is_dir 
            ? `<button class="btn btn-sm btn-secondary btn-open-dir" data-name="${item.name}">Open</button>` 
            : `<button class="btn btn-sm btn-secondary btn-download-file" data-name="${item.name}">Download</button>`
          }
        </td>
      `;
      body.appendChild(tr);
    }

    // Attach row click events
    body.querySelectorAll(".btn-open-dir, .file-item-name").forEach(elem => {
      elem.addEventListener("click", (e) => {
        const isDir = elem.dataset.isdir === "true" || elem.classList.contains("btn-open-dir");
        if (isDir) {
          const dirName = elem.dataset.name;
          const separator = this.currentPath.includes("\\") ? "\\" : "/";
          const newPath = this.currentPath.endsWith(separator) 
            ? this.currentPath + dirName 
            : this.currentPath + separator + dirName;
          this.requestList(newPath);
        }
      });
    });

    body.querySelectorAll(".btn-download-file").forEach(btn => {
      btn.addEventListener("click", () => {
        const fileName = btn.dataset.name;
        const separator = this.currentPath.includes("\\") ? "\\" : "/";
        const filePath = this.currentPath.endsWith(separator) 
          ? this.currentPath + fileName 
          : this.currentPath + separator + fileName;
        this.startDownload(filePath);
      });
    });
  }

  startDownload(filePath) {
    this._showProgress("Starting download...", 0);
    this.activeDownload = {
      path: filePath,
      chunks: [],
      received: 0
    };
    this.send({
      type: "file_download_req",
      payload: { path: filePath, chunk_index: 0 }
    });
  }

  handleFileChunk(payload) {
    // Check if this is an incoming download chunk
    if (this.activeDownload && payload.file_path === this.activeDownload.path) {
      const byteCharacters = atob(payload.data);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      this.activeDownload.chunks.push(new Uint8Array(byteNumbers));
      
      const pct = Math.round(((payload.chunk_index + 1) / payload.total_chunks) * 100);
      this._showProgress(`Downloading ${payload.filename} (${pct}%)...`, pct);

      if (payload.is_last) {
        // Assembled complete file
        const blob = new Blob(this.activeDownload.chunks);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = payload.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this._showProgress("Download complete!", 100);
        setTimeout(() => this._hideProgress(), 2000);
        this.activeDownload = null;
      } else {
        // Request next chunk
        this.send({
          type: "file_download_req",
          payload: { path: payload.file_path, chunk_index: payload.chunk_index + 1 }
        });
      }
    }

    // Check if this is an upload acknowledgment chunk
    if (this.activeUpload && payload.upload_id === this.activeUpload.uploadId) {
      if (payload.status === "complete") {
        this._showProgress("Upload complete!", 100);
        setTimeout(() => {
          this._hideProgress();
          this.requestList(this.currentPath);
        }, 1500);
        this.activeUpload = null;
      } else {
        const nextIdx = payload.received_chunks;
        this._uploadNextChunk(nextIdx);
      }
    }
  }

  startUpload(file) {
    if (!file) return;
    const chunkSize = 64 * 1024;
    const totalChunks = Math.ceil(file.size / chunkSize);
    const uploadId = "up_" + Math.random().toString(36).substring(2, 9);

    this.activeUpload = {
      file,
      uploadId,
      targetDir: this.currentPath,
      totalChunks,
      chunkSize
    };

    this._showProgress(`Preparing upload for ${file.name}...`, 0);
    this.send({
      type: "file_upload_start",
      payload: {
        upload_id: uploadId,
        target_dir: this.currentPath,
        filename: file.name,
        total_chunks: totalChunks,
        file_size: file.size
      }
    });

    // Send first chunk
    this._uploadNextChunk(0);
  }

  _uploadNextChunk(chunkIndex) {
    if (!this.activeUpload || chunkIndex >= this.activeUpload.totalChunks) return;
    const { file, uploadId, chunkSize, totalChunks } = this.activeUpload;
    
    const start = chunkIndex * chunkSize;
    const end = Math.min(file.size, start + chunkSize);
    const slice = file.slice(start, end);

    const reader = new FileReader();
    reader.onload = () => {
      const b64 = btoa(
        new Uint8Array(reader.result).reduce((data, byte) => data + String.fromCharCode(byte), "")
      );
      
      const pct = Math.round(((chunkIndex + 1) / totalChunks) * 100);
      this._showProgress(`Uploading ${file.name} (${pct}%)...`, pct);

      this.send({
        type: "file_chunk",
        payload: {
          upload_id: uploadId,
          chunk_index: chunkIndex,
          data: b64
        }
      });
    };
    reader.readAsArrayBuffer(slice);
  }

  _showProgress(text, pct) {
    const cont = document.getElementById("transferProgressContainer");
    const lbl = document.getElementById("progressLabel");
    const fill = document.getElementById("progressBarFill");
    if (cont) cont.style.display = "block";
    if (lbl) lbl.textContent = text;
    if (fill) fill.style.width = pct + "%";
  }

  _hideProgress() {
    const cont = document.getElementById("transferProgressContainer");
    if (cont) cont.style.display = "none";
  }

  _formatSize(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }
}
