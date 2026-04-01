import React, { useEffect, useRef } from "react";
import { fetchNetmap } from "../api";

/**
 * NetMap - Interactive network topology visualization on canvas
 * 
 * Props:
 *   run: Run object with id, name, etc. (from loadedRun in App)
 *   onPanelOpen: (open) => void - called when detail panel opens/closes
 * 
 * Fetches: GET /api/runs/{run_id}/netmap or GET /api/netmap
 * 
 * Expected response:
 *   {
 *     nodes: [
 *       {
 *         id: string ("CMD", "R1", "S1")
 *         label: string (human-readable name)
 *         role: "command" | "relay" | "sensor"
 *         x: number (0.0-1.0, normalized position)
 *         y: number (0.0-1.0, normalized position)
 *         battery: number (0-100)
 *         drain: number (% per hour)
 *         traffic: number (0-100)
 *         health: "good" | "warning" | "critical"
 *         packetsIn: number
 *         packetsOut: number
 *         retries: number
 *         collisions: number
 *         aiDet: number (AI detections on this node)
 *         events: string[]
 *         powerBreakdown: {radio: number, processor: number, mic: number}
 *         children?: string[] (child node IDs for this relay)
 *         parent?: string (parent node ID)
 *       }
 *     ],
 *     edges: [
 *       {
 *         from: string (node ID)
 *         to: string (node ID)
 *         congestion: number (0-100)
 *         packetLoss: number (percentage)
 *         retries: number
 *         collisions: number
 *         avgDelay: number (milliseconds)
 *         reroutes: number
 *         latency: number (milliseconds)
 *       }
 *     ],
 *     reroutes: [
 *       {
 *         from: string (node ID)
 *         to: string (node ID)
 *       }
 *     ]
 *   }
 * 
 * Features:
 * - Canvas rendering of nodes and edges
 * - Zoom and pan controls
 * - Hover tooltips
 * - Click to show detail panel
 */
export default function NetMap({ run, onPanelOpen }) {
  const canvasRef = useRef(null);
  const tipRef = useRef(null);
  const [loading, setLoading] = React.useState(true);
  const [hasData, setHasData] = React.useState(false);
  const stateRef = useRef({
    nodes: [],
    edges: [],
    reroutes: [],
    zoom: 1,
    panX: 0,
    panY: 0,
    time: 0,
    hoveredNode: null,
    hoveredEdge: null,
    selectedNode: null,
    selectedEdge: null,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    panStartX: 0,
    panStartY: 0,
  });
  const rafRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetchNetmap(run?.id)
      .then((d) => {
        if (!mounted) return;
        stateRef.current.nodes = d.nodes || [];
        stateRef.current.edges = d.edges || [];
        stateRef.current.reroutes = d.reroutes || [];
        setHasData((d.nodes || []).length > 0);
        setLoading(false);
        if ((d.nodes || []).length > 0) {
          startLoop();
        }
      })
      .catch(() => {
        if (mounted) {
          setHasData(false);
          setLoading(false);
        }
      });
    const canvas = canvasRef.current;
    if (!canvas) return;
    const tip = document.createElement("div");
    tip.className = "hover-tip";
    tip.style.display = "none";
    tip.id = "hoverTip";
    canvas.parentElement.appendChild(tip);
    tipRef.current = tip;
    
    const handleResize = () => resizeCanvas();
    window.addEventListener("resize", handleResize);
    
    handleResize(); // initialize 
    
    attachEvents();
    
    return () => {
      mounted = false;
      stopLoop();
      window.removeEventListener("resize", handleResize);
      detachEvents();
      if (tip && tip.parentElement) tip.parentElement.removeChild(tip);
    };
    // eslint-disable-next-line
  }, [run]);

  function resizeCanvas() {
    const area = canvasRef.current.parentElement;
    const canvas = canvasRef.current;
    const w = area.clientWidth,
      h = area.clientHeight;
    canvas.width = w * devicePixelRatio;
    canvas.height = h * devicePixelRatio;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  }

  function startLoop() {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    tick();
  }
  function stopLoop() {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  }
  function tick() {
    drawMap();
    rafRef.current = requestAnimationFrame(tick);
  }

  function nx(n) {
    const area = canvasRef.current.parentElement;
    const w = area.clientWidth;
    return (
      (n.x * w - w / 2) * stateRef.current.zoom + w / 2 + stateRef.current.panX
    );
  }
  function ny(n) {
    const area = canvasRef.current.parentElement;
    const h = area.clientHeight;
    return (
      (n.y * h - h / 2) * stateRef.current.zoom + h / 2 + stateRef.current.panY
    );
  }

  function congColor(c) {
    return c < 30
      ? { r: 0, g: 230, b: 138 }
      : c < 60
        ? { r: 255, g: 190, b: 46 }
        : { r: 255, g: 77, b: 106 };
  }
  function rgb(c, a = 1) {
    return `rgba(${c.r},${c.g},${c.b},${a})`;
  }

  function drawMap() {
    const s = stateRef.current;
    s.time += 0.016;
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    // Ensure canvas is properly sized
    if (canvas.width === 0 || canvas.height === 0) {
      resizeCanvas();
    }
    
    const ctx = canvas.getContext("2d");
    const w = canvas.clientWidth,
      h = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);
    // heat
    s.nodes.forEach((n) => {
      if (n.traffic > 50) {
        const g = ctx.createRadialGradient(
          nx(n),
          ny(n),
          0,
          nx(n),
          ny(n),
          (60 + n.traffic * 0.8) * s.zoom,
        );
        const c = congColor(n.traffic);
        g.addColorStop(0, rgb(c, 0.1 + Math.sin(s.time * 2) * 0.02));
        g.addColorStop(1, "transparent");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, w, h);
      }
    });
    // group rings
    s.nodes
      .filter((n) => n.role === "relay" && n.children)
      .forEach((relay) => {
        const children = relay.children
          .map((id) => s.nodes.find((x) => x.id === id))
          .filter(Boolean);
        if (!children.length) return;
        const all = [relay, ...children];
        let cx = 0,
          cy = 0;
        all.forEach((p) => {
          cx += nx(p);
          cy += ny(p);
        });
        cx /= all.length;
        cy /= all.length;
        let maxR = 0;
        all.forEach((p) => {
          const d = Math.hypot(nx(p) - cx, ny(p) - cy);
          if (d > maxR) maxR = d;
        });
        ctx.beginPath();
        ctx.arc(cx, cy, maxR + 30 * s.zoom, 0, Math.PI * 2);
        ctx.strokeStyle = nodeColor(relay) + "18";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = nodeColor(relay) + "06";
        ctx.fill();
      });
    // edges
    s.edges.forEach((e) => {
      const f = s.nodes.find((n) => n.id === e.from),
        t = s.nodes.find((n) => n.id === e.to);
      if (!f || !t) return;
      const x1 = nx(f),
        y1 = ny(f),
        x2 = nx(t),
        y2 = ny(t);
      const wgt = Math.max(1.5, (e.congestion / 100) * 7 * s.zoom);
      const c = congColor(e.congestion);
      const hl = s.hoveredEdge === e || s.selectedEdge === e;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = rgb(c, hl ? 0.9 : 0.5);
      ctx.lineWidth = hl ? wgt + 2 : wgt;
      ctx.lineCap = "round";
      ctx.stroke();
      const pc = Math.ceil(e.congestion / 25);
      for (let i = 0; i < pc; i++) {
        const p = (s.time * 0.3 + i / pc) % 1;
        ctx.beginPath();
        ctx.arc(
          x1 + (x2 - x1) * p,
          y1 + (y2 - y1) * p,
          1.5 * s.zoom,
          0,
          Math.PI * 2,
        );
        ctx.fillStyle = rgb(c, 0.6);
        ctx.fill();
      }
    });
    // reroutes
    s.reroutes.forEach((r) => {
      const f = s.nodes.find((n) => n.id === r.from),
        t = s.nodes.find((n) => n.id === r.to);
      if (!f || !t) return;
      ctx.beginPath();
      ctx.moveTo(nx(f), ny(f));
      ctx.lineTo(nx(t), ny(t));
      ctx.strokeStyle = "rgba(0,229,255,0.2)";
      ctx.lineWidth = 1.5 * s.zoom;
      ctx.setLineDash([8, 6]);
      ctx.stroke();
      ctx.setLineDash([]);
    });
    // nodes
    s.nodes.forEach((n) => {
      const x = nx(n),
        y = ny(n);
      const color = nodeColor(n);
      const hl = s.hoveredNode === n || s.selectedNode === n;
      const sz =
        (n.role === "command" ? 20 : n.role === "relay" ? 14 : 10) * s.zoom;
      if (n.health === "critical") {
        const pr = sz + 8 * s.zoom + Math.sin(s.time * 3) * 4 * s.zoom;
        ctx.beginPath();
        ctx.arc(x, y, pr, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255,77,106,${0.2 + Math.sin(s.time * 3) * 0.1})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      if (hl) {
        ctx.beginPath();
        ctx.arc(x, y, sz + 10 * s.zoom, 0, Math.PI * 2);
        ctx.fillStyle = color + "22";
        ctx.fill();
      }
      ctx.lineWidth = hl ? 2.5 : 1.8;
      if (n.role === "command") {
        ctx.beginPath();
        ctx.arc(x, y, sz, 0, Math.PI * 2);
        ctx.fillStyle = color + "25";
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y, sz * 0.35, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      } else if (n.role === "relay") {
        const hs = sz;
        ctx.beginPath();
        ctx.moveTo(x - hs, y - hs + 4);
        ctx.arcTo(x - hs, y - hs, x - hs + 4, y - hs, 4);
        ctx.arcTo(x + hs, y - hs, x + hs, y - hs + 4, 4);
        ctx.arcTo(x + hs, y + hs, x + hs - 4, y + hs, 4);
        ctx.arcTo(x - hs, y + hs, x - hs, y + hs - 4, 4);
        ctx.closePath();
        ctx.fillStyle = color + "20";
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y, 3 * s.zoom, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      } else {
        const h = sz * 1.15;
        ctx.beginPath();
        ctx.moveTo(x, y - h);
        ctx.lineTo(x + sz, y + h * 0.6);
        ctx.lineTo(x - sz, y + h * 0.6);
        ctx.closePath();
        ctx.fillStyle = color + "20";
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y + h * 0.05, 2.5 * s.zoom, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      }
      ctx.font = `${n.role === "command" ? 600 : 500} ${(n.role === "command" ? 10 : 9) * s.zoom}px "JetBrains Mono"`;
      ctx.fillStyle = "rgba(228,234,244,0.85)";
      ctx.textAlign = "center";
      ctx.fillText(n.id, x, y + sz + 12 * s.zoom);
      if (n.role !== "command") {
        const bw = 18 * s.zoom,
          bh = 3 * s.zoom,
          bx = x - bw / 2,
          by = y + sz + 16 * s.zoom;
        ctx.fillStyle = "rgba(255,255,255,0.06)";
        ctx.fillRect(bx, by, bw, bh);
        ctx.fillStyle =
          n.battery > 60 ? "#00e68a" : n.battery > 30 ? "#ffbe2e" : "#ff4d6a";
        ctx.fillRect(bx, by, bw * (n.battery / 100), bh);
      }
    });
  }

  function nodeColor(n) {
    return n.role === "command"
      ? "#00e5ff"
      : n.role === "relay"
        ? "#a78bfa"
        : "#00e68a";
  }

  function attachEvents() {
    const canvas = canvasRef.current;
    canvas.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("click", onClick);
  }
  function detachEvents() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.removeEventListener("mousedown", onMouseDown);
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
    canvas.removeEventListener("wheel", onWheel);
    canvas.removeEventListener("click", onClick);
  }

  function onMouseDown(e) {
    const s = stateRef.current;
    if (e.button === 0 && !s.hoveredNode && !s.hoveredEdge) {
      s.isDragging = true;
      s.dragStartX = e.clientX;
      s.dragStartY = e.clientY;
      s.panStartX = s.panX;
      s.panStartY = s.panY;
      canvasRef.current.style.cursor = "grabbing";
    }
  }
  function onMouseMove(e) {
    const s = stateRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left,
      my = e.clientY - rect.top;
    if (s.isDragging) {
      s.panX = s.panStartX + (e.clientX - s.dragStartX);
      s.panY = s.panStartY + (e.clientY - s.dragStartY);
      return;
    }
    // hover detection
    s.hoveredNode = null;
    s.hoveredEdge = null;
    for (const n of s.nodes) {
      const dx = mx - nx(n),
        dy = my - ny(n);
      const r =
        (n.role === "command" ? 24 : n.role === "relay" ? 18 : 14) * s.zoom;
      if (dx * dx + dy * dy < r * r) {
        s.hoveredNode = n;
        canvas.style.cursor = "pointer";
        showTipForNode(n, mx, my);
        return;
      }
    }
    for (const ed of s.edges) {
      const f = s.nodes.find((n) => n.id === ed.from),
        t = s.nodes.find((n) => n.id === ed.to);
      if (!f || !t) continue;
      if (distToSeg(mx, my, nx(f), ny(f), nx(t), ny(t)) < 8 * s.zoom) {
        s.hoveredEdge = ed;
        canvas.style.cursor = "pointer";
        showTipForEdge(ed, mx, my);
        return;
      }
    }
    canvas.style.cursor = s.isDragging ? "grabbing" : "grab";
    hideTip();
  }

  function onMouseUp() {
    const s = stateRef.current;
    s.isDragging = false;
    if (canvasRef.current) canvasRef.current.style.cursor = "grab";
  }
  function onWheel(e) {
    e.preventDefault();
    const s = stateRef.current;
    s.zoom = Math.max(0.5, Math.min(3, s.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
  }
  function onClick() {
    const s = stateRef.current;
    if (s.hoveredNode) {
      showNodePanel(s.hoveredNode);
    } else if (s.hoveredEdge) {
      showEdgePanel(s.hoveredEdge);
    }
  }

  function zoomIn() {
    stateRef.current.zoom = Math.max(0.5, Math.min(3, stateRef.current.zoom * 1.2));
  }
  function zoomOut() {
    stateRef.current.zoom = Math.max(0.5, Math.min(3, stateRef.current.zoom * 0.8));
  }
  function recenter() {
    stateRef.current.zoom = 1;
    stateRef.current.panX = 0;
    stateRef.current.panY = 0;
  }

  function getNetworkOverview() {
    const s = stateRef.current;
    const congestionScore = Math.round((s.edges.reduce((sum, e) => sum + e.congestion, 0) / s.edges.length) || 0);
    const avgLatency = Math.round((s.edges.reduce((sum, e) => sum + e.avgDelay, 0) / s.edges.length) || 0);
    const packetLoss = (s.edges.reduce((sum, e) => sum + e.packetLoss, 0) / s.edges.length).toFixed(1);
    const activeNodes = s.nodes.length;
    const rerouteCount = s.reroutes.length;
    return { congestionScore, avgLatency, packetLoss, activeNodes, rerouteCount };
  }

  function getColorClass(value, type = 'congestion') {
    if (type === 'congestion') return value < 40 ? 'good' : value < 70 ? 'warn' : 'bad';
    if (type === 'latency') return value < 50 ? 'good' : value < 100 ? 'warn' : 'bad';
    if (type === 'packetloss') return parseFloat(value) < 2 ? 'good' : parseFloat(value) < 5 ? 'warn' : 'bad';
    return 'good';
  }

  function showTipForNode(n, mx, my) {
    const tip = tipRef.current;
    if (!tip) return;
    tip.innerHTML = `<div class="tt-title" style="color:${nodeColor(n)}">${n.id} — ${n.label.replace("\n", " ")}</div><div class="tt-row"><span class="tt-label">Battery</span><span class="tt-val" style="color:${n.battery > 60 ? "var(--green)" : n.battery > 30 ? "var(--amber)" : "var(--red)"}">${n.battery}%</span></div><div class="tt-row"><span class="tt-label">Traffic</span><span class="tt-val">${n.traffic}%</span></div><div class="tt-row"><span class="tt-label">AI Detections</span><span class="tt-val">${n.aiDet}</span></div><div style="font-size:9px;color:var(--text-muted);margin-top:4px;">Click for details</div>`;
    tip.style.display = "block";
    tip.style.left = mx + 16 + "px";
    tip.style.top = my - 10 + "px";
  }
  function showTipForEdge(e, mx, my) {
    const tip = tipRef.current;
    if (!tip) return;
    tip.innerHTML = `<div class="tt-title">${e.from} ↔ ${e.to}</div><div class="tt-row"><span class="tt-label">Congestion</span><span class="tt-val" style="color:${rgb(congColor(e.congestion))}">${e.congestion}%</span></div><div class="tt-row"><span class="tt-label">Packet Loss</span><span class="tt-val">${e.packetLoss}%</span></div><div class="tt-row"><span class="tt-label">Avg Delay</span><span class="tt-val">${e.avgDelay}ms</span></div><div style="font-size:9px;color:var(--text-muted);margin-top:4px;">Click for details</div>`;
    tip.style.display = "block";
    tip.style.left = mx + 16 + "px";
    tip.style.top = my - 10 + "px";
  }
  function hideTip() {
    const tip = tipRef.current;
    if (tip) tip.style.display = "none";
  }

  function distToSeg(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1,
      dy = y2 - y1,
      ls = dx * dx + dy * dy;
    let t =
      ls === 0
        ? 0
        : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / ls));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }

  function showNodePanel(n) {
    const p = document.getElementById("detailPanel");
    if (!p) return;
    document.getElementById("app").classList.add("panel-open");
    const c = nodeColor(n);
    const bc =
      n.battery > 60
        ? "var(--green)"
        : n.battery > 30
          ? "var(--amber)"
          : "var(--red)";
    p.innerHTML = `<div class="dp-header"><div><div class="dp-title" style="color:${c}">${n.id} — ${n.label.replace("\n", " ")}</div><div class="dp-subtitle">${n.role === "command" ? "Command Center" : n.role === "relay" ? "Shaman II (Relay)" : "Shaman I (Sensor)"}</div></div><div class="dp-close" onclick="document.getElementById('app').classList.remove('panel-open')">✕</div></div><div class="dp-section"><div class="dp-section-title">Status</div><div class="dp-row"><span class="dp-row-l">Health</span><span class="dp-row-v" style="color:${n.health === "good" ? "var(--green)" : n.health === "warning" ? "var(--amber)" : "var(--red)"}">${(n.health || "").toUpperCase()}</span></div><div class="dp-row"><span class="dp-row-l">Battery</span><span class="dp-row-v" style="color:${bc}">${n.battery}%</span></div></div>`;
  }

  function showEdgePanel(e) {
    const p = document.getElementById("detailPanel");
    if (!p) return;
    document.getElementById("app").classList.add("panel-open");
    p.innerHTML = `<div class="dp-header"><div><div class="dp-title">${e.from} ↔ ${e.to}</div><div class="dp-subtitle">Link Detail</div></div><div class="dp-close" onclick="document.getElementById('app').classList.remove('panel-open')">✕</div></div><div class="dp-section"><div class="dp-section-title">Link Metrics</div><div class="dp-row"><span class="dp-row-l">Congestion</span><span class="dp-row-v">${e.congestion}%</span></div><div class="dp-row"><span class="dp-row-l">Packet Loss</span><span class="dp-row-v">${e.packetLoss}%</span></div></div>`;
  }

  return (
    <div
      style={{ position: "relative", width: "100%", height: "100%" }}
      id="pageNetMap"
    >
      {!loading && !hasData && (
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            textAlign: "center",
            zIndex: 10,
          }}
        >
          <div style={{ fontSize: 24, fontWeight: 600, marginBottom: 8, color: "rgba(228,234,244,0.6)" }}>
            No Network Map Found
          </div>
          <div style={{ fontSize: 14, color: "rgba(228,234,244,0.4)" }}>
            {run ? "This run does not have network topology data" : "Select a run to view its network map"}
          </div>
        </div>
      )}

      <canvas
        id="netCanvas"
        ref={canvasRef}
        style={{ width: "100%", height: "100%", cursor: "grab", display: hasData ? "block" : "none" }}
      ></canvas>

      {/* Network Overview (top-left) */}
      {hasData && (
        <div className="map-ov top-left">
          <div className="ov-title">Network Overview</div>
          {(() => {
            const overview = getNetworkOverview();
            return (
              <>
                <div className="ov-row">
                  <span className="ov-label">Congestion Score
                    <span className="help-icon" style={{position:'relative',top:'-1px'}}>?
                      <span className="help-tip">Aggregate network congestion metric (0-100). Calculation will be refined with Mech/AI input.</span>
                    </span>
                  </span>
                  <span className={`ov-val ${getColorClass(overview.congestionScore, 'congestion')}`}>{overview.congestionScore}/100</span>
                </div>
                <div className="ov-row">
                  <span className="ov-label">Avg Latency</span>
                  <span className={`ov-val ${getColorClass(overview.avgLatency, 'latency')}`}>{overview.avgLatency}ms</span>
                </div>
                <div className="ov-row">
                  <span className="ov-label">Packet Loss</span>
                  <span className={`ov-val ${getColorClass(overview.packetLoss, 'packetloss')}`}>{overview.packetLoss}%</span>
                </div>
                <div className="ov-row">
                  <span className="ov-label">Active Nodes</span>
                  <span className="ov-val good">{overview.activeNodes} / {overview.activeNodes}</span>
                </div>
                <div className="ov-row">
                  <span className="ov-label">Reroute Events</span>
                  <span className={`ov-val ${overview.rerouteCount > 5 ? 'warn' : 'good'}`}>{overview.rerouteCount}</span>
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* Zoom controls (top-right) */}
      {hasData && (
        <div className="map-zoom">
          <button className="zoom-btn" onClick={zoomIn} title="Zoom In">+</button>
          <button className="zoom-btn" onClick={zoomOut} title="Zoom Out">−</button>
          <button className="zoom-btn recenter" onClick={recenter} title="Recenter">⌖</button>
        </div>
      )}

      {/* Legend (bottom-left) */}
      {hasData && (
        <div className="map-ov bottom-left">
          <div className="ov-title">Legend</div>
          <div className="legend-row">
            <div className="legend-swatch" style={{background:'#00e5ff',borderColor:'#00e5ff',width:'14px',height:'14px'}}></div>
            <span> Command Center</span>
          </div>
          <div className="legend-row">
            <svg width="14" height="14" viewBox="0 0 14 14" style={{flexShrink:0}}>
              <rect x="1" y="1" width="12" height="12" rx="3" fill="rgba(167,139,250,0.2)" stroke="#a78bfa" strokeWidth="1.5"></rect>
            </svg>
            <span> Shaman II (Relay)</span>
          </div>
          <div className="legend-row">
            <svg width="14" height="14" viewBox="0 0 14 14" style={{flexShrink:0}}>
              <polygon points="7,1 13,13 1,13" fill="rgba(0,230,138,0.2)" stroke="#00e68a" strokeWidth="1.5"></polygon>
            </svg>
            <span> Shaman I (Sensor)</span>
          </div>
          <div className="legend-row">
            <div className="legend-line" style={{background:'var(--green)'}}></div>
            <span>Low congestion</span>
          </div>
          <div className="legend-row">
            <div className="legend-line" style={{background:'var(--amber)'}}></div>
            <span>Medium</span>
          </div>
          <div className="legend-row">
            <div className="legend-line" style={{background:'var(--red)'}}></div>
            <span>High congestion</span>
          </div>
        </div>
      )}
    </div>
  );
}
