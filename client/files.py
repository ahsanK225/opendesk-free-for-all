"""Native, streamed file transfers. All widget calls run on the Tk thread."""
import base64
import hashlib
import ntpath
import os
import secrets
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

CHUNK_SIZE = 65536


class FileDialog:
    def __init__(self, viewer):
        self.viewer = viewer
        self.path, self.parent, self.transfer = '', None, None
        self.win = tk.Toplevel(viewer)
        self.win.title('Remote files — shared home folder')
        self.win.geometry('720x480')
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        bar = ttk.Frame(self.win)
        bar.pack(fill='x', padx=8, pady=8)
        ttk.Button(bar, text='Up', command=lambda:self.list(self.parent) if self.parent else None).pack(side='left')
        ttk.Button(bar, text='Refresh', command=lambda:self.list(self.path)).pack(side='left')
        ttk.Button(bar, text='Upload', command=self.upload).pack(side='left')
        ttk.Button(bar, text='Download selected', command=self.download).pack(side='left')
        self.location = tk.StringVar()
        ttk.Label(self.win, textvariable=self.location).pack(fill='x', padx=8)
        self.tree = ttk.Treeview(self.win, columns=('size',), selectmode='browse')
        self.tree.heading('#0', text='Name')
        self.tree.heading('size', text='Bytes')
        self.tree.pack(fill='both', expand=True, padx=8, pady=8)
        self.tree.bind('<Double-1>', self.open_selected)
        self.status = tk.StringVar(value='Loading…')
        ttk.Label(self.win, textvariable=self.status).pack(fill='x', padx=8, pady=8)
        self.entries = {}
        self.list('')

    def send(self, typ, **payload):
        if self.viewer.in_session and self.viewer.granted_permissions.get('file_transfer'):
            self.viewer._send_payload(typ, payload)

    def list(self, path):
        self.send('file_list_req', path=path or '')

    def selected(self):
        selection = self.tree.selection()
        return self.entries.get(selection[0]) if selection else None

    def remote_path(self, name):
        return ntpath.join(self.path, name) if '\\' in self.path else self.path.rstrip('/')+'/'+name

    def open_selected(self, event=None):
        item = self.selected()
        if item and item['is_dir']:
            self.list(self.remote_path(item['name']))

    def download(self):
        item = self.selected()
        if self.transfer or not item or item['is_dir']:
            return
        target = filedialog.asksaveasfilename(parent=self.win, initialfile=item['name'])
        if not target:
            return
        temporary = target+'.opendesk-'+secrets.token_hex(6)+'.part'
        self.transfer = {'direction':'down', 'path':self.remote_path(item['name']), 'target':target,
                         'temp':temporary, 'stream':open(temporary,'xb'), 'index':0, 'size':0}
        self.send('file_download_req', path=self.transfer['path'], chunk_index=0)

    def upload(self):
        if self.transfer:
            return
        source = filedialog.askopenfilename(parent=self.win)
        if not source:
            return
        self.status.set('Hashing file…')
        def prepare():
            try:
                hasher = hashlib.sha256()
                with open(source,'rb') as stream:
                    for block in iter(lambda:stream.read(CHUNK_SIZE), b''): hasher.update(block)
                self.viewer.post_ui(self._begin_upload, source, hasher.hexdigest())
            except OSError as exc:
                self.viewer.post_ui(self.fail, str(exc))
        threading.Thread(target=prepare,daemon=True).start()

    def _begin_upload(self, source, digest):
        if not self.win.winfo_exists() or self.transfer:
            return
        size = os.path.getsize(source)
        upload_id = secrets.token_hex(16)
        self.transfer = {'direction':'up','id':upload_id,'stream':open(source,'rb'),
                         'index':0,'size':size,'digest':digest}
        self.send('file_upload_start', upload_id=upload_id, target_dir=self.path,
                  filename=os.path.basename(source), total_chunks=max(1,(size+CHUNK_SIZE-1)//CHUNK_SIZE),
                  file_size=size, sha256=digest)

    def _next_upload(self):
        transfer = self.transfer
        block = transfer['stream'].read(CHUNK_SIZE)
        self.send('file_chunk', upload_id=transfer['id'], chunk_index=transfer['index'],
                  data=base64.b64encode(block).decode())
        transfer['index'] += 1
        self.status.set(f"Uploading: {min(transfer['index']*CHUNK_SIZE,transfer['size']):,} / {transfer['size']:,} bytes")

    def receive(self, typ, payload):
        if not self.win.winfo_exists(): return
        if payload.get('error') or typ == 'file_error':
            self.fail(payload.get('error') or payload.get('message','Transfer failed'))
            return
        if typ == 'file_list_resp':
            self.path, self.parent = payload['path'], payload.get('parent')
            self.location.set(self.path)
            self.tree.delete(*self.tree.get_children())
            self.entries.clear()
            for index,item in enumerate(payload.get('entries',[])):
                iid = str(index)
                self.entries[iid] = item
                self.tree.insert('', 'end', iid=iid, text=('📁 ' if item['is_dir'] else '')+item['name'],
                                 values=('' if item['is_dir'] else f"{item['size']:,}",))
            self.status.set('Ready')
            return
        transfer = self.transfer
        if not transfer: return
        try:
            if transfer['direction']=='up' and payload.get('upload_id')==transfer['id']:
                if payload.get('status')=='complete':
                    if payload.get('sha256') != transfer['digest']: raise ValueError('Upload digest mismatch')
                    self.finish()
                elif typ=='file_upload_start' or payload.get('received_chunks')==transfer['index']:
                    self._next_upload()
            elif transfer['direction']=='down' and typ=='file_chunk':
                if payload.get('file_path') != transfer['path'] or payload['chunk_index'] != transfer['index']:
                    raise ValueError('Unexpected file response')
                block = base64.b64decode(payload['data'], validate=True)
                transfer['stream'].write(block)
                transfer['size'] += len(block)
                transfer['index'] += 1
                self.status.set(f"Downloaded {transfer['size']:,} / {payload['file_size']:,} bytes")
                if payload['is_last']:
                    if transfer['size'] != payload['file_size']: raise ValueError('Download size mismatch')
                    transfer['stream'].close()
                    os.replace(transfer['temp'], transfer['target'])
                    self.finish()
                else:
                    self.send('file_download_req', path=transfer['path'], chunk_index=transfer['index'])
        except (OSError,ValueError,KeyError) as exc:
            self.fail(str(exc))

    def finish(self):
        if self.transfer: self.transfer['stream'].close()
        self.transfer = None
        self.status.set('Transfer complete')
        self.list(self.path)

    def fail(self, message):
        self.cancel()
        self.status.set(message)

    def cancel(self):
        if self.transfer:
            self.transfer['stream'].close()
            temporary = self.transfer.get('temp')
            if temporary and os.path.exists(temporary): os.unlink(temporary)
        self.transfer = None

    def close(self):
        self.cancel()
        self.win.destroy()
