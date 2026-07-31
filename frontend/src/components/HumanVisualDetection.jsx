import React, { useEffect, useRef, useState } from "react";
import { detectHumans } from "../api";

/**
 * HumanVisualDetection
 *
 * Standalone YOLO person-detection page — upload a wildcam still, detect
 * people, draw bounding boxes. Deliberately independent of the run pipeline:
 * no run needs to be loaded, nothing is persisted.
 *
 * The backend returns ALL detections above a low confidence floor (~0.1) with
 * normalized coordinates; the slider filters client-side so dragging it is
 * instant and never re-runs inference. Boxes are positioned with percentage
 * coordinates on an overlay that exactly matches the rendered image, so they
 * stay aligned at any display size.
 */

const DEFAULT_THRESHOLD = 0.5;

export default function HumanVisualDetection() {
  const [previewUrl, setPreviewUrl] = useState(null);
  const [fileName, setFileName] = useState("");
  const [result, setResult] = useState(null); // { detections, image_width, ... }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  // Revoke object URLs when they are replaced or on unmount.
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  async function handleFile(file) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Please choose an image file (jpg, png, webp).");
      return;
    }

    setError("");
    setResult(null);
    setFileName(file.name);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });

    setLoading(true);
    try {
      const response = await detectHumans(file);
      setResult(response);
    } catch (err) {
      setError(err.message || "Detection failed");
    } finally {
      setLoading(false);
    }
  }

  function onInputChange(e) {
    handleFile(e.target.files?.[0] || null);
    // Allow re-selecting the same file to re-run detection.
    e.target.value = "";
  }

  function onDrop(e) {
    e.preventDefault();
    setDragActive(false);
    handleFile(e.dataTransfer.files?.[0] || null);
  }

  const allDetections = result?.detections || [];
  const visibleDetections = allDetections.filter(
    (d) => d.confidence >= threshold,
  );

  const countLine = loading
    ? "Detecting…"
    : result
      ? visibleDetections.length === 0
        ? allDetections.length > 0
          ? `No people above ${(threshold * 100).toFixed(0)}% confidence (${allDetections.length} below threshold)`
          : "No people detected in this image"
        : `${visibleDetections.length} ${visibleDetections.length === 1 ? "person" : "people"} detected`
      : "";

  return (
    <div id="pageHumanVision" style={{ overflowY: "auto", padding: 24 }}>
      <div className="overview-shell">
        <div className="overview-topbar">
          <div className="pg-title">Human Visual Detection</div>
          <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 6 }}>
            Upload a wildcam image to detect human presence. Images are
            processed in memory and never stored.
          </div>
        </div>

        <div
          className={`hvd-dropzone ${dragActive ? "drag-active" : ""}`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={onDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={onInputChange}
          />
          <div className="hvd-dropzone-inner">
            <div style={{ fontSize: 22 }}>◉</div>
            <div>
              {fileName ? (
                <>
                  <strong>{fileName}</strong> — click or drop to replace
                </>
              ) : (
                <>
                  Click to choose an image, or drag &amp; drop it here
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    jpg, png, webp — max 15 MB
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {error && <div className="hvd-error">{error}</div>}

        {previewUrl && (
          <div className="hvd-results">
            <div className="hvd-toolbar">
              <div className="hvd-count">{countLine}</div>
              <div className="hvd-slider-group">
                <label className="hvd-slider-label">
                  Confidence ≥ {(threshold * 100).toFixed(0)}%
                </label>
                <input
                  type="range"
                  min="0.1"
                  max="0.95"
                  step="0.01"
                  value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                />
              </div>
              {result && (
                <div className="hvd-meta">
                  {result.model} · {result.inference_ms} ms ·{" "}
                  {result.image_width}×{result.image_height}
                </div>
              )}
            </div>

            <div className="hvd-image-wrap">
              <img src={previewUrl} alt="Uploaded for human detection" />
              {visibleDetections.map((d, idx) => (
                <div
                  key={idx}
                  className="hvd-box"
                  style={{
                    left: `${d.x1 * 100}%`,
                    top: `${d.y1 * 100}%`,
                    width: `${(d.x2 - d.x1) * 100}%`,
                    height: `${(d.y2 - d.y1) * 100}%`,
                  }}
                >
                  <span className="hvd-box-label">
                    {(d.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
              {loading && (
                <div className="hvd-overlay-loading">
                  <div className="loading-spinner" />
                  <div>Running detection…</div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
