"""A stand-in strata-models service on 127.0.0.1 for tests that go through the real client over real HTTP: the three endpoints the client
uses for a job (health, submit, wait) and the registry. Its `ocr` role is the real `tesseract` (books.tesseract_ocr), so the text is
real; only the queue, the GPU and the database of the real service are left out. Any other role fails the job, as the service does."""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from books import tesseract_ocr


class _Handler(BaseHTTPRequestHandler):
    server: "ModelsService"

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/health":
            return self._send(200, {"ok": True})
        if path == "/api/registry":
            return self._send(200, {"roles": [{"key": "ocr", "model": "tesseract-eng"}]})
        m = re.fullmatch(r"/api/jobs/(\d+)", path)
        if m and int(m.group(1)) in self.server.jobs:
            return self._send(200, self.server.jobs[int(m.group(1))])
        return self._send(404, {"detail": f"no {path}"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        with self.server.lock:
            self.server.count += 1
            job_id = self.server.count
        self.server.submitted.append(body)
        p = body.get("params", {})
        try:
            if body.get("role") != "ocr":
                raise ValueError(f"no role {body.get('role')!r}")
            result = tesseract_ocr(p["path"], p["pdf"], p.get("lang", "eng"), p.get("dpi", 300))
            self.server.jobs[job_id] = {"id": job_id, "status": "done", "result": result}
        except Exception as e:
            self.server.jobs[job_id] = {"id": job_id, "status": "failed", "error": str(e)}
        return self._send(200, {"id": job_id, "status": "queued"})


class ModelsService(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.jobs, self.submitted, self.count, self.lock = {}, [], 0, threading.Lock()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"
