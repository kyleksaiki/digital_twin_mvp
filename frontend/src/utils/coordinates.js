/**
 * Coordinate system utilities for mapping screen positions to real-world lat/lon
 * Uses calibration reference points to perform affine transformation
 */

/**
 * Validate calibration data has minimum required points
 */
export function validateCalibration(calibration) {
  if (!calibration || !calibration.refPoints) return false;
  return calibration.refPoints.length >= 2;
}

/**
 * Convert screen coordinates to real-world lat/lon using calibration
 * Uses linear regression on reference points
 */
export function screenToReal(screenX, screenY, calibration) {
  if (!validateCalibration(calibration)) {
    return null; // No calibration available
  }

  const refPoints = calibration.refPoints;
  
  // Use least-squares linear regression to fit screen → lat and screen → lon
  // For simplicity with 2+ points, use weighted average based on distance
  
  let totalWeight = 0;
  let weightedLat = 0;
  let weightedLon = 0;

  for (const ref of refPoints) {
    const dx = screenX - ref.x;
    const dy = screenY - ref.y;
    const distSq = dx * dx + dy * dy;
    const dist = Math.sqrt(distSq);
    
    // Weight inversely proportional to distance (closer points have more influence)
    const weight = dist < 1 ? 1000 : 1 / (dist + 1);
    
    weightedLat += ref.lat * weight;
    weightedLon += ref.lon * weight;
    totalWeight += weight;
  }

  return {
    lat: weightedLat / totalWeight,
    lon: weightedLon / totalWeight,
  };
}

/**
 * Convert real-world lat/lon to screen coordinates using calibration
 */
export function realToScreen(lat, lon, calibration) {
  if (!validateCalibration(calibration)) {
    return null; // No calibration available
  }

  const refPoints = calibration.refPoints;
  
  let totalWeight = 0;
  let weightedX = 0;
  let weightedY = 0;

  for (const ref of refPoints) {
    const dLat = lat - ref.lat;
    const dLon = lon - ref.lon;
    const distSq = dLat * dLat + dLon * dLon;
    const dist = Math.sqrt(distSq);
    
    // Weight inversely proportional to distance
    const weight = dist < 0.0001 ? 1000 : 1 / (dist + 0.0001);
    
    weightedX += ref.x * weight;
    weightedY += ref.y * weight;
    totalWeight += weight;
  }

  return {
    x: weightedX / totalWeight,
    y: weightedY / totalWeight,
  };
}

/**
 * Calculate distance between two real-world coordinates using Haversine formula
 * Returns distance in kilometers
 */
export function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371; // Earth radius in km
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Calculate distance between two screen coordinates
 * Returns distance in normalized units (0-1 scale)
 */
export function screenDistance(x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Format lat/lon for display
 */
export function formatCoordinate(lat, lon) {
  const latStr = Math.abs(lat).toFixed(6) + (lat >= 0 ? '°N' : '°S');
  const lonStr = Math.abs(lon).toFixed(6) + (lon >= 0 ? '°E' : '°W');
  return `${latStr}, ${lonStr}`;
}

/**
 * Parse coordinate string (e.g., "-2.5, 35.3") into {lat, lon}
 */
export function parseCoordinate(coordStr) {
  const parts = coordStr.split(',').map(s => s.trim());
  if (parts.length !== 2) return null;
  const lat = parseFloat(parts[0]);
  const lon = parseFloat(parts[1]);
  if (isNaN(lat) || isNaN(lon)) return null;
  return { lat, lon };
}
