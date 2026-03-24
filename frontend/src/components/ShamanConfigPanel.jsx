import React, { useState } from "react";

/**
 * ShamanConfigPanel - Global Shaman configuration for all nodes
 * 
 * Props:
 *   config: object with power model, component settings, solar config
 *   onChange: (config) => void - called when config changes
 */
export default function ShamanConfigPanel({ config, onChange }) {
  const [isExpanded, setIsExpanded] = useState(false);

  function handlePowerModelChange(model) {
    onChange({
      ...config,
      powerModel: model,
    });
  }

  function handleCurrentChange(e) {
    onChange({
      ...config,
      current: parseFloat(e.target.value) || 0,
    });
  }

  function handleVoltageChange(e) {
    onChange({
      ...config,
      voltage: parseFloat(e.target.value) || 0,
    });
  }

  function handlePowerChange(e) {
    onChange({
      ...config,
      power: parseFloat(e.target.value) || 0,
    });
  }

  function handleMaxRangeChange(e) {
    onChange({
      ...config,
      maxRange: parseFloat(e.target.value) || 0,
    });
  }

  function handleComponentChange(key) {
    onChange({
      ...config,
      components: {
        ...config.components,
        [key]: !config.components[key],
      },
    });
  }

  function handleSolarPowerChange(e) {
    onChange({
      ...config,
      solar: {
        ...config.solar,
        panelPower: parseFloat(e.target.value) || 0,
      },
    });
  }

  function handleSolarEfficiencyChange(e) {
    onChange({
      ...config,
      solar: {
        ...config.solar,
        efficiency: parseFloat(e.target.value) || 0,
      },
    });
  }

  const powerWattage = config.powerModel === "current" ? (config.current * config.voltage) / 1000 : config.power;

  return (
    <div className={`shaman-config-panel ${isExpanded ? "expanded" : ""}`}>
      <div className="scp-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="scp-title">Shaman Config</div>
        <div className="scp-toggle">{isExpanded ? "−" : "+"}</div>
      </div>

      {isExpanded && (
        <div className="scp-content">
          {/* Power Model Section */}
          <div className="scp-section">
            <div className="scp-section-title">Component Power Model</div>
            <div className="scp-form-group">
              <label className="scp-radio">
                <input
                  type="radio"
                  name="powerModel"
                  value="current"
                  checked={config.powerModel === "current"}
                  onChange={(e) => handlePowerModelChange(e.target.value)}
                />
                <span>Current + Voltage</span>
              </label>
            </div>
            <div className="scp-form-group">
              <label className="scp-radio">
                <input
                  type="radio"
                  name="powerModel"
                  value="power"
                  checked={config.powerModel === "power"}
                  onChange={(e) => handlePowerModelChange(e.target.value)}
                />
                <span>Power (W)</span>
              </label>
            </div>

            {config.powerModel === "current" ? (
              <>
                <div className="scp-input-group">
                  <label className="scp-label">Current (mA)</label>
                  <input
                    type="number"
                    className="scp-input"
                    value={config.current}
                    onChange={handleCurrentChange}
                    step="0.1"
                  />
                </div>
                <div className="scp-input-group">
                  <label className="scp-label">Voltage (V)</label>
                  <input
                    type="number"
                    className="scp-input"
                    value={config.voltage}
                    onChange={handleVoltageChange}
                    step="0.1"
                  />
                </div>
              </>
            ) : (
              <div className="scp-input-group">
                <label className="scp-label">Power (W)</label>
                <input
                  type="number"
                  className="scp-input"
                  value={config.power}
                  onChange={handlePowerChange}
                  step="0.1"
                />
              </div>
            )}

            <div className="scp-computed">
              <span className="scp-label">Est. Power</span>
              <span className="scp-value">{powerWattage.toFixed(3)} W</span>
            </div>
          </div>

          {/* Connection Range */}
          <div className="scp-section">
            <div className="scp-section-title">Network</div>
            <div className="scp-input-group">
              <label className="scp-label">Max Connection Range (m)</label>
              <input
                type="number"
                className="scp-input"
                value={config.maxRange}
                onChange={handleMaxRangeChange}
                step="1"
              />
            </div>
          </div>

          {/* Components & States */}
          <div className="scp-section">
            <div className="scp-section-title">Component / State Processing</div>
            <div className="scp-checklist">
              <label className="scp-checkbox">
                <input
                  type="checkbox"
                  checked={config.components.sleep}
                  onChange={() => handleComponentChange("sleep")}
                />
                <span>Sleep</span>
              </label>
              <label className="scp-checkbox">
                <input
                  type="checkbox"
                  checked={config.components.working}
                  onChange={() => handleComponentChange("working")}
                />
                <span>Working</span>
              </label>
              <label className="scp-checkbox">
                <input
                  type="checkbox"
                  checked={config.components.transmit}
                  onChange={() => handleComponentChange("transmit")}
                />
                <span>Communications: Transmit</span>
              </label>
              <label className="scp-checkbox">
                <input
                  type="checkbox"
                  checked={config.components.receive}
                  onChange={() => handleComponentChange("receive")}
                />
                <span>Communications: Receive</span>
              </label>
              <label className="scp-checkbox">
                <input
                  type="checkbox"
                  checked={config.components.cameraImage}
                  onChange={() => handleComponentChange("cameraImage")}
                />
                <span>Camera: Taking Image</span>
              </label>
              <label className="scp-checkbox">
                <input
                  type="checkbox"
                  checked={config.components.cameraSleep}
                  onChange={() => handleComponentChange("cameraSleep")}
                />
                <span>Camera: Sleep</span>
              </label>
              <label className="scp-checkbox">
                <input
                  type="checkbox"
                  checked={config.components.micListen}
                  onChange={() => handleComponentChange("micListen")}
                />
                <span>Microphone: Listening</span>
              </label>
              <label className="scp-checkbox">
                <input
                  type="checkbox"
                  checked={config.components.micSleep}
                  onChange={() => handleComponentChange("micSleep")}
                />
                <span>Microphone: Sleep</span>
              </label>
            </div>
          </div>

          {/* Solar Panel */}
          <div className="scp-section">
            <div className="scp-section-title">Solar</div>
            <div className="scp-input-group">
              <label className="scp-label">Panel Power (W)</label>
              <input
                type="number"
                className="scp-input"
                value={config.solar.panelPower}
                onChange={handleSolarPowerChange}
                step="0.1"
              />
            </div>
            <div className="scp-input-group">
              <label className="scp-label">Charge Efficiency (%)</label>
              <input
                type="number"
                className="scp-input"
                value={config.solar.efficiency}
                onChange={handleSolarEfficiencyChange}
                step="0.1"
                min="0"
                max="100"
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="scp-actions">
            <button className="scp-btn-save" onClick={() => setIsExpanded(false)}>
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
