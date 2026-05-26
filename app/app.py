"""Interactive demo app for the cloud architecture assessment.

The UI showcases the running infrastructure:
- Identifies which ECS task served each request (via ECS task metadata)
- Lets the user fire batches of requests and visualizes load-balancer fan-out
- Optional CPU stress endpoint to trigger autoscaling on demand

Stateless by design — each task keeps its own counters in memory; the
"unique tasks seen" view on the frontend is what proves multi-task
deployment is real.
"""
import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template_string, request

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("app")

STARTED_AT = time.time()
REQUEST_COUNT = 0
REQUEST_LOCK = threading.Lock()
HOSTNAME = socket.gethostname()


def fetch_task_metadata():
    """Pull this task's metadata from the ECS agent (no IAM required)."""
    uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
    if not uri:
        return {}
    try:
        with urllib.request.urlopen(f"{uri}/task", timeout=2) as r:
            data = json.loads(r.read())
        return {
            "task_id": data.get("TaskARN", "").split("/")[-1],
            "availability_zone": data.get("AvailabilityZone"),
            "cluster": data.get("Cluster", "").split("/")[-1],
            "family": data.get("Family"),
            "revision": data.get("Revision"),
            "cpu": data.get("Limits", {}).get("CPU"),
            "memory": data.get("Limits", {}).get("Memory"),
        }
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as e:
        log.warning("Could not fetch ECS metadata (running outside ECS?): %s", e)
        return {}


ECS_META = fetch_task_metadata()


def task_info():
    """Payload returned by /api/info and /api/ping."""
    uptime = int(time.time() - STARTED_AT)
    with REQUEST_LOCK:
        count = REQUEST_COUNT
    return {
        "hostname": HOSTNAME,
        "task_id": ECS_META.get("task_id", HOSTNAME),
        "availability_zone": ECS_META.get("availability_zone", "local"),
        "cluster": ECS_META.get("cluster", "local"),
        "cpu_units": ECS_META.get("cpu", "n/a"),
        "memory_mb": ECS_META.get("memory", "n/a"),
        "env": os.environ.get("APP_ENV", "dev"),
        "uptime_seconds": uptime,
        "request_count": count,
        "now": datetime.now(timezone.utc).isoformat(),
    }


@app.before_request
def count_requests():
    # Don't count ALB health checks — they'd dominate the counter
    if request.path == "/health":
        return
    global REQUEST_COUNT
    with REQUEST_LOCK:
        REQUEST_COUNT += 1


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    """ALB target group health check."""
    return jsonify(status="ok"), 200


@app.route("/api/info")
def api_info():
    """Current task info (used by the dashboard on load and on poll)."""
    return jsonify(task_info())


@app.route("/api/ping")
def api_ping():
    """Same payload as /api/info — meant to be called repeatedly so the
    frontend can show which task answers each request."""
    return jsonify(task_info())


@app.route("/api/stress", methods=["POST"])
def api_stress():
    """Burn CPU for N seconds (capped) so we can watch autoscaling react."""
    try:
        seconds = min(int(request.args.get("seconds", 3)), 10)
    except (TypeError, ValueError):
        seconds = 3
    log.info("CPU stress for %ds on task %s", seconds, HOSTNAME)
    end = time.time() + seconds
    # Tight Python loop is plenty to spike a 0.25-vCPU Fargate task
    while time.time() < end:
        sum(i * i for i in range(20_000))
    return jsonify({"stressed_for_seconds": seconds, **task_info()})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ECS Fargate Demo · webapp</title>
<style>
  :root {
    --bg: #0b1020;
    --bg-2: #11172a;
    --bg-3: #1a223a;
    --border: #2a3354;
    --fg: #e6e9f2;
    --fg-dim: #9aa3bf;
    --accent: #7aa2ff;
    --accent-2: #5eead4;
    --warn: #fbbf24;
    --danger: #f87171;
    --ok: #34d399;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: radial-gradient(1100px 600px at 80% -10%, #1a2447 0%, var(--bg) 55%);
    color: var(--fg);
    min-height: 100vh;
  }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 32px 24px 60px; }
  header { margin-bottom: 28px; }
  header h1 { margin: 0; font-size: 26px; letter-spacing: -0.01em; }
  header p  { margin: 6px 0 0; color: var(--fg-dim); font-size: 14px; }
  .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
  .card {
    background: linear-gradient(180deg, var(--bg-2), var(--bg-3));
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px 20px;
  }
  .card h2 {
    margin: 0 0 14px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--fg-dim);
  }
  .col-12 { grid-column: span 12; }
  .kv { display: grid; grid-template-columns: 160px 1fr; row-gap: 8px; font-size: 14px; }
  .kv .k { color: var(--fg-dim); }
  .kv .v { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }
  .pill {
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 12px; background: var(--bg-3); border: 1px solid var(--border);
    color: var(--fg-dim);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    margin-left: 8px;
  }
  .pill.live { color: var(--ok); border-color: rgba(52,211,153,0.4); }
  .btn-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; align-items: center; }
  button {
    background: var(--bg-3); color: var(--fg);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 9px 14px; font-size: 13px; cursor: pointer;
    font-family: inherit;
    transition: border-color 120ms, background 120ms, transform 60ms;
  }
  button:hover  { border-color: var(--accent); background: #1f2a4a; }
  button:active { transform: translateY(1px); }
  button.warn:hover { border-color: var(--warn); }
  button.danger:hover { border-color: var(--danger); }
  .stats { display: flex; gap: 28px; margin-bottom: 14px; flex-wrap: wrap; }
  .stat .num { font-size: 28px; font-weight: 600; }
  .stat .lbl { color: var(--fg-dim); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
  .task-chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--bg-3);
    font-family: ui-monospace, monospace; font-size: 12px;
    display: flex; flex-direction: column; gap: 2px; min-width: 110px;
  }
  .chip .id { color: var(--fg); font-weight: 600; }
  .chip .meta { color: var(--fg-dim); font-size: 11px; }
  .log {
    max-height: 280px; overflow-y: auto;
    font-family: ui-monospace, monospace; font-size: 12.5px;
    background: #070b1a; border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 12px;
  }
  .log .row {
    padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04);
    display: grid; grid-template-columns: 80px 110px 110px 70px 1fr;
    gap: 10px; align-items: baseline;
  }
  .log .row:last-child { border-bottom: none; }
  .log .t { color: var(--fg-dim); }
  .log .tid { font-weight: 600; }
  .log .az { color: var(--fg-dim); }
  .log .ms { color: var(--accent-2); }
  .log .st.ok  { color: var(--ok); }
  .log .st.err { color: var(--danger); }
  .empty { color: var(--fg-dim); font-style: italic; padding: 6px 0; }
  footer { margin-top: 28px; color: var(--fg-dim); font-size: 12px; text-align: center; }
</style>
</head>
<body>
<div class="wrap">

  <header>
    <h1>ECS Fargate Demo<span class="pill live" id="liveDot">● LIVE</span></h1>
    <p>Containerized Flask app on AWS — VPC + ALB + ECS Fargate + ECR + GitHub Actions CI/CD.
       This page is being served by one of the tasks behind the load balancer.</p>
  </header>

  <div class="grid">

    <section class="card col-12">
      <h2>This task</h2>
      <div class="kv">
        <div class="k">Task ID</div>          <div class="v" id="thisTaskId">—</div>
        <div class="k">Availability zone</div><div class="v" id="thisAz">—</div>
        <div class="k">Cluster</div>          <div class="v" id="thisCluster">—</div>
        <div class="k">CPU / memory</div>     <div class="v" id="thisCpuMem">—</div>
        <div class="k">Environment</div>      <div class="v" id="thisEnv">—</div>
        <div class="k">Uptime</div>           <div class="v" id="thisUptime">—</div>
        <div class="k">Requests served</div>  <div class="v" id="thisReqs">—</div>
      </div>
    </section>

    <section class="card col-12">
      <h2>Load balancer fan-out</h2>
      <p style="margin:0 0 14px; color: var(--fg-dim); font-size: 13px;">
        Fire requests through the ALB and watch which task answers each one.
        With multiple tasks behind the load balancer, requests should fan out
        across them — you'll see chips light up for every distinct task.
      </p>
      <div class="btn-row">
        <button onclick="ping(1)">Ping × 1</button>
        <button onclick="ping(10)">Ping × 10</button>
        <button onclick="ping(50)">Ping × 50</button>
        <button onclick="ping(200)">Ping × 200</button>
        <button class="warn" onclick="resetLog()">Reset</button>
      </div>
      <div class="stats">
        <div class="stat"><div class="num" id="totalReqs">0</div><div class="lbl">Total requests</div></div>
        <div class="stat"><div class="num" id="uniqueTasks">0</div><div class="lbl">Unique tasks seen</div></div>
        <div class="stat"><div class="num" id="avgMs">—</div><div class="lbl">Avg latency (ms)</div></div>
      </div>
      <div class="task-chips" id="taskChips">
        <span class="empty">Click a Ping button to see tasks light up.</span>
      </div>
    </section>

    <section class="card col-12">
      <h2>Stress test — exercise autoscaling</h2>
      <p style="margin:0 0 14px; color: var(--fg-dim); font-size: 13px;">
        Burn CPU on one task for a few seconds. Combined with rounds of
        Ping × 200 above, this pushes the service past the 60% CPU autoscaling
        target — within ~60s you should see new tasks come up in CloudWatch.
      </p>
      <div class="btn-row">
        <button class="warn" onclick="stress(3)">Stress 3s</button>
        <button class="warn" onclick="stress(5)">Stress 5s</button>
        <button class="danger" onclick="stress(10)">Stress 10s</button>
        <span id="stressStatus" style="color: var(--fg-dim); font-size: 13px;"></span>
      </div>
    </section>

    <section class="card col-12">
      <h2>Activity log</h2>
      <div class="log" id="log">
        <div class="empty">No activity yet — try a Ping or Stress button above.</div>
      </div>
    </section>

  </div>

  <footer>
    VPC · 2 AZs · public + private subnets · single NAT · ALB · ECS Fargate · ECR · CloudWatch · GitHub Actions OIDC
  </footer>
</div>

<script>
  // -------- state --------
  const seenTasks = new Map();   // task_id -> { count, az, color }
  let totalReqs = 0;
  let latencies = [];

  const palette = [
    "#7aa2ff", "#5eead4", "#fbbf24", "#f472b6",
    "#a78bfa", "#34d399", "#fb923c", "#60a5fa",
    "#f87171", "#c084fc"
  ];
  function colorFor(id) {
    let h = 0;
    for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
    return palette[Math.abs(h) % palette.length];
  }
  function shortId(id) { return (id || "").slice(0, 8); }
  function nowHHMMSS() { return new Date().toTimeString().slice(0,8); }

  // -------- "this task" panel (polls every 5s) --------
  async function loadSelf() {
    try {
      const r = await fetch("/api/info", { cache: "no-store" });
      const d = await r.json();
      document.getElementById("thisTaskId").textContent  = d.task_id;
      document.getElementById("thisAz").textContent      = d.availability_zone;
      document.getElementById("thisCluster").textContent = d.cluster;
      document.getElementById("thisCpuMem").textContent  = `${d.cpu_units} units · ${d.memory_mb} MB`;
      document.getElementById("thisEnv").textContent     = d.env;
      document.getElementById("thisUptime").textContent  = fmtDuration(d.uptime_seconds);
      document.getElementById("thisReqs").textContent    = d.request_count.toLocaleString();
    } catch (e) {
      const dot = document.getElementById("liveDot");
      dot.textContent = "● OFFLINE";
      dot.style.color = "var(--danger)";
    }
  }
  function fmtDuration(s) {
    if (s < 60) return s + "s";
    if (s < 3600) return Math.floor(s/60) + "m " + (s%60) + "s";
    return Math.floor(s/3600) + "h " + Math.floor((s%3600)/60) + "m";
  }
  setInterval(loadSelf, 5000);
  loadSelf();

  // -------- ping fan-out --------
  async function ping(n) {
    await Promise.allSettled(
      Array.from({length: n}, () => doPing())
    );
  }
  async function doPing() {
    const t0 = performance.now();
    let ok = true, data = null;
    try {
      const r = await fetch("/api/ping", { cache: "no-store" });
      data = await r.json();
      ok = r.ok;
    } catch (e) { ok = false; }
    record(data, ok, Math.round(performance.now() - t0));
  }
  function record(data, ok, ms) {
    totalReqs += 1;
    latencies.push(ms);
    if (latencies.length > 500) latencies.shift();

    const taskId = data?.task_id || "?";
    const az     = data?.availability_zone || "?";

    const t = seenTasks.get(taskId) || { count: 0, az, color: colorFor(taskId) };
    t.count += 1; t.az = az;
    seenTasks.set(taskId, t);

    document.getElementById("totalReqs").textContent   = totalReqs.toLocaleString();
    document.getElementById("uniqueTasks").textContent = seenTasks.size;
    const avg = latencies.reduce((a,b)=>a+b,0) / latencies.length;
    document.getElementById("avgMs").textContent = avg.toFixed(0);

    renderChips();
    appendLog(taskId, az, ms, ok);
  }
  function renderChips() {
    const root = document.getElementById("taskChips");
    if (seenTasks.size === 0) return;
    root.innerHTML = [...seenTasks.entries()].map(([id, info]) => `
      <div class="chip" style="border-left: 3px solid ${info.color}">
        <div class="id" title="${id}">${shortId(id)}</div>
        <div class="meta">${info.count} req · ${info.az}</div>
      </div>
    `).join("");
  }
  function appendLog(taskId, az, ms, ok) {
    const log = document.getElementById("log");
    if (log.querySelector(".empty")) log.innerHTML = "";
    const color = colorFor(taskId);
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <span class="t">${nowHHMMSS()}</span>
      <span class="tid" style="color:${color}">${shortId(taskId)}</span>
      <span class="az">${az}</span>
      <span class="ms">${ms}ms</span>
      <span class="st ${ok ? 'ok' : 'err'}">${ok ? '200 OK' : 'ERROR'}</span>
    `;
    log.prepend(row);
    while (log.children.length > 100) log.removeChild(log.lastChild);
  }
  function resetLog() {
    seenTasks.clear();
    totalReqs = 0;
    latencies = [];
    document.getElementById("totalReqs").textContent   = "0";
    document.getElementById("uniqueTasks").textContent = "0";
    document.getElementById("avgMs").textContent       = "—";
    document.getElementById("taskChips").innerHTML =
      '<span class="empty">Click a Ping button to see tasks light up.</span>';
    document.getElementById("log").innerHTML =
      '<div class="empty">No activity yet — try a Ping or Stress button above.</div>';
  }

  // -------- stress --------
  async function stress(seconds) {
    const status = document.getElementById("stressStatus");
    status.textContent = `stressing one task for ${seconds}s…`;
    const t0 = performance.now();
    try {
      const r = await fetch(`/api/stress?seconds=${seconds}`, { method: "POST" });
      const d = await r.json();
      const ms = Math.round(performance.now() - t0);
      status.innerHTML =
        `done — task <strong style="color:${colorFor(d.task_id)}">${shortId(d.task_id)}</strong>` +
        ` in <strong>${d.availability_zone}</strong> burned <strong>${d.stressed_for_seconds}s</strong>` +
        ` of CPU (round-trip ${ms}ms)`;
      record(d, true, ms);
    } catch (e) {
      status.textContent = `error: ${e.message}`;
    }
  }
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
