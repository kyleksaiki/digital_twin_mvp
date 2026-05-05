import React, { useEffect, useRef, useState } from "react";
import { createRun } from "../api";
import {
  OSA_MAP_BOUNDS,
  formatLatLonDMS,
  latLonToNormalized,
  normalizedToLatLon,
} from "../utils/coordinates";
import ModalStepper from "./common/ModalStepper";
import useStepNavigator from "../hooks/useStepNavigator";

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
 * - Calibration system for real-world coordinates
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

function ComponentPowerModel(batteryLife, components, isShamanII = false) {
  this.batteryLife = batteryLife;
  this.components =
    components ||
    (isShamanII
      ? {
          sleep: new CVP(),
          working: new CVP(),
          transmit: new CVP(),
          receive: new CVP(),
        }
      : {
          sleep: new CVP(),
          working: new CVP(),
          transmit: new CVP(),
          receive: new CVP(),
          cameraImage: new CVP(),
          cameraSleep: new CVP(),
          micListen: new CVP(),
          micSleep: new CVP(),
        });
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

const formatFieldLabel = (value) =>
  value.replace(/_/g, " ").replace(/\s+/g, " ").trim();

const STAGE1_FIELDS = [
  {
    key: "target_sample_rate",
    label: "Target Sample Rate (Hz)",
    type: "number",
    step: "1",
    defaultValue: 48000,
  },
  {
    key: "block_seconds",
    label: "Block Seconds",
    type: "number",
    step: "1",
    defaultValue: 60,
  },
  {
    key: "clip_s",
    label: "Clip Duration (s)",
    type: "number",
    step: "0.1",
    defaultValue: 3.0,
  },
  {
    key: "rms_z_thresh",
    label: "RMS Z Threshold",
    type: "number",
    step: "0.1",
    defaultValue: 1.2,
  },
  {
    key: "centroid_hz_thresh",
    label: "Centroid Threshold (Hz)",
    type: "number",
    step: "1",
    defaultValue: 1400,
  },
  {
    key: "bandwidth_hz_thresh",
    label: "Bandwidth Threshold (Hz)",
    type: "number",
    step: "1",
    defaultValue: 700,
  },
  {
    key: "snr_db_thresh",
    label: "SNR Threshold (dB)",
    type: "number",
    step: "0.1",
    defaultValue: 4.0,
  },
  {
    key: "min_gap_s",
    label: "Min Gap (s)",
    type: "number",
    step: "0.1",
    defaultValue: 1.5,
  },
];

const STAGE1_DEFAULTS = STAGE1_FIELDS.reduce((acc, field) => {
  acc[field.key] = field.defaultValue ?? "";
  return acc;
}, {});

const STAGE4_SENTINEL_KEYS = [
  "Myiothlypis fulvicauda_Buff-rumped Warbler",
  "Habia atrimaxillaris_Black-cheeked Ant-Tanager",
  "Thamnophilus bridgesi_Black-hooded Antshrike",
  "Tinamus major_Great Tinamou",
  "Patagioenas nigrirostris_Short-billed Pigeon",
  "Ramphastos ambiguus_Yellow-throated Toucan",
  "Cyanoloxia cyanoides_Blue-black Grosbeak",
  "Lipaugus unirufus_Rufous Piha",
  "Threnetes ruckeri_Band-tailed Barbthroat",
  "Ara macao_Scarlet Macaw",
];

const STAGE4_GROUPS = [
  {
    title: "Clip Metadata",
    fields: [
      {
        key: "clip_name",
        label: "Clip Name or Window ID",
        type: "text",
        placeholder: "node_01_2026-05-05_001",
      },
      {
        key: "Recorder",
        label: "Recorder / Node ID",
        type: "text",
        placeholder: "node_01",
      },
      {
        key: "Timestamp",
        label: "Timestamp",
        type: "text",
        placeholder: "2026-05-05T08:15:00",
      },
      {
        key: "Timestamp Local",
        label: "Timestamp Local",
        type: "text",
        placeholder: "2026-05-05T08:15:00-06:00",
      },
      {
        key: "Timestamp UTC",
        label: "Timestamp UTC",
        type: "text",
        placeholder: "2026-05-05T14:15:00+00:00",
      },
      {
        key: "Datetime",
        label: "Datetime",
        type: "text",
        placeholder: "2026-05-05 08:15:00",
      },
      {
        key: "Time Of Day",
        label: "Time Of Day",
        type: "text",
        placeholder: "morning",
      },
      {
        key: "Sunrise",
        label: "Sunrise",
        type: "text",
        placeholder: "2026-05-05T05:10:00-06:00",
      },
      {
        key: "Sunset",
        label: "Sunset",
        type: "text",
        placeholder: "2026-05-05T18:20:00-06:00",
      },
    ],
  },
  {
    title: "Weather",
    fields: [
      {
        key: "Temperature",
        label: "Temperature",
        type: "number",
        step: "0.1",
      },
      {
        key: "Windspeed",
        label: "Windspeed",
        type: "number",
        step: "0.1",
      },
      {
        key: "Precipitation",
        label: "Precipitation",
        type: "number",
        step: "0.1",
      },
      {
        key: "Humidity",
        label: "Humidity",
        type: "number",
        step: "1",
      },
      {
        key: "Weathercode",
        label: "Weathercode",
        type: "number",
        step: "1",
      },
      {
        key: "Weather Desc",
        label: "Weather Desc",
        type: "text",
        placeholder: "Overcast",
      },
    ],
  },
  {
    title: "Human Activity",
    fields: [
      {
        key: "Human Activity",
        label: "Human Activity",
        type: "text",
        placeholder: "footsteps",
      },
      {
        key: "Human Activity Score",
        label: "Human Activity Score",
        type: "number",
        step: "0.01",
      },
    ],
  },
  {
    title: "BirdNET Outputs",
    fields: [
      {
        key: "species",
        label: "species",
        type: "text",
        placeholder: "Tinamus major",
      },
      {
        key: "confidence",
        label: "confidence",
        type: "number",
        step: "0.001",
      },
    ],
  },
  {
    title: "Simulation Context",
    fields: [
      {
        key: "Sim Type",
        label: "Sim Type",
        type: "text",
        placeholder: "MVP",
      },
      {
        key: "Sim Relative Time",
        label: "Sim Relative Time",
        type: "number",
        step: "0.01",
      },
    ],
  },
  {
    title: "Engineered Features",
    fields: [
      {
        key: "hour_sin",
        label: "hour_sin",
        type: "number",
        step: "0.0001",
      },
      {
        key: "hour_cos",
        label: "hour_cos",
        type: "number",
        step: "0.0001",
      },
      {
        key: "Eerie_Silence",
        label: "Eerie Silence",
        type: "number",
        step: "0.0001",
      },
      {
        key: "Volume_Wind_Ratio",
        label: "Volume Wind Ratio",
        type: "number",
        step: "0.0001",
      },
      {
        key: "Volume_Spike_15s",
        label: "Volume Spike 15s",
        type: "number",
        step: "0.0001",
      },
    ],
  },
  {
    title: "Sentinel Species Flags",
    fields: STAGE4_SENTINEL_KEYS.map((key) => ({
      key,
      label: formatFieldLabel(key),
      type: "number",
      step: "1",
    })),
  },
];

const STAGE4_DEFAULTS = STAGE4_GROUPS.reduce((acc, group) => {
  group.fields.forEach((field) => {
    acc[field.key] = field.defaultValue ?? "";
  });
  return acc;
}, {});

export default function CreateRun({ onNavigate, onRunCreated }) {
  const canvasRef = useRef(null);
  const tipRef = useRef(null);
  const draggedButtonRef = useRef(null);
  const mapImageRef = useRef(null);

  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [shamanIConfig, setShamanIConfig] = useState(
    new ComponentPowerModel(30, undefined, false),
  );
  const [shamanIIConfig, setShamanIIConfig] = useState(
    new ComponentPowerModel(undefined, undefined, true),
  );
  const [shamanIProcessor, setShamanIProcessor] = useState("ESP32");
  const [shamanIIProcessor, setShamanIIProcessor] = useState("Radxa Zero");
  const [mediaFiles, setMediaFiles] = useState({});
  const [stage1Config, setStage1Config] = useState(() => ({
    ...STAGE1_DEFAULTS,
  }));
  const [stage4Config, setStage4Config] = useState(() => ({
    ...STAGE4_DEFAULTS,
  }));
  const [workflow, setWorkflow] = useState("design"); // "design" | "configure" | "loading" | "confirm"
  const [isLoading, setIsLoading] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState("");
  const [runName, setRunName] = useState(null);
  const [coordNodeType, setCoordNodeType] = useState("sensor");
  const [coordLat, setCoordLat] = useState("");
  const [coordLon, setCoordLon] = useState("");
  const [coordError, setCoordError] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [mouseCoords, setMouseCoords] = useState({
    lat: OSA_MAP_BOUNDS.latMax,
    lon: OSA_MAP_BOUNDS.lonMin,
    visible: false,
  });

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
  const selectedNode =
    nodes.find((node) => node.id === selectedNodeId) || null;

  // Sync state with React state
  useEffect(() => {
    stateRef.current.nodes = nodes;
    stateRef.current.edges = edges;
  }, [nodes, edges]);

  useEffect(() => {
    stateRef.current.selectedNode = selectedNodeId;
  }, [selectedNodeId]);

  // Load Osa Peninsula map image
  useEffect(() => {
    const img = new Image();
    img.src = "/Osa_Penisula_Map.png";
    img.onload = () => {
      mapImageRef.current = img;
    };
    img.onerror = () => {
      console.error("Failed to load Osa Peninsula map image");
    };
  }, []);

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
    const canvas = canvasRef.current;
    if (!canvas) return 0;
    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    return (
      (n.x * w - w / 2) * stateRef.current.zoom + w / 2 + stateRef.current.panX
    );
  }

  function ny(n) {
    const canvas = canvasRef.current;
    if (!canvas) return 0;
    const rect = canvas.getBoundingClientRect();
    const h = rect.height;
    return (
      (n.y * h - h / 2) * stateRef.current.zoom + h / 2 + stateRef.current.panY
    );
  }

  function clampPan() {
    const s = stateRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    const minPanX = w * (0.5 - s.zoom);
    const maxPanX = w * (s.zoom - 0.5);
    const minPanY = h * (0.5 - s.zoom);
    const maxPanY = h * (s.zoom - 0.5);

    s.panX = Math.max(minPanX, Math.min(maxPanX, s.panX));
    s.panY = Math.max(minPanY, Math.min(maxPanY, s.panY));
  }

  function nodeColor(role) {
    return role === "command"
      ? "#00e5ff"
      : role === "relay"
        ? "#a78bfa"
        : "#00e68a";
  }

  /**
   * Returns a consistent color per connection type:
   *   LoRa backbone       → blue (#3b82f6)
   *   Wi-Fi access links  → red  (#ef4444)
   */
  function connectionTypeColor(fromRole, toRole) {
    // Wi-Fi links: Shaman II <-> Shaman I
    if (
      (fromRole === "relay" && toRole === "sensor") ||
      (fromRole === "sensor" && toRole === "relay")
    ) {
      return "#ef4444";
    }

    // LoRa links: Command <-> Shaman II and Shaman II <-> Shaman II
    if (
      (fromRole === "command" && toRole === "relay") ||
      (fromRole === "relay" && toRole === "command")
    ) {
      return "#3b82f6";
    }
    if (fromRole === "relay" && toRole === "relay") return "#3b82f6";

    return "#3b82f6";
  }

  function formatComponentLabel(name) {
    const map = {
      sleep: "Processor Sleep",
      working: "Processor Working",
      cameraImage: "Camera Image",
      cameraSleep: "Camera Sleep",
      micListen: "Mic Listen",
      micSleep: "Mic Sleep",
      transmit: "Radio Transmit",
      receive: "Radio Receive",
    };
    if (map[name]) return map[name];
    // Fallback: split camelCase or underscores into words
    const spaced = name.replace(/([A-Z])/g, " $1").replace(/[_-]/g, " ");
    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
  }

  function drawCanvas() {
    const s = stateRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (canvas.width === 0 || canvas.height === 0) {
      resizeCanvas();
    }

    const ctx = canvas.getContext("2d");
    const rect = canvas.getBoundingClientRect();
    const w = rect.width,
      h = rect.height;
    ctx.clearRect(0, 0, w, h);

    // Draw Osa Peninsula map background
    if (mapImageRef.current) {
      ctx.save();
      ctx.globalAlpha = 1;

      // Map dimensions in normalized coordinates (-0.5 to 0.5)
      const mapSize = 1;
      const mapX = -mapSize / 2;
      const mapY = -mapSize / 2;

      // Convert to screen coordinates with pan/zoom
      const screenX = mapX * w * s.zoom + w / 2 + s.panX;
      const screenY = mapY * h * s.zoom + h / 2 + s.panY;
      const screenW = mapSize * w * s.zoom;
      const screenH = mapSize * h * s.zoom;

      ctx.drawImage(mapImageRef.current, screenX, screenY, screenW, screenH);
      ctx.restore();
    }

    // Draw map-like background pattern that moves with pan/zoom
    // Subtle topographic grid
    ctx.save();
    ctx.globalAlpha = 0.4;
    ctx.strokeStyle = "rgba(0, 0, 0, 0.5)";
    ctx.lineWidth = 1;
    const gridSize = 60 * s.zoom;
    const baseX = s.panX % gridSize;
    const baseY = s.panY % gridSize;

    // Vertical lines
    for (let x = baseX - gridSize; x < w + gridSize; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }

    // Horizontal lines
    for (let y = baseY - gridSize; y < h + gridSize; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
    ctx.restore();

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
        ? connectionTypeColor(from.role, to.role)
        : "#ff4d6a";
      ctx.lineWidth = Math.max(2, 2.5 * s.zoom);
      ctx.lineCap = "round";
      ctx.stroke();
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
      ctx.strokeStyle = "#7a5dfb";
      ctx.lineWidth = Math.max(1, 1.5 * s.zoom);
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
      const isHovered = s.hoveredNode === n;
      const isSelected = s.selectedNode === n.id;
      const isConnecting = s.connectingFrom && s.connectingFrom.id === n.id;
      const hl = isHovered || isSelected || isConnecting;

      if (hl) {
        ctx.beginPath();
        ctx.arc(x, y, sz + 10 * s.zoom, 0, Math.PI * 2);
        ctx.fillStyle = isConnecting
          ? "rgba(0, 230, 138, 0.9)"
          : "rgba(0,0,0,0.06)";
        ctx.fill();
      }

      ctx.lineWidth = hl ? 2.5 : 1.8;

      if (n.role === "command") {
        ctx.beginPath();
        ctx.arc(x, y, sz, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = isConnecting
          ? "rgba(0, 230, 138, 0.95)"
          : "rgba(0,0,0,0.18)";
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y, sz * 0.35, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
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
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = isConnecting
          ? "rgba(0, 230, 138, 0.95)"
          : "rgba(0,0,0,0.18)";
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y, 3 * s.zoom, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
      } else {
        const h = sz * 1.15;
        ctx.beginPath();
        ctx.moveTo(x, y - h);
        ctx.lineTo(x + sz, y + h * 0.6);
        ctx.lineTo(x - sz, y + h * 0.6);
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = isConnecting
          ? "rgba(0, 230, 138, 0.95)"
          : "rgba(0,0,0,0.18)";
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y + h * 0.05, 2.5 * s.zoom, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
      }

      ctx.font = `500 ${(n.role === "command" ? 10 : 9) * s.zoom}px "JetBrains Mono"`;
      ctx.fillStyle = "rgba(0, 0, 0, 0.85)";
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

  function buildNode(role, x, y, lat = null, lon = null) {
    const s = stateRef.current;
    s.nodeCounter[role]++;

    const id =
      role === "command"
        ? "CMD"
        : role === "relay"
          ? `R${s.nodeCounter.relay}`
          : `S${s.nodeCounter.sensor}`;

    const resolvedCoordinates =
      Number.isFinite(lat) && Number.isFinite(lon)
        ? { lat, lon }
        : normalizedToLatLon(x, y);

    return {
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
      lat: resolvedCoordinates.lat,
      lon: resolvedCoordinates.lon,
      realX: resolvedCoordinates.lat,
      realY: resolvedCoordinates.lon,
    };
  }

  function deleteNode(nodeToDelete) {
    setNodes((prevNodes) => prevNodes.filter((n) => n.id !== nodeToDelete.id));
    setEdges((prevEdges) =>
      prevEdges.filter(
        (e) => e.from !== nodeToDelete.id && e.to !== nodeToDelete.id,
      ),
    );
    setSelectedNodeId((prev) => (prev === nodeToDelete.id ? null : prev));
  }

  function addEdge(from, to) {
    if (!from || !to || !from.id || !to.id) return;
    if (!canConnect(from, to)) return;
    // Allow multiple edges between nodes (no duplicate checking)
    // Use functional setState to always get the latest state
    setEdges((prevEdges) => [...prevEdges, { from: from.id, to: to.id }]);
  }

  function deleteEdge(edgeToDelete) {
    setEdges((prevEdges) =>
      prevEdges.filter(
        (e) => !(e.from === edgeToDelete.from && e.to === edgeToDelete.to),
      ),
    );
  }

  function attachEvents() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.addEventListener("mousedown", onMouseDown);
    canvas.addEventListener("mousemove", onMouseMove);
    canvas.addEventListener("mouseleave", onMouseLeave);
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
    canvas.removeEventListener("mouseleave", onMouseLeave);
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
    const w = rect.width;
    const h = rect.height;

    const normalizedX = clamp((mx - w / 2 - s.panX) / (s.zoom * w) + 0.5, 0, 1);
    const normalizedY = clamp((my - h / 2 - s.panY) / (s.zoom * h) + 0.5, 0, 1);
    const realCoords = normalizedToLatLon(normalizedX, normalizedY);

    setMouseCoords((prev) => {
      if (
        prev.visible &&
        prev.lat === realCoords.lat &&
        prev.lon === realCoords.lon
      ) {
        return prev;
      }
      return { lat: realCoords.lat, lon: realCoords.lon, visible: true };
    });

    s.lastMouseX = mx;
    s.lastMouseY = my;

    if (s.isDragging) {
      s.panX = s.panStartX + (e.clientX - s.dragStartX);
      s.panY = s.panStartY + (e.clientY - s.dragStartY);
      clampPan();
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

  function onMouseLeave() {
    setMouseCoords((prev) => {
      if (!prev.visible) return prev;
      return { ...prev, visible: false };
    });
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
    clampPan();
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
      const rectArea = canvas.getBoundingClientRect();
      const w = rectArea.width;
      const h = rectArea.height;

      // Convert screen coords to normalized coords
      const x = clamp((mx - w / 2 - s.panX) / (s.zoom * w) + 0.5, 0, 1);
      const y = clamp((my - h / 2 - s.panY) / (s.zoom * h) + 0.5, 0, 1);

      const role = s.isPlacingNode;
      const newNode = buildNode(role, x, y);

      setNodes((prevNodes) => [...prevNodes, newNode]);
      s.isPlacingNode = null;
      canvas.style.cursor = "grab";
      return;
    }

    // If hovering a node, check if double-click to delete or start connection
    if (s.hoveredNode) {
      setSelectedNodeId(s.hoveredNode.id);
      if (e.detail === 2) {
        // Double click = delete
        deleteNode(s.hoveredNode);
        s.connectingFrom = null;
      } else {
        // Single click = start/complete connection
        const currentNodeId = s.hoveredNode.id;
        const startNodeId = s.connectingFrom ? s.connectingFrom.id : null;

        if (startNodeId === null) {
          // No connection in progress - start one
          s.connectingFrom = s.hoveredNode;
        } else if (startNodeId === currentNodeId) {
          // Clicked the same node again - cancel connection
          s.connectingFrom = null;
        } else {
          // Different node - complete the connection
          addEdge(s.connectingFrom, s.hoveredNode);
          s.connectingFrom = null;
        }
      }
    } else {
      s.connectingFrom = null;
      setSelectedNodeId(null);
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

  function insertNodeAtRealCoordinate() {
    const parsedLat = Number(coordLat);
    const parsedLon = Number(coordLon);

    if (!Number.isFinite(parsedLat) || !Number.isFinite(parsedLon)) {
      setCoordError("Enter valid numeric coordinates.");
      return;
    }

    if (
      parsedLat < OSA_MAP_BOUNDS.latMin ||
      parsedLat > OSA_MAP_BOUNDS.latMax ||
      parsedLon < OSA_MAP_BOUNDS.lonMin ||
      parsedLon > OSA_MAP_BOUNDS.lonMax
    ) {
      setCoordError(
        `Coordinates must be within ${OSA_MAP_BOUNDS.latMin}-${OSA_MAP_BOUNDS.latMax} (lat) and ${OSA_MAP_BOUNDS.lonMin}-${OSA_MAP_BOUNDS.lonMax} (lon).`,
      );
      return;
    }

    const { x, y } = latLonToNormalized(parsedLat, parsedLon);
    const newNode = buildNode(coordNodeType, x, y, parsedLat, parsedLon);
    setNodes((prevNodes) => [...prevNodes, newNode]);
    setCoordError("");
  }

  async function runSimulation() {
    setWorkflow("loading");
    setIsLoading(true);

    // Simulate loading delay
    await new Promise((resolve) => setTimeout(resolve, 2000));

    // Create run data
    const runData = {
      name:
        runName ||
        `Run-${new Date().toISOString().split("T")[0]}-${Date.now() % 10000}`,
      scenario: "MVP Simulation",
      shamani: shamanIProcessor,
      shamanii: shamanIIProcessor,
      duration: "24h",
      status: "pass",
      nodes: nodes.map((n) => ({
        id: n.id,
        label: n.label,
        role: n.role,
        x: n.x,
        y: n.y,
        realX: n.lat ?? n.realX ?? null,
        realY: n.lon ?? n.realY ?? null,
        lat: n.lat ?? n.realX ?? null,
        lon: n.lon ?? n.realY ?? null,
      })),
      edges: edges.map((e) => ({
        from: e.from,
        to: e.to,
      })),
      mediaFiles,
      shamanIConfig,
      shamanIIConfig,
      stage1Config,
      stage4Config,
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
    resetConfigSteps();
    setConfirmMessage("");
    setNodes([]);
    setEdges([]);
    setMediaFiles({});
    setStage1Config({ ...STAGE1_DEFAULTS });
    setStage4Config({ ...STAGE4_DEFAULTS });
    setCoordLat("");
    setCoordLon("");
    setCoordError("");
    setShamanIConfig(new ComponentPowerModel(30));
    setShamanIIConfig(new ComponentPowerModel());
    // Navigate to run selector if run was created
    if (onRunCreated) {
      onRunCreated();
    }
  }

  function zoomIn() {
    const s = stateRef.current;
    s.zoom = Math.max(0.5, Math.min(3, s.zoom * 1.2));
    clampPan();
  }

  function zoomOut() {
    const s = stateRef.current;
    s.zoom = Math.max(0.5, Math.min(3, s.zoom * 0.8));
    clampPan();
  }

  function recenter() {
    stateRef.current.zoom = 1;
    stateRef.current.panX = 0;
    stateRef.current.panY = 0;
  }

  function coerceNumberInput(value) {
    if (value === "" || value === null || value === undefined) return "";
    const parsed = Number(value);
    return Number.isNaN(parsed) ? "" : parsed;
  }

  const configSteps = [
    {
      id: "shamanI",
      title: "Power Configuration: Shaman I",
      content: (
        <div className="modal-section">
          <div className="modal-label">Shaman I Configuration</div>

          <div className="scp-input-group">
            <label className="scp-label">Processor:</label>
            <select
              className="scp-input"
              value={shamanIProcessor}
              onChange={(e) => setShamanIProcessor(e.target.value)}
            >
              <option value="ESP32">ESP32</option>
              <option value="Radxa Zero">Radxa Zero</option>
              <option value="Raspberry Pi">Raspberry Pi</option>
              <option value="Custom">Custom</option>
            </select>
          </div>

          <div className="scp-input-group">
            <label className="scp-label">Component Power Model</label>
          </div>
          <div
            style={{
              fontSize: "10px",
              color: "var(--text-muted)",
              marginBottom: "12px",
              lineHeight: "1.4",
            }}
          >
            Enter <strong>Current (mA) + Voltage (V)</strong> OR just{" "}
            <strong>Power (W)</strong> for each component.
          </div>

          <div className="scp-input-group">
            <label className="scp-label">Battery Capacity (Wh):</label>
            <input
              type="number"
              className="scp-input"
              value={shamanIConfig.batteryLife}
              onChange={(e) =>
                setShamanIConfig(
                  new ComponentPowerModel(
                    e.target.value,
                    shamanIConfig.components,
                  ),
                )
              }
              step="0.1"
            />
          </div>

          <div style={{ overflowX: "auto", marginTop: "12px" }}>
            <table
              style={{
                width: "100%",
                fontSize: "10px",
                borderCollapse: "collapse",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border)",
                    fontWeight: "600",
                  }}
                >
                  <th style={{ padding: "8px 4px", textAlign: "left" }}>
                    Component
                  </th>
                  <th style={{ padding: "8px 4px", textAlign: "right" }}>
                    Current (mA)
                  </th>
                  <th style={{ padding: "8px 4px", textAlign: "right" }}>
                    Voltage (V)
                  </th>
                  <th style={{ padding: "8px 4px", textAlign: "right" }}>
                    Power (W)
                  </th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(shamanIConfig.components).map(
                  ([name, cvp]) => (
                    <tr
                      key={name}
                      style={{
                        borderBottom: "1px solid var(--border-muted)",
                      }}
                    >
                      <td
                        style={{
                          padding: "8px 4px",
                          color: "var(--text-primary)",
                        }}
                      >
                        {formatComponentLabel(name)}
                      </td>
                      <td style={{ padding: "4px" }}>
                        <input
                          type="number"
                          className="scp-input"
                          placeholder="—"
                          value={cvp.current ?? ""}
                          onChange={(e) => {
                            const newVal = e.target.value
                              ? parseFloat(e.target.value)
                              : null;
                            shamanIConfig.components[name].current = newVal;
                            setShamanIConfig(
                              new ComponentPowerModel(
                                shamanIConfig.batteryLife,
                                { ...shamanIConfig.components },
                              ),
                            );
                          }}
                          step="0.1"
                          style={{ width: "100%" }}
                        />
                      </td>
                      <td style={{ padding: "4px" }}>
                        <input
                          type="number"
                          className="scp-input"
                          placeholder="—"
                          value={cvp.voltage ?? ""}
                          onChange={(e) => {
                            const newVal = e.target.value
                              ? parseFloat(e.target.value)
                              : null;
                            shamanIConfig.components[name].voltage = newVal;
                            setShamanIConfig(
                              new ComponentPowerModel(
                                shamanIConfig.batteryLife,
                                { ...shamanIConfig.components },
                              ),
                            );
                          }}
                          step="0.1"
                          style={{ width: "100%" }}
                        />
                      </td>
                      <td style={{ padding: "4px" }}>
                        <input
                          type="number"
                          className="scp-input"
                          placeholder="—"
                          value={cvp.power ?? ""}
                          onChange={(e) => {
                            const newVal = e.target.value
                              ? parseFloat(e.target.value)
                              : null;
                            shamanIConfig.components[name].power = newVal;
                            setShamanIConfig(
                              new ComponentPowerModel(
                                shamanIConfig.batteryLife,
                                { ...shamanIConfig.components },
                              ),
                            );
                          }}
                          step="0.001"
                          style={{ width: "100%" }}
                        />
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </div>
      ),
    },
    {
      id: "shamanII",
      title: "Power Configuration: Shaman II",
      content: (
        <div className="modal-section">
          <div className="modal-label">Shaman II Configuration</div>

          <div className="scp-input-group">
            <label className="scp-label">Processor:</label>
            <select
              className="scp-input"
              value={shamanIIProcessor}
              onChange={(e) => setShamanIIProcessor(e.target.value)}
            >
              <option value="ESP32">ESP32</option>
              <option value="Radxa Zero">Radxa Zero</option>
              <option value="Raspberry Pi">Raspberry Pi</option>
              <option value="Custom">Custom</option>
            </select>
          </div>

          <div className="scp-input-group">
            <label className="scp-label">Component Power Model</label>
          </div>
          <div
            style={{
              fontSize: "10px",
              color: "var(--text-muted)",
              marginBottom: "12px",
              lineHeight: "1.4",
            }}
          >
            Enter <strong>Current (mA) + Voltage (V)</strong> OR just{" "}
            <strong>Power (W)</strong> for each component.
          </div>

          <div className="scp-input-group">
            <label className="scp-label">Battery Capacity (Wh):</label>
            <input
              type="number"
              className="scp-input"
              value={shamanIIConfig.batteryLife}
              onChange={(e) =>
                setShamanIIConfig(
                  new ComponentPowerModel(
                    e.target.value,
                    shamanIIConfig.components,
                  ),
                )
              }
              step="0.1"
            />
          </div>

          <div style={{ overflowX: "auto", marginTop: "12px" }}>
            <table
              style={{
                width: "100%",
                fontSize: "10px",
                borderCollapse: "collapse",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border)",
                    fontWeight: "600",
                  }}
                >
                  <th style={{ padding: "8px 4px", textAlign: "left" }}>
                    Component
                  </th>
                  <th style={{ padding: "8px 4px", textAlign: "right" }}>
                    Current (mA)
                  </th>
                  <th style={{ padding: "8px 4px", textAlign: "right" }}>
                    Voltage (V)
                  </th>
                  <th style={{ padding: "8px 4px", textAlign: "right" }}>
                    Power (W)
                  </th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(shamanIIConfig.components).map(
                  ([name, cvp]) => (
                    <tr
                      key={name}
                      style={{
                        borderBottom: "1px solid var(--border-muted)",
                      }}
                    >
                      <td
                        style={{
                          padding: "8px 4px",
                          color: "var(--text-primary)",
                        }}
                      >
                        {formatComponentLabel(name)}
                      </td>
                      <td style={{ padding: "4px" }}>
                        <input
                          type="number"
                          className="scp-input"
                          placeholder="—"
                          value={cvp.current ?? ""}
                          onChange={(e) => {
                            const newVal = e.target.value
                              ? parseFloat(e.target.value)
                              : null;
                            shamanIIConfig.components[name].current = newVal;
                            setShamanIIConfig(
                              new ComponentPowerModel(
                                shamanIIConfig.batteryLife,
                                { ...shamanIIConfig.components },
                              ),
                            );
                          }}
                          step="0.1"
                          style={{ width: "100%" }}
                        />
                      </td>
                      <td style={{ padding: "4px" }}>
                        <input
                          type="number"
                          className="scp-input"
                          placeholder="—"
                          value={cvp.voltage ?? ""}
                          onChange={(e) => {
                            const newVal = e.target.value
                              ? parseFloat(e.target.value)
                              : null;
                            shamanIIConfig.components[name].voltage = newVal;
                            setShamanIIConfig(
                              new ComponentPowerModel(
                                shamanIIConfig.batteryLife,
                                { ...shamanIIConfig.components },
                              ),
                            );
                          }}
                          step="0.1"
                          style={{ width: "100%" }}
                        />
                      </td>
                      <td style={{ padding: "4px" }}>
                        <input
                          type="number"
                          className="scp-input"
                          placeholder="—"
                          value={cvp.power ?? ""}
                          onChange={(e) => {
                            const newVal = e.target.value
                              ? parseFloat(e.target.value)
                              : null;
                            shamanIIConfig.components[name].power = newVal;
                            setShamanIIConfig(
                              new ComponentPowerModel(
                                shamanIIConfig.batteryLife,
                                { ...shamanIIConfig.components },
                              ),
                            );
                          }}
                          step="0.001"
                          style={{ width: "100%" }}
                        />
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </div>
      ),
    },
    {
      id: "media",
      title: "Connect Media Files",
      content: (
        <div className="modal-section">
          <div className="modal-label">
            Select audio/video files for Shaman I nodes
          </div>
          {nodes
            .filter((node) => node.label.includes("Shaman I "))
            .map((node) => (
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
      ),
    },
    {
      id: "stage1",
      title: "Stage 1: Event Detection",
      content: (
        <div className="modal-section">
          <div className="modal-label">Candidate Generation Defaults</div>
          <div className="modal-helper">
            Applies to all nodes and clips for Stage 1 prefiltering.
          </div>
          <div className="modal-grid">
            {STAGE1_FIELDS.map((field) => (
              <div className="scp-input-group" key={field.key}>
                <label className="scp-label">{field.label}</label>
                <input
                  type="number"
                  className="scp-input"
                  value={stage1Config[field.key] ?? ""}
                  step={field.step}
                  onChange={(e) => {
                    const nextValue = coerceNumberInput(e.target.value);
                    setStage1Config((prev) => ({
                      ...prev,
                      [field.key]: nextValue,
                    }));
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      ),
    },
    {
      id: "stage4",
      title: "Stage 4: Human Presence",
      content: (
        <div className="modal-section">
          <div className="modal-label">Human Presence Feature Inputs</div>
          <div className="modal-helper">
            Provide defaults for per-clip metadata, weather, and audio features.
          </div>
          {STAGE4_GROUPS.map((group) => (
            <div className="modal-subsection" key={group.title}>
              <div className="modal-subsection-title">{group.title}</div>
              <div className="modal-grid">
                {group.fields.map((field) => (
                  <div className="scp-input-group" key={field.key}>
                    <label className="scp-label">{field.label}</label>
                    <input
                      type={field.type || "text"}
                      className="scp-input"
                      value={stage4Config[field.key] ?? ""}
                      placeholder={field.placeholder}
                      step={field.type === "number" ? field.step : undefined}
                      onChange={(e) => {
                        const rawValue = e.target.value;
                        const nextValue =
                          field.type === "number"
                            ? coerceNumberInput(rawValue)
                            : rawValue;
                        setStage4Config((prev) => ({
                          ...prev,
                          [field.key]: nextValue,
                        }));
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ),
    },
    {
      id: "details",
      title: "Configure Details",
      content: (
        <div className="modal-section">
          <div className="modal-label">Configure Run Details</div>
          <div className="scp-input-group">
            <label className="scp-label">Run Name:</label>
            <input
              className="scp-input"
              value={runName}
              onChange={(e) => setRunName(e.target.value)}
            />
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "var(--text-muted)",
              lineHeight: "1.5",
            }}
          ></div>
        </div>
      ),
    },
  ];

  const {
    activeIndex: configStepIndex,
    goToStep: goToConfigStep,
    next: nextConfigStep,
    prev: prevConfigStep,
    reset: resetConfigSteps,
    isFirst: isConfigFirst,
    isLast: isConfigLast,
  } = useStepNavigator(configSteps.length, 0);

  const selectedLat =
    selectedNode && Number.isFinite(selectedNode.lat)
      ? selectedNode.lat
      : selectedNode?.realX;
  const selectedLon =
    selectedNode && Number.isFinite(selectedNode.lon)
      ? selectedNode.lon
      : selectedNode?.realY;
  const selectedCoordsText = selectedNode
    ? formatLatLonDMS(selectedLat, selectedLon)
    : null;
  const mouseCoordsText = formatLatLonDMS(mouseCoords.lat, mouseCoords.lon);

  const osaMapBoundsMinText = formatLatLonDMS(OSA_MAP_BOUNDS.latMin, OSA_MAP_BOUNDS.lonMin);
  
  const osaMapBoundsMaxText = formatLatLonDMS(OSA_MAP_BOUNDS.latMax, OSA_MAP_BOUNDS.lonMax);
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

        <div className="coord-panel-title">Insert at Lat/Lon</div>
        <select
          className="coord-input"
          value={coordNodeType}
          onChange={(e) => setCoordNodeType(e.target.value)}
        >
          <option value="command">Command Center</option>
          <option value="relay">Shaman II</option>
          <option value="sensor">Shaman I</option>
        </select>
        <input
          className="coord-input"
          type="number"
          placeholder={`Lat (${osaMapBoundsMinText.lat} to ${osaMapBoundsMaxText.lat})`}
          value={coordLat}
          onChange={(e) => setCoordLat(e.target.value)}
        />
        <input
          className="coord-input"
          type="number"
          placeholder={`Lon (${osaMapBoundsMinText.lon} to ${osaMapBoundsMaxText.lon})`}
          value={coordLon}
          onChange={(e) => setCoordLon(e.target.value)}
        />
        <button className="toolbar-btn" onClick={insertNodeAtRealCoordinate}>
          Insert Node
        </button>
        {coordError ? <div className="coord-error">{coordError}</div> : null}

        <div className="toolbar-divider"></div>
        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
          <div>Nodes: {nodes.length}</div>
          <div>Edges: {edges.length}</div>
        </div>
      </div>

      {/* Zoom controls (top-right) */}
      <div
        className={`map-cursor-popup ${
          mouseCoords.visible || selectedNode ? "visible" : ""
        }`}
      >
        {selectedNode ? (
          <>
            <div className="map-cursor-row" style={{ fontWeight: 600 }}>
              Selected {selectedNode.id}
            </div>
            <div className="map-cursor-row">
              Lat: {selectedCoordsText?.lat ?? "N/A"}
            </div>
            <div className="map-cursor-row">
              Lon: {selectedCoordsText?.lon ?? "N/A"}
            </div>
            {mouseCoords.visible ? (
              <div
                style={{
                  height: "1px",
                  background: "var(--border)",
                  margin: "6px 0",
                  opacity: 0.6,
                }}
              ></div>
            ) : null}
          </>
        ) : null}
        {mouseCoords.visible ? (
          <>
            <div className="map-cursor-row">
              Lat: {mouseCoordsText.lat}
            </div>
            <div className="map-cursor-row">
              Lon: {mouseCoordsText.lon}
            </div>
          </>
        ) : null}
      </div>

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
              fill="#a78bfa"
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
              fill="#00e68a"
              stroke="#00e68a"
              strokeWidth="1.5"
            ></polygon>
          </svg>
          <span> Shaman I (Sensor)</span>
        </div>
        <div
          style={{
            height: "1px",
            background: "var(--border)",
            margin: "8px 0 6px",
          }}
        ></div>
        <div
          style={{
            fontSize: "9px",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            color: "var(--text-muted)",
            marginBottom: "4px",
          }}
        >
          Connections
        </div>
        <div className="legend-row">
          <div
            style={{
              width: "20px",
              height: "3px",
              borderRadius: "2px",
              background: "#3b82f6",
              flexShrink: 0,
            }}
          ></div>
          <span>LoRa (Shaman II to Shaman II)</span>
        </div>
        <div className="legend-row">
          <div
            style={{
              width: "20px",
              height: "3px",
              borderRadius: "2px",
              background: "#ef4444",
              flexShrink: 0,
            }}
          ></div>
          <span>Wi-Fi (Shaman II to Shaman I)</span>
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
            onClick={() => {
              setWorkflow("configure");
              resetConfigSteps();
            }}
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

      {/* Configuration Wizard */}
      {workflow === "configure" && (
        <ModalStepper
          open
          steps={configSteps}
          activeIndex={configStepIndex}
          onStepChange={goToConfigStep}
          dialogClassName="modal-dialog-fixed"
          onClose={() => {
            setWorkflow("design");
            resetConfigSteps();
          }}
          footer={
            <>
              <button
                className="modal-btn-cancel"
                onClick={() => {
                  if (isConfigFirst) {
                    setWorkflow("design");
                    resetConfigSteps();
                  } else {
                    prevConfigStep();
                  }
                }}
              >
                Back
              </button>
              <button
                className="modal-btn-confirm"
                onClick={() => {
                  if (isConfigLast) {
                    runSimulation();
                  } else {
                    nextConfigStep();
                  }
                }}
              >
                {isConfigLast ? "Run Simulation" : "Next"}
              </button>
            </>
          }
        />
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
