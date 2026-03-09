#!/usr/bin/env python3
"""
SLURM Dashboard - Proxy Server
slurmrestd API에 JWT 인증을 자동으로 붙여서 브라우저에 전달하는 프록시.
로컬 TensorBoard 이벤트 파일에서 실험 데이터를 직접 읽어 시각화.
"""

import http.server
import json
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import os
import time

PORT = 3080
SLURMRESTD_URL = os.environ.get("SLURMRESTD_URL", "http://localhost:6820")
TENSORBOARD_URL = os.environ.get("TENSORBOARD_URL", "http://localhost:6006")
SLURM_API_VERSION = os.environ.get("SLURM_API_VERSION", "v0.0.44")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

# JWT token cache
_jwt_cache = {"token": None, "expires": 0}


def get_jwt_token():
    """Get JWT token from slurmctld container, with caching."""
    now = time.time()
    if _jwt_cache["token"] and _jwt_cache["expires"] > now:
        return _jwt_cache["token"]
    try:
        result = subprocess.run(
            ["docker", "exec", "slurmctld", "scontrol", "token"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "SLURM_JWT=" in line:
                token = line.split("=", 1)[1].strip()
                _jwt_cache["token"] = token
                _jwt_cache["expires"] = now + 1500
                return token
    except Exception as e:
        print(f"Error getting JWT: {e}")
    return None


def docker_exec(cmd_str, timeout=15):
    """Execute a command inside slurmctld container and return stdout."""
    result = subprocess.run(
        ["docker", "exec", "slurmctld", "bash", "-c", cmd_str],
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout, result.stderr


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith("/tb/"):
            self.proxy_tensorboard()
        elif self.path.startswith("/data/plugin/"):
            # TensorBoard API calls (used by embedded TB frontend)
            self.proxy_tensorboard()
        elif self.path.startswith("/api/runs"):
            self.handle_training_runs()
        elif self.path.startswith("/api/run-history"):
            self.handle_run_history()
        elif self.path.startswith("/api/run-log"):
            self.handle_run_log()
        elif self.path.startswith("/api/tb-status"):
            self.handle_tb_status()
        elif self.path.startswith("/api/"):
            self.proxy_api()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/submit":
            self.handle_submit()
        elif self.path == "/api/cancel":
            self.handle_cancel()
        elif self.path.startswith("/api/"):
            self.proxy_api(method="POST")
        else:
            self.send_error_json(404, "Not found")

    def handle_submit(self):
        """Submit a job via docker exec sbatch."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error_json(400, "Invalid JSON")
            return

        job_name = data.get("job_name", "web_job")
        partition = data.get("partition", "")
        nodes = data.get("nodes", "1")
        gpus = data.get("gpus", "")
        cpus = data.get("cpus", "")
        mem = data.get("mem", "")
        time_limit = data.get("time_limit", "")
        command = data.get("command", "hostname")

        cmd = ["docker", "exec", "slurmctld", "bash", "-c"]
        sbatch = f"cd /data && sbatch --job-name={job_name}"
        if partition:
            sbatch += f" --partition={partition}"
        if nodes and nodes != "1":
            sbatch += f" -N {nodes}"
        if gpus:
            sbatch += f" --gres=gpu:{gpus}"
        if cpus:
            sbatch += f" --cpus-per-task={cpus}"
        if mem:
            sbatch += f" --mem={mem}"
        if time_limit:
            sbatch += f" --time={time_limit}"
        sbatch += f" --wrap='{command}'"
        cmd.append(sbatch)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout.strip() + result.stderr.strip()
            self.send_json({"result": output})
        except Exception as e:
            self.send_error_json(500, f"Submit error: {str(e)}")

    def handle_cancel(self):
        """Cancel a job via docker exec scancel."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error_json(400, "Invalid JSON")
            return
        job_id = data.get("job_id", "")
        if not job_id:
            self.send_error_json(400, "job_id required")
            return
        try:
            result = subprocess.run(
                ["docker", "exec", "slurmctld", "scancel", str(job_id)],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip() + result.stderr.strip()
            self.send_json({"result": output or f"Job {job_id} cancelled"})
        except Exception as e:
            self.send_error_json(500, f"Cancel error: {str(e)}")

    def proxy_api(self, method="GET"):
        """Proxy /api/* requests to slurmrestd with JWT auth."""
        token = get_jwt_token()
        if not token:
            self.send_error_json(500, "Failed to get JWT token")
            return
        api_path = self.path[4:]
        path_part = api_path.split("?")[0]
        query = ""
        if "?" in api_path:
            query = "?" + api_path.split("?", 1)[1]
        url = f"{SLURMRESTD_URL}/slurm/{SLURM_API_VERSION}{path_part}{query}"
        headers = {
            "X-SLURM-USER-TOKEN": token,
            "X-SLURM-USER-NAME": "root",
            "Accept": "application/json",
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self.send_error_json(e.code, f"slurmrestd error: {body[:200]}")
        except Exception as e:
            self.send_error_json(502, f"Proxy error: {str(e)}")

    # ==================== TensorBoard Proxy ====================

    def proxy_tensorboard(self, method="GET", body=None):
        """Proxy requests to TensorBoard server."""
        # Strip /tb/ prefix if present, otherwise pass as-is
        if self.path.startswith("/tb/"):
            tb_path = self.path[3:]  # /tb/foo -> /foo
        else:
            tb_path = self.path  # /data/plugin/... -> /data/plugin/...

        url = f"{TENSORBOARD_URL}{tb_path}"
        try:
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header("Accept", self.headers.get("Accept", "*/*"))
            if self.headers.get("Content-Type"):
                req.add_header("Content-Type", self.headers["Content-Type"])

            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                self.send_response(resp.status)
                # Forward content type
                ct = resp.headers.get("Content-Type", "application/octet-stream")
                self.send_header("Content-Type", ct)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")
            self.send_error_json(e.code, f"TensorBoard error: {body_err[:200]}")
        except Exception as e:
            self.send_error_json(502, f"TensorBoard proxy error: {str(e)}")

    def handle_tb_status(self):
        """GET /api/tb-status - check if TensorBoard is running."""
        try:
            req = urllib.request.Request(f"{TENSORBOARD_URL}/", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.send_json({"status": "running", "url": TENSORBOARD_URL})
        except Exception:
            self.send_json({"status": "stopped", "url": TENSORBOARD_URL})

    # ==================== TensorBoard-based Training Runs ====================

    def handle_training_runs(self):
        """GET /api/runs - scan /data for TensorBoard event files."""
        try:
            # Find all TensorBoard event files
            stdout, _ = docker_exec(
                "find /data -name 'events.out.tfevents.*' -type f 2>/dev/null | sort -r | head -100",
                timeout=30
            )
            runs = []
            seen_dirs = set()

            for event_path in stdout.strip().splitlines():
                if not event_path:
                    continue
                tb_dir = os.path.dirname(event_path)
                if tb_dir in seen_dirs:
                    continue
                seen_dirs.add(tb_dir)

                # Determine the training run root directory
                # Common patterns:
                #   /data/.../output/training_log/.../tb/events.out.tfevents.*
                #   /data/.../logs/events.out.tfevents.*
                #   /data/.../tensorboard/events.out.tfevents.*
                train_dir = tb_dir
                dir_name = os.path.basename(tb_dir)
                if dir_name in ("tb", "tensorboard", "logs", "tfevent"):
                    train_dir = os.path.dirname(tb_dir)

                # Extract run name from directory structure
                run_name = os.path.basename(train_dir)
                project_name = os.path.basename(os.path.dirname(train_dir))
                if project_name in ("training_log", "output", "logs"):
                    project_name = os.path.basename(os.path.dirname(os.path.dirname(train_dir)))

                # Get event file info for timing
                stat_out, _ = docker_exec(f"stat -c '%Y' '{event_path}' 2>/dev/null")
                mtime = int(stat_out.strip()) if stat_out.strip().isdigit() else 0
                started_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mtime)) if mtime else ""

                # Check if still being written (running vs finished)
                age_out, _ = docker_exec(
                    f"echo $(( $(date +%s) - $(stat -c '%Y' '{event_path}') ))"
                )
                try:
                    age_seconds = int(age_out.strip())
                    state = "running" if age_seconds < 300 else "finished"
                except (ValueError, TypeError):
                    state = "finished"

                # Read scalar tags summary (quick peek at what metrics exist)
                tags_out, _ = docker_exec(
                    f"""python3 -c "
import json
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
ea = EventAccumulator('{tb_dir}', size_guidance={{'scalars': 1}})
ea.Reload()
tags = ea.Tags().get('scalars', [])
# Get last value for each tag
summary = {{}}
for tag in tags:
    events = ea.Scalars(tag)
    if events:
        summary[tag] = round(events[-1].value, 6)
print(json.dumps({{'tags': tags, 'summary': summary}}))
" 2>/dev/null""",
                    timeout=10
                )
                try:
                    tags_data = json.loads(tags_out.strip())
                    tags = tags_data.get("tags", [])
                    summary = tags_data.get("summary", {})
                except (json.JSONDecodeError, ValueError):
                    tags = []
                    summary = {}

                runs.append({
                    "id": run_name,
                    "tb_dir": tb_dir,
                    "train_dir": train_dir,
                    "project": project_name,
                    "display_name": run_name,
                    "state": state,
                    "started_at": started_at,
                    "tags": tags,
                    "summary": summary,
                })

            self.send_json({"runs": runs})
        except Exception as e:
            self.send_error_json(500, f"Error scanning runs: {str(e)}")

    def handle_run_history(self):
        """GET /api/run-history?tb_dir=<tb_dir> - parse TensorBoard event files."""
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        tb_dir = qs.get("tb_dir", [""])[0]

        if not tb_dir or ".." in tb_dir:
            self.send_error_json(400, "Invalid tb_dir parameter")
            return

        try:
            # Use tensorboard's EventAccumulator inside the container
            history_out, err = docker_exec(
                f"""python3 -c "
import json
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

ea = EventAccumulator('{tb_dir}', size_guidance={{'scalars': 0}})
ea.Reload()
tags = ea.Tags().get('scalars', [])

# Build a step-indexed dict
step_data = {{}}
for tag in tags:
    for event in ea.Scalars(tag):
        step = event.step
        if step not in step_data:
            step_data[step] = {{'_step': step, '_wall_time': event.wall_time}}
        step_data[step][tag] = event.value

# Sort by step and output
history = sorted(step_data.values(), key=lambda x: x['_step'])
print(json.dumps({{'history': history, 'tags': tags}}))
" 2>/dev/null""",
                timeout=30
            )
            try:
                result = json.loads(history_out.strip())
                self.send_json(result)
            except (json.JSONDecodeError, ValueError):
                self.send_json({"history": [], "tags": [], "error": err.strip()[:200] if err else "Parse error"})
        except Exception as e:
            self.send_error_json(500, f"Error reading history: {str(e)}")

    def handle_run_log(self):
        """GET /api/run-log?dir=<train_dir>&lines=100 - return raw log output."""
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        train_dir = qs.get("dir", [""])[0]
        max_lines = int(qs.get("lines", ["200"])[0])

        if not train_dir or ".." in train_dir:
            self.send_error_json(400, "Invalid dir parameter")
            return

        try:
            # Find related log files (.out and .err from Slurm)
            logs_out, _ = docker_exec(
                f"find '{train_dir}' -maxdepth 3 -name '*.out' -o -name '*.log' 2>/dev/null | sort -r | head -5; "
                f"find /data -maxdepth 4 -name 'train_*.out' 2>/dev/null | sort -r | head -5"
            )

            stdout_log = ""
            stderr_log = ""
            for log_path in logs_out.strip().splitlines():
                if not log_path:
                    continue
                content, _ = docker_exec(f"tail -n {max_lines} '{log_path}' 2>/dev/null")
                stdout_log = content
                # Also get corresponding .err file
                err_path = log_path.replace(".out", ".err")
                err_content, _ = docker_exec(f"tail -n {max_lines} '{err_path}' 2>/dev/null")
                stderr_log = err_content
                break

            self.send_json({"stdout": stdout_log, "stderr": stderr_log})
        except Exception as e:
            self.send_error_json(500, f"Error reading log: {str(e)}")

    # ==================== Helpers ====================

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())

    def log_message(self, format, *args):
        first_arg = str(args[0]) if args else ""
        if "/api/" in first_arg:
            super().log_message(format, *args)


if __name__ == "__main__":
    print(f"SLURM Dashboard starting on http://localhost:{PORT}")
    print(f"slurmrestd backend: {SLURMRESTD_URL}")
    print(f"TensorBoard backend: {TENSORBOARD_URL}")
    print(f"API version: {SLURM_API_VERSION}")
    server = http.server.HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
