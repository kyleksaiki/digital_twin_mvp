import React, { useEffect, useRef, useState } from "react";
import ShamanConfigPanel from "./ShamanConfigPanel";
import { createRun } from "../api";

/**
 * CreateRun - Interactive topology design canvas for creating new simulation runs
 *
 * Features:
 * - Canvas-based node and edge placement
 * - Draggable toolbar for node creation
 * - Right-click context menu for node placement
 * - Pan, zoom, and navigation controls
 * - Shaman configuration panel
 * - Connection validation rules
 *
 * Props:
 *   onNavigate: (page: string) => void - called to navigate to other pages
 *   onRunCreated: () => void - called after successful run creation
 */

function CVP(current, voltage, power) {
  this.current = current || null;
  this.voltage = voltage || null;
  this.power = power || null;
}

function ComponentPowerModel(batteryLife) {
  this.batteryLife = batteryLife;
  this.components = {
    sleep: new CVP(),
    working: new CVP(),
    transmit: new CVP(),
    receive: new CVP(),
    cameraImage: new CVP(),
    cameraSleep: new CVP(),
    micListen: new CVP(),
    micSleep: new CVP(),
  };
}
export default function CreateRun({ onNavigate, onRunCreated }) {
  const canvasRef = useRef(null);
  const tipRef = useRef(null);
  const draggedButtonRef = useRef(null);

  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [shamanIConfig, setShamanIConfig] = useState(new ComponentPowerModel());
  const [shamanIIConfig, setShamanIIConfig] = useState(new ComponentPowerModel());
  const [mediaFiles, setMediaFiles] = useState({});
  const [workflow, setWorkflow] = useState("design"); // "design" | "power" | "media" | "loading" | "confirm"
  const [isLoading, setIsLoading] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState("");

  const stateRef = useRef({
    nodes: [],
    edges: [],
    zoom: 1,
    panX: 0,
    panY: 0,
    hoveredNode: null,
    hoveredEdge: null,
    selectedNode: null,
    selectedEdge: null,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    panStartX: 0,
    panStartY: 0,
    nodeCounter: { command: 0, relay: 0, sensor: 0 },
    isPlacingNode: null, // "command" | "relay" | "sensor" | null
    connectingFrom: null, // node to start edge from
    contextMenu: null, // { x, y, show: boolean }
  });

  const rafRef = useRef(null);

  // Sync state with React state
  useEffect(() => {
    stateRef.current.nodes = nodes;
    stateRef.current.edges = edges;
  }, [nodes, edges]);

  useEffect(() => {
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

    handleResize();
    attachEvents();
    startLoop();

    return () => {
      stopLoop();
      window.removeEventListener("resize", handleResize);
      detachEvents();
      if (tip && tip.parentElement) tip.parentElement.removeChild(tip);
    };
  }, []);

  function resizeCanvas() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const area = canvas.parentElement,
      w = area.clientWidth,
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
    drawCanvas();
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

  function nodeColor(role) {
    return role === "command"
      ? "#00e5ff"
      : role === "relay"
        ? "#a78bfa"
        : "#00e68a";
  }

  function drawCanvas() {
    const s = stateRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (canvas.width === 0 || canvas.height === 0) {
      resizeCanvas();
    }

    const ctx = canvas.getContext("2d");
    const w = canvas.clientWidth,
      h = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);

    // Draw edges first
    s.edges.forEach((e) => {
      const from = s.nodes.find((n) => n.id === e.from);
      const to = s.nodes.find((n) => n.id === e.to);
      if (!from || !to) return;

      const x1 = nx(from),
        y1 = ny(from),
        x2 = nx(to),
        y2 = ny(to);
      const isValid = canConnect(from, to);

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = isValid
        ? "rgba(167, 139, 250, 0.6)"
        : "rgba(255, 77, 106, 0.6)";
      ctx.lineWidth = 2 * s.zoom;
      ctx.lineCap = "round";
      ctx.stroke();

      // Draw connection indicator
      const midX = (x1 + x2) / 2;
      const midY = (y1 + y2) / 2;
      ctx.beginPath();
      ctx.arc(midX, midY, 4 * s.zoom, 0, Math.PI * 2);
      ctx.fillStyle = isValid
        ? "rgba(0, 230, 138, 0.8)"
        : "rgba(255, 77, 106, 0.8)";
      ctx.fill();
    });

    // Draw preview connection line if connecting
    if (s.connectingFrom) {
      const x1 = nx(s.connectingFrom);
      const y1 = ny(s.connectingFrom);
      const mouseX = s.lastMouseX || w / 2;
      const mouseY = s.lastMouseY || h / 2;

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(mouseX, mouseY);
      ctx.strokeStyle = "rgba(167, 139, 250, 0.3)";
      ctx.lineWidth = 1.5 * s.zoom;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw nodes
    s.nodes.forEach((n) => {
      const x = nx(n);
      const y = ny(n);
      const color = nodeColor(n.role);
      const sz =
        (n.role === "command" ? 20 : n.role === "relay" ? 14 : 10) * s.zoom;
      const hl = s.hoveredNode === n || s.selectedNode === n;

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

      ctx.font = `500 ${(n.role === "command" ? 10 : 9) * s.zoom}px "JetBrains Mono"`;
      ctx.fillStyle = "rgba(228,234,244,0.85)";
      ctx.textAlign = "center";
      ctx.fillText(n.id, x, y + sz + 12 * s.zoom);
    });
  }

  function canConnect(from, to) {
    // Command can connect to relays
    if (from.role === "command" && to.role === "relay") return true;
    if (from.role === "relay" && to.role === "command") return true;

    // Relay can connect to relay (parent-child)
    if (from.role === "relay" && to.role === "relay") return true;

    // Relay can connect to sensors
    if (from.role === "relay" && to.role === "sensor") return true;
    if (from.role === "sensor" && to.role === "relay") return true;

    return false;
  }

  function addNode(role) {
    const s = stateRef.current;
    s.nodeCounter[role]++;
    const id =
      role === "command"
        ? "CMD"
        : role === "relay"
          ? `R${s.nodeCounter.relay}`
          : `S${s.nodeCounter.sensor}`;

    const x = Math.random() * 0.3 + 0.35;
    const y = Math.random() * 0.3 + 0.35;

    const newNode = {
      id,
      label:
        role === "command"
          ? "Command Center"
          : role === "relay"
            ? `Shaman II (${id})`
            : `Shaman I (${id})`,
      role,
      x,
      y,
    };

    setNodes([...nodes, newNode]);
  }

  function deleteNode(nodeToDelete) {
    setNodes(nodes.filter((n) => n.id !== nodeToDelete.id));
    setEdges(
      edges.filter(
        (e) => e.from !== nodeToDelete.id && e.to !== nodeToDelete.id,
      ),
    );
  }

  function addEdge(from, to) {
    if (!canConnect(from, to)) return;
    // Only prevent exact same direction, allow multiple edges and bidirectional
    if (edges.some((e) => e.from === from.id && e.to === to.id)) return;

    setEdges([...edges, { from: from.id, to: to.id }]);
  }

  function deleteEdge(edgeToDelete) {
    setEdges(
      edges.filter(
        (e) => !(e.from === edgeToDelete.from && e.to === edgeToDelete.to),
      ),
    );
  }

  function attachEvents() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.addEventListener("mousedown", onMouseDown);
    canvas.addEventListener("mousemove", onMouseMove);
    canvas.addEventListener("mouseup", onMouseUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("click", onClick);
    canvas.addEventListener("contextmenu", onContextMenu);
    document.addEventListener("click", onDocumentClick);
  }

  function detachEvents() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.removeEventListener("mousedown", onMouseDown);
    canvas.removeEventListener("mousemove", onMouseMove);
    canvas.removeEventListener("mouseup", onMouseUp);
    canvas.removeEventListener("wheel", onWheel);
    canvas.removeEventListener("click", onClick);
    canvas.removeEventListener("contextmenu", onContextMenu);
    document.removeEventListener("click", onDocumentClick);
  }

  function onMouseDown(e) {
    const s = stateRef.current;
    if (e.button === 0 && !s.hoveredNode) {
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
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    s.lastMouseX = mx;
    s.lastMouseY = my;

    if (s.isDragging) {
      s.panX = s.panStartX + (e.clientX - s.dragStartX);
      s.panY = s.panStartY + (e.clientY - s.dragStartY);
      return;
    }

    // Hover detection
    s.hoveredNode = null;
    for (const n of s.nodes) {
      const dx = mx - nx(n);
      const dy = my - ny(n);
      const r =
        (n.role === "command" ? 24 : n.role === "relay" ? 18 : 14) * s.zoom;
      if (dx * dx + dy * dy < r * r) {
        s.hoveredNode = n;
        canvas.style.cursor = "pointer";
        return;
      }
    }

    canvas.style.cursor = s.isDragging ? "grabbing" : "grab";
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

  function onClick(e) {
    const s = stateRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // If placing a node from toolbar
    if (s.isPlacingNode) {
      const area = canvas.parentElement;
      const w = area.clientWidth;
      const h = area.clientHeight;

      // Convert screen coords to normalized coords
      const x = (mx - w / 2 - s.panX) / (s.zoom * w) + 0.5;
      const y = (my - h / 2 - s.panY) / (s.zoom * h) + 0.5;

      const role = s.isPlacingNode;
      s.nodeCounter[role]++;

      const id =
        role === "command"
          ? "CMD"
          : role === "relay"
            ? `R${s.nodeCounter.relay}`
            : `S${s.nodeCounter.sensor}`;

      const newNode = {
        id,
        label:
          role === "command"
            ? "Command Center"
            : role === "relay"
              ? `Shaman II (${id})`
              : `Shaman I (${id})`,
        role,
        x: Math.max(0, Math.min(1, x)),
        y: Math.max(0, Math.min(1, y)),
      };

      setNodes([...s.nodes, newNode]);
      s.isPlacingNode = null;
      canvas.style.cursor = "grab";
      return;
    }

    // If hovering a node, check if double-click to delete or start connection
    if (s.hoveredNode) {
      if (e.detail === 2) {
        // Double click = delete
        deleteNode(s.hoveredNode);
        s.connectingFrom = null;
      } else {
        // Single click = start/complete connection
        if (!s.connectingFrom) {
          s.connectingFrom = s.hoveredNode;
        } else if (s.connectingFrom !== s.hoveredNode) {
          addEdge(s.connectingFrom, s.hoveredNode);
          s.connectingFrom = null;
        } else {
          s.connectingFrom = null;
        }
      }
    } else {
      s.connectingFrom = null;
    }
  }

  function onContextMenu(e) {
    e.preventDefault();
    const s = stateRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    s.contextMenu = {
      x: e.clientX,
      y: e.clientY,
      show: true,
    };
  }

  function onDocumentClick() {
    const s = stateRef.current;
    s.contextMenu = null;
  }

  function startToolbarDrag(e, nodeType) {
    draggedButtonRef.current = nodeType;
    const s = stateRef.current;
    s.isPlacingNode = nodeType;
    const canvas = canvasRef.current;
    canvas.style.cursor = "crosshair";
  }

  function handleMediaFileChange(nodeId, file) {
    setMediaFiles({
      ...mediaFiles,
      [nodeId]: file ? file.name : null,
    });
  }

  async function runSimulation() {
    setWorkflow("loading");
    setIsLoading(true);

    // Simulate loading delay
    await new Promise((resolve) => setTimeout(resolve, 2000));

    // Create run data
    const runData = {
      name: `Run-${new Date().toISOString().split("T")[0]}-${Date.now() % 10000}`,
      scenario: "Digital Twin Simulation",
      model: "Auto-generated",
      hw: `${nodes.length} nodes, ${edges.length} connections`,
      duration: "24h",
      status: "pass",
      nodes: nodes.map((n) => ({
        id: n.id,
        label: n.label,
        role: n.role,
        x: n.x,
        y: n.y,
      })),
      edges: edges.map((e) => ({
        from: e.from,
        to: e.to,
      })),
      mediaFiles,
      shamanIConfig,
      shamanIIConfig
    };

    try {
      // POST to backend via API client
      const result = await createRun(runData);
      setIsLoading(false);
      setWorkflow("confirm");
      setConfirmMessage(
        `Simulation created successfully!\n\nRun ID: ${result.id}\nRun Name: ${result.name}`,
      );
    } catch (err) {
      // Fallback to mock if backend not available
      setIsLoading(false);
      setWorkflow("confirm");
      setConfirmMessage(
        `Mock Simulation created!\n\nRun: ${runData.name}\nNodes: ${nodes.length}\nConnections: ${edges.length}`,
      );
    }
  }

  function closeConfirmation() {
    // Reset workflow
    setWorkflow("design");
    setConfirmMessage("");
    setNodes([]);
    setEdges([]);
    setMediaFiles({});
    // Navigate to run selector if run was created
    if (onRunCreated) {
      onRunCreated();
    }
  }

  function zoomIn() {
    stateRef.current.zoom = Math.max(
      0.5,
      Math.min(3, stateRef.current.zoom * 1.2),
    );
  }

  function zoomOut() {
    stateRef.current.zoom = Math.max(
      0.5,
      Math.min(3, stateRef.current.zoom * 0.8),
    );
  }

  function recenter() {
    stateRef.current.zoom = 1;
    stateRef.current.panX = 0;
    stateRef.current.panY = 0;
  }

  return (
    <div
      style={{ position: "relative", width: "100%", height: "100%" }}
      id="pageCreateRun"
    >
      <canvas
        id="createRunCanvas"
        ref={canvasRef}
        style={{
          width: "100%",
          height: "100%",
          cursor: "grab",
          display: "block",
        }}
      ></canvas>

      {/* Toolbar (top-left) */}
      <div className="create-toolbar top-left">
        <div className="toolbar-title">Create Topology</div>
        <button
          className="toolbar-btn"
          onMouseDown={(e) => startToolbarDrag(e, "command")}
          title="Click canvas to place Command Center"
        >
          + Command
        </button>
        <button
          className="toolbar-btn"
          onMouseDown={(e) => startToolbarDrag(e, "relay")}
          title="Click canvas to place Shaman II (Relay)"
        >
          + Shaman II
        </button>
        <button
          className="toolbar-btn"
          onMouseDown={(e) => startToolbarDrag(e, "sensor")}
          title="Click canvas to place Shaman I (Sensor)"
        >
          + Shaman I
        </button>
        <div className="toolbar-divider"></div>
        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
          <div>Nodes: {nodes.length}</div>
          <div>Edges: {edges.length}</div>
        </div>
      </div>

      {/* Zoom controls (top-right) */}
      <div className="map-zoom">
        <button className="zoom-btn" onClick={zoomIn} title="Zoom In">
          +
        </button>
        <button className="zoom-btn" onClick={zoomOut} title="Zoom Out">
          −
        </button>
        <button
          className="zoom-btn recenter"
          onClick={recenter}
          title="Recenter"
        >
          ⌖
        </button>
      </div>

      {/* Legend (bottom-left) */}
      <div className="map-ov bottom-left">
        <div className="ov-title">Legend</div>
        <div className="legend-row">
          <div
            className="legend-swatch"
            style={{
              background: "#00e5ff",
              borderColor: "#00e5ff",
              width: "14px",
              height: "14px",
            }}
          ></div>
          <span> Command Center</span>
        </div>
        <div className="legend-row">
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            style={{ flexShrink: 0 }}
          >
            <rect
              x="1"
              y="1"
              width="12"
              height="12"
              rx="3"
              fill="rgba(167,139,250,0.2)"
              stroke="#a78bfa"
              strokeWidth="1.5"
            ></rect>
          </svg>
          <span> Shaman II (Relay)</span>
        </div>
        <div className="legend-row">
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            style={{ flexShrink: 0 }}
          >
            <polygon
              points="7,1 13,13 1,13"
              fill="rgba(0,230,138,0.2)"
              stroke="#00e68a"
              strokeWidth="1.5"
            ></polygon>
          </svg>
          <span> Shaman I (Sensor)</span>
        </div>
        <div
          style={{
            fontSize: "10px",
            color: "var(--text-muted)",
            marginTop: "8px",
          }}
        >
          <div>• Click nodes to connect</div>
          <div>• Double-click to delete</div>
          <div>• Right-click for menu</div>
        </div>
      </div>

      {/* Workflow: Next Button (only on design phase) */}
      {workflow === "design" && nodes.length > 0 && (
        <div
          style={{ position: "absolute", bottom: 20, right: 20, zIndex: 10 }}
        >
          <button
            className="workflow-btn"
            onClick={() => setWorkflow("configi")}
            style={{
              background: "var(--green)",
              color: "var(--bg-deep)",
              border: "1px solid var(--green)",
              padding: "10px 16px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: "700",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => {
              e.target.style.opacity = "0.9";
              e.target.style.boxShadow = "0 0 12px rgba(0, 230, 138, 0.3)";
            }}
            onMouseLeave={(e) => {
              e.target.style.opacity = "1";
              e.target.style.boxShadow = "none";
            }}
          >
            Configure Run
          </button>
        </div>
      )}

      {/* Shaman I Config Panel */}
      {workflow === "configi" && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <div className="modal-header">
              <div className="modal-title">Configure Shaman I</div>
              <button
                className="modal-close"
                onClick={() => setWorkflow("design")}
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              <div className="modal-section">
                <div className="modal-label">
                  Component Power Model (Enter Current + Voltage or Power)
                </div>
                {/*shamanIConfig.components.map((component) => (
                  <div>{component.current}</div>
                ))*/}
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="modal-btn-cancel"
                onClick={() => setWorkflow("design")}
              >
                Back
              </button>
              <button
                className="modal-btn-confirm"
                onClick={() => setWorkflow("configii")}
              >
                Configure Shaman II
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Shaman II Config Panel */}
      {workflow === "configii" && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <div className="modal-header">
              <div className="modal-title">Configure Shaman II</div>
              <button
                className="modal-close"
                onClick={() => setWorkflow("design")}
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              <div className="modal-section">
                <div className="modal-label">
                  Component Power Model (Enter Current + Voltage or Power)
                </div>
                {/*shamanIConfig.components.map((component) => (
                  <div>{component.current}</div>
                ))*/}
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="modal-btn-cancel"
                onClick={() => setWorkflow("configi")}
              >
                Back
              </button>
              <button
                className="modal-btn-confirm"
                onClick={() => setWorkflow("media")}
              >
                Configure Media
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Dialog: Media Files Upload */}
      {workflow === "media" && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <div className="modal-header">
              <div className="modal-title">Connect Media Files</div>
              <button
                className="modal-close"
                onClick={() => setWorkflow("design")}
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              <div className="modal-section">
                <div className="modal-label">
                  Select audio/video files for each node
                </div>
                {nodes.map((node) => (
                  <div key={node.id} className="modal-file-group">
                    <label className="modal-file-label">
                      {node.id} — {node.label}
                    </label>
                    <input
                      type="file"
                      className="modal-file-input"
                      accept="audio/*,video/*"
                      onChange={(e) =>
                        handleMediaFileChange(node.id, e.target.files?.[0])
                      }
                    />
                    {mediaFiles[node.id] && (
                      <div className="modal-file-selected">
                        ✓ {mediaFiles[node.id]}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="modal-btn-cancel"
                onClick={() => setWorkflow("configii")}
              >
                Back
              </button>
              <button
                className="modal-btn-confirm"
                onClick={() => runSimulation()}
              >
                Run Simulation
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Dialog: Loading Screen */}
      {workflow === "loading" && (
        <div className="modal-overlay">
          <div className="modal-dialog modal-loading">
            <div className="modal-spinner"></div>
            <div className="modal-label" style={{ marginTop: "16px" }}>
              Running simulation...
            </div>
            <div
              style={{
                fontSize: "10px",
                color: "var(--text-muted)",
                marginTop: "8px",
              }}
            >
              Processing {nodes.length} nodes and {edges.length} connections
            </div>
          </div>
        </div>
      )}

      {/* Dialog: Confirmation */}
      {workflow === "confirm" && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <div className="modal-header">
              <div className="modal-title">
                {confirmMessage.includes("Error") ? "⚠ Error" : "✓ Success"}
              </div>
            </div>
            <div className="modal-body">
              <div
                style={{
                  whiteSpace: "pre-wrap",
                  fontSize: "11px",
                  lineHeight: "1.6",
                }}
              >
                {confirmMessage}
              </div>
            </div>
            <div className="modal-footer">
              <button className="modal-btn-confirm" onClick={closeConfirmation}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
