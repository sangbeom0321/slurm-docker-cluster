#!/usr/bin/env python3
"""
SLURM Dashboard - Proxy Server
slurmrestd API에 JWT 인증을 자동으로 붙여서 브라우저에 전달하는 프록시.
W&B API를 GraphQL로 중계하여 실험 데이터를 제공.
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
SLURM_API_VERSION = os.environ.get("SLURM_API_VERSION", "v0.0.44")
WANDB_API_KEY = os.environ.get("WANDB_API_KEY", "")
WANDB_ENTITY = os.environ.get("WANDB_ENTITY", "")
WANDB_BASE_URL = os.environ.get("WANDB_BASE_URL", "https://api.wandb.ai")
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
                _jwt_cache["expires"] = now + 1500  # cache for 25 min
                return token
    except Exception as e:
        print(f"Error getting JWT: {e}")
    return None


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith("/wandb/"):
            self.handle_wandb()
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

        # Build sbatch command
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

        # Map /api/nodes -> /slurm/v0.0.44/nodes
        api_path = self.path[4:]  # remove /api
        # strip query string for mapping
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

    # ==================== W&B API ====================

    def handle_wandb(self):
        """Route /wandb/* requests to appropriate handler."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/wandb/projects":
                self._wandb_projects()
            elif path == "/wandb/runs":
                self._wandb_runs(qs.get("project", [""])[0])
            elif path == "/wandb/history":
                self._wandb_history(
                    qs.get("project", [""])[0],
                    qs.get("run", [""])[0],
                )
            else:
                self.send_error_json(404, "Unknown wandb endpoint")
        except Exception as e:
            self.send_error_json(500, f"W&B API error: {str(e)}")

    def _wandb_gql(self, query, variables=None):
        """Execute a GraphQL query against the W&B API."""
        if not WANDB_API_KEY:
            raise Exception("WANDB_API_KEY not set")
        url = f"{WANDB_BASE_URL}/graphql"
        headers = {
            "Authorization": f"Bearer {WANDB_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if "errors" in data:
            raise Exception(data["errors"][0].get("message", "GraphQL error"))
        return data.get("data", {})

    def _wandb_projects(self):
        """List W&B projects for the configured entity."""
        query = """
        query($entity: String!) {
          entity(name: $entity) {
            projects(first: 100) {
              edges {
                node { name description runCount }
              }
            }
          }
        }
        """
        data = self._wandb_gql(query, {"entity": WANDB_ENTITY})
        edges = data.get("entity", {}).get("projects", {}).get("edges", [])
        projects = []
        for edge in edges:
            node = edge["node"]
            projects.append({
                "name": node["name"],
                "description": node.get("description", ""),
                "run_count": node.get("runCount", 0),
            })
        self.send_json({
            "projects": projects,
            "entity": WANDB_ENTITY,
            "base_url": WANDB_BASE_URL.replace("api.wandb.ai", "wandb.ai"),
        })

    def _wandb_runs(self, project):
        """List runs for a W&B project."""
        query = """
        query($entity: String!, $project: String!) {
          project(name: $project, entityName: $entity) {
            runs(first: 50, order: "-created_at") {
              edges {
                node {
                  id name displayName state
                  config summaryMetrics
                  createdAt heartbeatAt tags
                }
              }
            }
          }
        }
        """
        data = self._wandb_gql(query, {"entity": WANDB_ENTITY, "project": project})
        edges = data.get("project", {}).get("runs", {}).get("edges", [])
        runs = []
        for edge in edges:
            node = edge["node"]
            # Parse config JSON and flatten wandb's {key: {value: X}} format
            raw_config = json.loads(node.get("config") or "{}")
            config = {}
            for k, v in raw_config.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, dict) and "value" in v:
                    config[k] = v["value"]
                else:
                    config[k] = v
            # Parse summary metrics JSON
            summary = json.loads(node.get("summaryMetrics") or "{}")
            # Filter out internal wandb keys from summary
            summary = {k: v for k, v in summary.items() if not k.startswith("_")}
            runs.append({
                "id": node["id"],
                "name": node["name"],
                "display_name": node.get("displayName", node["name"]),
                "state": node.get("state", "unknown"),
                "config": config,
                "summary": summary,
                "created_at": node.get("createdAt", ""),
                "tags": node.get("tags", []),
            })
        self.send_json({"runs": runs, "entity": WANDB_ENTITY, "project": project})

    def _wandb_history(self, project, run_name):
        """Get metric history for a specific run."""
        query = """
        query($entity: String!, $project: String!, $runName: String!) {
          project(name: $project, entityName: $entity) {
            run(name: $runName) {
              history(samples: 500)
            }
          }
        }
        """
        data = self._wandb_gql(
            query,
            {"entity": WANDB_ENTITY, "project": project, "runName": run_name},
        )
        raw = data.get("project", {}).get("run", {}).get("history", [])
        history = []
        for row in raw:
            if isinstance(row, str):
                row = json.loads(row)
            history.append(row)
        self.send_json({"history": history})

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
        # Only log API calls, not static files
        if "/api/" in (args[0] if args else "") or "/wandb/" in (args[0] if args else ""):
            super().log_message(format, *args)


if __name__ == "__main__":
    print(f"SLURM Dashboard starting on http://localhost:{PORT}")
    print(f"slurmrestd backend: {SLURMRESTD_URL}")
    print(f"API version: {SLURM_API_VERSION}")
    print(f"W&B entity: {WANDB_ENTITY or '(not set)'}")
    print(f"W&B API key: {'configured' if WANDB_API_KEY else 'NOT SET'}")
    server = http.server.HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
