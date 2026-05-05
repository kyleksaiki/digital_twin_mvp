/**
 * Coordinate system utilities for mapping screen positions to real-world lat/lon
 * Uses calibration reference points to perform affine transformation
 */

export const OSA_MAP_BOUNDS = Object.freeze({
  latMax: 8.72,
  latMin: 8.366667,
  lonMin: -83.77,
  lonMax: -83.283333,
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

function normalizeDmsParts(deg, min, sec) {
  let nextDeg = deg;
  let nextMin = min;
  let nextSec = sec;

  if (nextSec >= 59.995) {
    nextSec = 0;
    nextMin += 1;
  }

  if (nextMin >= 60) {
    nextMin = 0;
    nextDeg += 1;
  }

  return { deg: nextDeg, min: nextMin, sec: nextSec };
}

function toDms(value, isLat) {
  if (!Number.isFinite(value)) return "N/A";

  const abs = Math.abs(value);
  const deg = Math.floor(abs);
  const minFloat = (abs - deg) * 60;
  const min = Math.floor(minFloat);
  const sec = (minFloat - min) * 60;
  const { deg: fixedDeg, min: fixedMin, sec: fixedSec } =
    normalizeDmsParts(deg, min, sec);
  const hemisphere = value >= 0 ? (isLat ? "N" : "E") : isLat ? "S" : "W";

  return `${fixedDeg}° ${fixedMin}' ${fixedSec.toFixed(2)}" ${hemisphere}`;
}

/**
 * Format lat/lon values as degrees/minutes/seconds strings.
 */
export function formatLatLonDMS(lat, lon) {
  return {
    lat: toDms(lat, true),
    lon: toDms(lon, false),
  };
}

/**
 * Validate calibration data has minimum required points
 */
export function validateCalibration(calibration) {
  if (!calibration || !calibration.refPoints) return false;
  return calibration.refPoints.length >= 2;
}
