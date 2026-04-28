/**
 * Coordinate system utilities for mapping screen positions to real-world lat/lon
 * Uses calibration reference points to perform affine transformation
 */

export const OSA_MAP_BOUNDS = Object.freeze({
  latMax: 8.70,
  latMin: 8.37,
  lonMin: -83.75,
  lonMax: -83.28,
});

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

/**
 * Convert normalized (0-1) coordinates to lat/lon using map bounds.
 * y=0 is top of the image, so latitude decreases as y increases.
 */
export function normalizedToLatLon(x, y, bounds = OSA_MAP_BOUNDS) {
  const latRange = bounds.latMax - bounds.latMin || 1;
  const lonRange = bounds.lonMax - bounds.lonMin || 1;
  const lat = bounds.latMax - y * latRange;
  const lon = bounds.lonMin + x * lonRange;

  return {
    lat: Number(lat.toFixed(6)),
    lon: Number(lon.toFixed(6)),
  };
}

/**
 * Convert lat/lon to normalized (0-1) coordinates using map bounds.
 */
export function latLonToNormalized(lat, lon, bounds = OSA_MAP_BOUNDS) {
  const latRange = bounds.latMax - bounds.latMin || 1;
  const lonRange = bounds.lonMax - bounds.lonMin || 1;

  return {
    x: clamp((lon - bounds.lonMin) / lonRange, 0, 1),
    y: clamp((bounds.latMax - lat) / latRange, 0, 1),
  };
}

/**
 * Validate calibration data has minimum required points
 */
export function validateCalibration(calibration) {
  if (!calibration || !calibration.refPoints) return false;
  return calibration.refPoints.length >= 2;
}
