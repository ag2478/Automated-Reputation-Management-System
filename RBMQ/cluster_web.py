#!/usr/bin/env python3

import base64
import concurrent.futures
import ipaddress
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NODES = [
    ("ag2478-dev", "100.80.61.81"),
    ("ag2478-test", "100.79.190.69"),
    ("ag2478-prod", "100.100.75.81"),
    ("aks55-dev-1", "100.79.161.71"),
    ("ojo-dev", "100.110.5.44"),
    ("jxo-dev", "100.96.160.83"),
]

LOCAL_HOST = socket.gethostname()
RMQ_USER = os.getenv("RMQ_USER", "repo_user")
RMQ_PASS = os.getenv("RMQ_PASS", "repo_pass")
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

# Tunable slow-network parameters (override in /etc/default/cluster_web if needed)
TCP_TIMEOUT = float(os.getenv("TCP_TIMEOUT", "2.5"))
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "5.0"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "8.0"))
FAIL_THRESHOLD = int(os.getenv("FAIL_THRESHOLD", "2"))
SLOW_MS = int(os.getenv("SLOW_MS", "400"))
STALE_GRACE_SEC = float(os.getenv("STALE_GRACE_SEC", "60.0"))

TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
PORTS_TO_CHECK = (4369, 5672, 15672, 25672)

_LAST_GOOD_API = (LOCAL_HOST, "127.0.0.1")
_PORT_MISSES = {(h, p): 0 for h, _ in NODES for p in PORTS_TO_CHECK}
_PORT_WAS_UP = {(h, p): False for h, _ in NODES for p in PORTS_TO_CHECK}
_LAST_API_CACHE = {"ts": 0.0, "source": None, "nodes": [], "conns": [], "queues": []}

_CACHE_LOCK = threading.Lock()
_CACHE_BYTES = json.dumps({
    "served_by": LOCAL_HOST,
    "web_port": WEB_PORT,
    "timestamp": "Initializing...",
    "api_source": None,
    "api_error": None,
    "api_stale": False,
    "nodes": [],
    "load_balancing": {"rows": [], "verdict": {"state": "IDLE", "detail": "Collecting initial telemetry..."}},
    "threat_monitoring": {
        "status": "CLEAN",
        "alerts": [],
        "rogue_peers": [],
        "partitions": [],
        "threat_queues": [],
        "stalled_conns": [],
    },
}).encode()


def check_tcp(ip: str, port: int, timeout: float = TCP_TIMEOUT):
    start = time.monotonic()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            rtt_ms = int((time.monotonic() - start) * 1000)
            return True, rtt_ms
    except OSError:
        return False, None


def is_tailscale_or_local(raw_ip: str) -> bool:
    if not raw_ip:
        return False
    cleaned = raw_ip.strip().strip("[]").split("%")[0]
    try:
        addr = ipaddress.ip_address(cleaned)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_loopback or (isinstance(addr, ipaddress.IPv4Address) and addr in TAILSCALE_NET)


def rmq_api_get(endpoint: str):
    global _LAST_GOOD_API
    token = base64.b64encode(f"{RMQ_USER}:{RMQ_PASS}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}

    targets = [_LAST_GOOD_API, (LOCAL_HOST, "127.0.0.1")] + list(NODES)
    seen_ips = set()
    ordered_targets = []
    for host, ip in targets:
        if ip not in seen_ips:
            seen_ips.add(ip)
            ordered_targets.append((host, ip))

    last_err = "No RabbitMQ management API reachable"
    for host, ip in ordered_targets:
        url = f"http://{ip}:15672/api/{endpoint}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                _LAST_GOOD_API = (host, ip)
                return json.loads(resp.read().decode()), host, None
        except urllib.error.HTTPError as exc:
            last_err = f"{host} HTTP {exc.code} (check RMQ_USER/RMQ_PASS)"
            if exc.code == 401:
                break
        except Exception as exc:
            last_err = f"{host}: {exc}"
    return None, None, last_err


def collect_telemetry() -> dict:
    # 1. Parallel TCP probes with 2-strike flap protection and latency tracking
    port_state = {h: {} for h, _ in NODES}
    node_rtt = {h: None for h, _ in NODES}

    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futs = {
            pool.submit(check_tcp, ip, port): (host, port)
            for host, ip in NODES
            for port in PORTS_TO_CHECK
        }
        for fut in concurrent.futures.as_completed(futs):
            host, port = futs[fut]
            ok, rtt_ms = fut.result()
            key = (host, port)
            if ok:
                _PORT_MISSES[key] = 0
                _PORT_WAS_UP[key] = True
                port_state[host][str(port)] = "SLOW" if (rtt_ms is not None and rtt_ms >= SLOW_MS) else "OPEN"
                if rtt_ms is not None and (node_rtt[host] is None or rtt_ms < node_rtt[host]):
                    node_rtt[host] = rtt_ms
            else:
                _PORT_MISSES[key] += 1
                if _PORT_WAS_UP[key] and _PORT_MISSES[key] < FAIL_THRESHOLD:
                    port_state[host][str(port)] = "RETRY"
                else:
                    _PORT_WAS_UP[key] = False
                    port_state[host][str(port)] = "CLOSED"

    # 2. Fetch RabbitMQ Management API with stale-cache fallback on transient VPN hiccups
    api_nodes, api_source, err_n = rmq_api_get("nodes")
    api_conns, _, err_c = rmq_api_get("connections")
    api_queues, _, err_q = rmq_api_get("queues")
    api_error = err_n or err_c or err_q
    api_stale = False

    now_mono = time.monotonic()
    if api_error is None:
        _LAST_API_CACHE.update({
            "ts": now_mono,
            "source": api_source,
            "nodes": api_nodes or [],
            "conns": api_conns or [],
            "queues": api_queues or [],
        })
    elif _LAST_API_CACHE["ts"] > 0 and (now_mono - _LAST_API_CACHE["ts"]) <= STALE_GRACE_SEC:
        api_stale = True
        api_source = f"{_LAST_API_CACHE['source']} (cached)"
        api_nodes = _LAST_API_CACHE["nodes"]
        api_conns = _LAST_API_CACHE["conns"]
        api_queues = _LAST_API_CACHE["queues"]
        age = int(now_mono - _LAST_API_CACHE["ts"])
        api_error = f"Slow/unreachable API — displaying cached data ({age}s old): {api_error}"

    api_nodes = api_nodes or []
    api_conns = api_conns or []
    api_queues = api_queues or []

    running_nodes = {n.get("name"): n for n in api_nodes}
    queue_by_name = {q.get("name"): q for q in api_queues}

    # 3. Node health & Mnesia membership
    nodes_out = []
    joined_count = 0
    partitions = []
    slow_nodes = []

    for host, ip in NODES:
        rname = f"rabbit@{host}"
        info = running_nodes.get(rname)
        if info and info.get("running"):
            mnesia = "JOINED"
            joined_count += 1
        elif info:
            mnesia = "STOPPED"
        else:
            mnesia = "ISOLATED"

        node_parts = (info or {}).get("partitions") or []
        if node_parts:
            partitions.append({"node": rname, "partitioned_from": node_parts})

        agent_q = queue_by_name.get(f"agent_{host}")
        agent_online = bool(agent_q and (agent_q.get("consumers") or 0) > 0)

        rtt = node_rtt[host]
        if rtt is not None and rtt >= SLOW_MS:
            slow_nodes.append(f"{host} ({rtt}ms)")

        nodes_out.append({
            "host": host,
            "ip": ip,
            "mnesia": mnesia,
            "rtt_ms": rtt,
            "ports": port_state[host],
            "agent_online": agent_online,
            "mem_mb": round(((info or {}).get("mem_used") or 0) / (1024 * 1024), 1),
        })

    # 4. Load balancing verification
    total_conns = len(api_conns)
    lb_rows = []
    active_conn_nodes = 0
    max_share = 0.0

    for host, _ in NODES:
        rname = f"rabbit@{host}"
        node_conns = sum(1 for c in api_conns if c.get("node") == rname)
        share_pct = round((node_conns * 100) / total_conns, 1) if total_conns else 0.0
        if node_conns > 0:
            active_conn_nodes += 1
        if share_pct > max_share:
            max_share = share_pct

        leaders = 0
        consumers = 0
        backlog = 0
        for q in api_queues:
            owner = q.get("leader") or q.get("node") or ""
            if owner == rname:
                leaders += 1
                consumers += int(q.get("consumers") or 0)
                backlog += int(q.get("messages") or 0)

        lb_rows.append({
            "host": host,
            "conns": node_conns,
            "share_pct": share_pct,
            "leaders": leaders,
            "consumers": consumers,
            "backlog": backlog,
        })

    if total_conns == 0:
        lb_verdict = {"state": "IDLE", "detail": f"0 active AMQP connections across {joined_count} joined nodes"}
    elif active_conn_nodes <= 1 and joined_count > 1:
        lb_verdict = {"state": "SKEWED", "detail": f"100% of {total_conns} connections pinned to 1 node"}
    elif max_share > 60 and joined_count > 1:
        lb_verdict = {"state": "UNEVEN", "detail": f"Heaviest node holds {max_share}% of {total_conns} connections"}
    else:
        lb_verdict = {"state": "BALANCED", "detail": f"{total_conns} connections across {active_conn_nodes}/{joined_count} joined nodes"}

    # 5. Cluster-wide Threat Monitoring
    rogue_peers = []
    stalled_conns = []
    for c in api_conns:
        peer = c.get("peer_host", "")
        if not is_tailscale_or_local(peer):
            rogue_peers.append({
                "peer": f"{peer}:{c.get('peer_port', '')}",
                "node": c.get("node", ""),
                "user": c.get("user", ""),
            })
        if c.get("state") in ("starting", "tuning", "opening", "blocked", "blocking"):
            stalled_conns.append({
                "peer": peer,
                "node": c.get("node", ""),
                "state": c.get("state", ""),
            })

    threat_queues = []
    for q in api_queues:
        qname = q.get("name", "")
        if "threat" in qname.lower():
            threat_queues.append({
                "name": qname,
                "messages": int(q.get("messages") or 0),
                "consumers": int(q.get("consumers") or 0),
                "node": q.get("leader") or q.get("node") or "",
            })

    alerts = []
    if rogue_peers:
        alerts.append(f"CRITICAL: {len(rogue_peers)} non-Tailscale client connection(s) detected")
    if partitions:
        alerts.append(f"CRITICAL: Network partition active on {len(partitions)} node(s)")
    if slow_nodes:
        alerts.append(f"DEGRADED LINK: High Tailscale latency on {', '.join(slow_nodes)}")
    for tq in threat_queues:
        if tq["consumers"] == 0:
            alerts.append(f"WARNING: Threat queue '{tq['name']}' has 0 active consumers ({tq['messages']} queued)")
    if stalled_conns:
        alerts.append(f"WARNING: {len(stalled_conns)} connection(s) stuck in handshake or blocked state")
    if joined_count < len(NODES) and not api_error:
        alerts.append(f"WARNING: Only {joined_count}/{len(NODES)} nodes joined in Mnesia cluster")

    return {
        "served_by": LOCAL_HOST,
        "web_port": WEB_PORT,
        "timestamp": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "api_source": api_source,
        "api_error": api_error,
        "api_stale": api_stale,
        "nodes": nodes_out,
        "load_balancing": {"rows": lb_rows, "verdict": lb_verdict},
        "threat_monitoring": {
            "status": "ALERT" if alerts else "CLEAN",
            "alerts": alerts,
            "rogue_peers": rogue_peers,
            "partitions": partitions,
            "threat_queues": threat_queues,
            "stalled_conns": stalled_conns,
        },
    }


def background_poller():
    global _CACHE_BYTES
    while True:
        try:
            payload = json.dumps(collect_telemetry()).encode()
            with _CACHE_LOCK:
                _CACHE_BYTES = payload
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>RabbitMQ Cluster, Load Balancing &amp; Threat Monitor</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }
  h1 { margin: 0 0 6px; font-size: 1.35rem; color: #38bdf8; }
  .meta { color: #94a3b8; font-size: 0.85rem; margin-bottom: 12px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
  .hosts { margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; font-size: 0.82rem; }
  .hosts a { color: #93c5fd; text-decoration: none; background: #1e293b; border: 1px solid #334155; padding: 4px 10px; border-radius: 6px; }
  .hosts a.active { background: #0284c7; color: #fff; border-color: #38bdf8; font-weight: 700; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; margin-bottom: 18px; }
  .card h2 { margin: 0 0 12px; font-size: 1rem; color: #f8fafc; display: flex; justify-content: space-between; align-items: center; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #334155; }
  th { color: #94a3b8; font-weight: 600; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; }
  .ok { background: #064e3b; color: #34d399; }
  .warn { background: #78350f; color: #fbbf24; }
  .err { background: #7f1d1d; color: #f87171; }
  .bar-bg { background: #0f172a; border-radius: 6px; height: 10px; width: 120px; display: inline-block; vertical-align: middle; margin-right: 6px; overflow: hidden; }
  .bar-fill { background: #38bdf8; height: 100%; }
  button { background: #0284c7; color: #fff; border: none; border-radius: 6px; padding: 5px 12px; cursor: pointer; font-weight: 600; }
  button:hover { background: #0369a1; }
  ul { margin: 6px 0 0; padding-left: 20px; }
  li { margin: 4px 0; }
  .banner { padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-weight: 600; }
</style>
</head>
<body>
  <h1>Tailscale &amp; RabbitMQ Cluster Monitor (Active-Active Web Portal)</h1>
  <div class="meta">
    <span id="served">Served by: ...</span>
    <span id="src">API Source: ...</span>
    <span id="ts">Loading...</span>
    <button onclick="refresh()">Refresh Now</button>
  </div>
  <div class="hosts" id="hostLinks"></div>
  <div id="apiErr" class="banner" style="display:none;"></div>

  <div class="card">
    <h2>1. Cluster Node &amp; Port Topology</h2>
    <table>
      <thead><tr><th>Node</th><th>Tailscale IP</th><th>Latency</th><th>Mnesia</th><th>4369</th><th>5672</th><th>15672</th><th>25672</th><th>Agent Queue</th><th>RAM (MB)</th></tr></thead>
      <tbody id="nodesBody"></tbody>
    </table>
  </div>

  <div class="card">
    <h2>2. RabbitMQ Load Balancing Verification <span id="lbBadge" class="badge"></span></h2>
    <div id="lbDetail" style="margin-bottom:10px;color:#cbd5e1;font-size:0.9rem;"></div>
    <table>
      <thead><tr><th>Node</th><th>Connections</th><th>Share</th><th>Queue Leaders</th><th>Consumers</th><th>Backlog Msgs</th></tr></thead>
      <tbody id="lbBody"></tbody>
    </table>
  </div>

  <div class="card">
    <h2>3. Cluster-Wide Threat Monitoring <span id="tmBadge" class="badge"></span></h2>
    <div id="tmContent"></div>
  </div>

<script>
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const badge = (text, cls) => `<span class="badge ${cls}">${esc(text)}</span>`;
const portBadge = st => badge(st, st === 'OPEN' ? 'ok' : (st === 'SLOW' || st === 'RETRY' ? 'warn' : 'err'));
let consecutiveFails = 0;
let knownNodes = [];
let inFlight = false;

async function failoverToPeer() {
  const peers = knownNodes.filter(n => window.location.hostname !== n.ip);
  if (!peers.length) return;
  try {
    const winner = await Promise.any(peers.map(async n => {
      const url = `http://${n.ip}:${n.port || 8080}`;
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 6000);
      try {
        const r = await fetch(`${url}/api/status`, { signal: ctrl.signal });
        if (!r.ok) throw new Error();
        return url;
      } finally { clearTimeout(t); }
    }));
    window.location.href = winner;
  } catch (_) {}
}

async function refresh() {
  if (inFlight) return;
  inFlight = true;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  try {
    const res = await fetch('/api/status', { signal: ctrl.signal });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    consecutiveFails = 0;

    knownNodes = d.nodes.map(n => ({ host: n.host, ip: n.ip, port: d.web_port }));
    document.getElementById('served').textContent = 'Served by: ' + d.served_by;
    document.getElementById('src').textContent = d.api_source ? ('API Source: ' + d.api_source) : 'API Source: None';
    document.getElementById('ts').textContent = 'Updated: ' + d.timestamp;

    document.getElementById('hostLinks').innerHTML =
      '<span style="color:#94a3b8;">Failover Mirrors:</span>' +
      d.nodes.map(n => `<a href="http://${esc(n.ip)}:${esc(d.web_port)}" class="${n.host === d.served_by ? 'active' : ''}">${esc(n.host)}</a>`).join('');

    const errBox = document.getElementById('apiErr');
    if (d.api_error) {
      errBox.style.display = 'block';
      errBox.className = 'banner ' + (d.api_stale ? 'warn' : 'err');
      errBox.textContent = d.api_error;
    } else {
      errBox.style.display = 'none';
    }

    document.getElementById('nodesBody').innerHTML = d.nodes.map(n => {
      const rttLabel = n.rtt_ms === null ? badge('TIMEOUT', 'err') : badge(n.rtt_ms + ' ms', n.rtt_ms >= 400 ? 'warn' : 'ok');
      return `<tr>
        <td><strong>${esc(n.host)}</strong></td>
        <td>${esc(n.ip)}</td>
        <td>${rttLabel}</td>
        <td>${badge(n.mnesia, n.mnesia === 'JOINED' ? 'ok' : 'err')}</td>
        <td>${portBadge(n.ports['4369'])}</td>
        <td>${portBadge(n.ports['5672'])}</td>
        <td>${portBadge(n.ports['15672'])}</td>
        <td>${portBadge(n.ports['25672'])}</td>
        <td>${badge(n.agent_online ? 'ONLINE' : 'OFFLINE', n.agent_online ? 'ok' : 'warn')}</td>
        <td>${esc(n.mem_mb)}</td>
      </tr>`;
    }).join('');

    const lb = d.load_balancing;
    const lbCls = lb.verdict.state === 'BALANCED' ? 'ok' : (lb.verdict.state === 'SKEWED' ? 'err' : 'warn');
    const lbBadge = document.getElementById('lbBadge');
    lbBadge.className = 'badge ' + lbCls;
    lbBadge.textContent = lb.verdict.state;
    document.getElementById('lbDetail').textContent = lb.verdict.detail;
    document.getElementById('lbBody').innerHTML = lb.rows.map(r => `
      <tr>
        <td><strong>${esc(r.host)}</strong></td>
        <td>${esc(r.conns)}</td>
        <td><span class="bar-bg"><span class="bar-fill" style="width:${r.share_pct}%"></span></span>${esc(r.share_pct)}%</td>
        <td>${esc(r.leaders)}</td>
        <td>${esc(r.consumers)}</td>
        <td>${esc(r.backlog)}</td>
      </tr>`).join('');

    const tm = d.threat_monitoring;
    const tmBadge = document.getElementById('tmBadge');
    tmBadge.className = 'badge ' + (tm.status === 'CLEAN' ? 'ok' : 'err');
    tmBadge.textContent = tm.status;

    let html = '';
    if (tm.alerts.length) {
      html += '<div class="banner err">Active Alerts:<ul>' + tm.alerts.map(a => `<li>${esc(a)}</li>`).join('') + '</ul></div>';
    } else {
      html += '<div class="banner ok">Perimeter clean: 100% of AMQP connections originate from Tailscale/Loopback, no partitions detected.</div>';
    }
    if (tm.rogue_peers.length) {
      html += '<p><strong>Non-Tailscale Connections:</strong></p><ul>' +
        tm.rogue_peers.map(p => `<li>${esc(p.peer)} on ${esc(p.node)} (user: ${esc(p.user)})</li>`).join('') + '</ul>';
    }
    html += '<p><strong>Threat Queues:</strong></p>';
    if (tm.threat_queues.length) {
      html += '<ul>' + tm.threat_queues.map(q =>
        `<li><strong>${esc(q.name)}</strong> (${esc(q.node)}) — Messages: ${esc(q.messages)}, Consumers: ${esc(q.consumers)}</li>`
      ).join('') + '</ul>';
    } else {
      html += '<p style="color:#94a3b8;">No queues matching "threat" are currently declared.</p>';
    }
    document.getElementById('tmContent').innerHTML = html;
  } catch (e) {
    consecutiveFails++;
    const errBox = document.getElementById('apiErr');
    errBox.style.display = 'block';
    errBox.className = 'banner warn';
    errBox.textContent = `Slow or dropped response from current VM (${consecutiveFails}/4 before failover)...`;
    if (consecutiveFails >= 4) failoverToPeer();
  } finally {
    clearTimeout(timer);
    inFlight = false;
  }
}
refresh();
setInterval(refresh, 8000);
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/api/status":
            with _CACHE_LOCK:
                payload = _CACHE_BYTES
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path in ("/", "/index.html"):
            payload = HTML_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_error(404)


if __name__ == "__main__":
    threading.Thread(target=background_poller, daemon=True).start()
    server = ThreadingHTTPServer((WEB_HOST, WEB_PORT), DashboardHandler)
    print(f"Cluster Web Monitor ({LOCAL_HOST}) running at http://{WEB_HOST}:{WEB_PORT}")
    server.serve_forever()