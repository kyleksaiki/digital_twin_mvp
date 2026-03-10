-- =============================================================
-- Shaman Digital Twin — MySQL Schema
-- =============================================================

-- -----------------------------------------------------------------
-- 1. RUNS  (replaces MOCK_RUNS)
-- -----------------------------------------------------------------
CREATE TABLE runs (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100)    NOT NULL,
    date        DATE            NOT NULL,
    scenario    VARCHAR(100)    NOT NULL,
    model       VARCHAR(100)    NOT NULL,
    hw          VARCHAR(50)     NOT NULL,
    duration    VARCHAR(20)     NOT NULL,
    status      ENUM('pass','warning','fail') NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------
-- 2. RUN METRICS  (replaces inline metric generation in runs.py)
--    One row per run — populates the 5 Overview Dashboard cards
--    and the Accuracy vs Confidence Threshold line chart marker.
-- -----------------------------------------------------------------
CREATE TABLE run_metrics (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    run_id          INT NOT NULL,
    accuracy        FLOAT   NOT NULL,   -- AI Accuracy card  (%)
    fpr             FLOAT   NOT NULL,   -- False Positive Rate card (%)
    latency_ms      INT     NOT NULL,   -- Avg Inference Latency card (ms)
    detection_count INT     NOT NULL,   -- Detection Count card
    battery_health  FLOAT   NOT NULL,   -- Battery Health card (%)
    congestion      INT     NOT NULL,   -- used by Network Map overview
    throughput      FLOAT   NOT NULL,   -- events/sec
    conf_threshold  FLOAT   NOT NULL,   -- current confidence threshold marker
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- 3. DETECTIONS BY TYPE  (bar chart on Overview Dashboard)
--    One row per detection category per run.
-- -----------------------------------------------------------------
CREATE TABLE detections_by_type (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    run_id      INT             NOT NULL,
    event_type  VARCHAR(50)     NOT NULL,   -- 'Bird', 'Gunshot', 'Chainsaw', 'Voice', 'Vehicle'
    count       INT             NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- 4. LATENCY BY RANK  (bar chart on Overview Dashboard)
--    One row per network rank per run.
-- -----------------------------------------------------------------
CREATE TABLE latency_by_rank (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    run_id      INT     NOT NULL,
    rank        INT     NOT NULL,   -- 1, 2, 3 (hop count from gateway)
    latency_ms  INT     NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- 5. ACCURACY CONFIDENCE CURVE  (line chart on Overview Dashboard)
--    One row per threshold sample per run.
-- -----------------------------------------------------------------
CREATE TABLE accuracy_confidence_curve (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    run_id      INT     NOT NULL,
    threshold   FLOAT   NOT NULL,   -- e.g. 0.30, 0.35 ... 0.95
    accuracy    FLOAT   NOT NULL,   -- accuracy at this threshold (%)
    fpr         FLOAT   NOT NULL,   -- false positive rate at this threshold (%)
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- 6. NETWORK NODES  (replaces MOCK_NODES)
--    One row per physical node per run.
-- -----------------------------------------------------------------
CREATE TABLE network_nodes (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    run_id          INT             NOT NULL,
    node_id         VARCHAR(20)     NOT NULL,   -- 'CMD', 'R1', 'S1', etc.
    label           VARCHAR(100)    NOT NULL,
    role            ENUM('command','relay','sensor') NOT NULL,
    pos_x           FLOAT           NOT NULL,   -- normalized 0-1
    pos_y           FLOAT           NOT NULL,   -- normalized 0-1
    battery         INT             NOT NULL,   -- %
    drain           FLOAT           NOT NULL,   -- %/hr
    traffic         INT             NOT NULL,   -- %
    health          ENUM('good','warning','critical') NOT NULL,
    packets_in      INT             NOT NULL,
    packets_out     INT             NOT NULL,
    retries         INT             NOT NULL,
    collisions      INT             NOT NULL,
    ai_det          INT             NOT NULL,   -- AI detection count
    parent_node_id  VARCHAR(20)     DEFAULT NULL,
    -- powerBreakdown stored as columns (radio/processor/mic are the only 3 keys)
    power_radio     INT             NOT NULL,
    power_processor INT             NOT NULL,
    power_mic       INT             NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    UNIQUE KEY uq_run_node (run_id, node_id)
);

-- -----------------------------------------------------------------
-- 7. NODE EVENTS  (the events[] list on each node)
--    One row per event string per node per run.
-- -----------------------------------------------------------------
CREATE TABLE node_events (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    run_id      INT             NOT NULL,
    node_id     VARCHAR(20)     NOT NULL,
    event_text  VARCHAR(255)    NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- 8. NODE CHILDREN  (the children[] list on relay nodes)
-- -----------------------------------------------------------------
CREATE TABLE node_children (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    run_id          INT         NOT NULL,
    parent_node_id  VARCHAR(20) NOT NULL,
    child_node_id   VARCHAR(20) NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- 9. NETWORK EDGES  (replaces MOCK_EDGES)
-- -----------------------------------------------------------------
CREATE TABLE network_edges (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    run_id      INT         NOT NULL,
    from_node   VARCHAR(20) NOT NULL,
    to_node     VARCHAR(20) NOT NULL,
    congestion  INT         NOT NULL,   -- %
    packet_loss FLOAT       NOT NULL,   -- %
    retries     INT         NOT NULL,
    collisions  INT         NOT NULL,
    avg_delay   INT         NOT NULL,   -- ms
    reroutes    INT         NOT NULL,
    latency     INT         NOT NULL,   -- ms
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- 10. REROUTE EVENTS  (replaces MOCK_REROUTES)
-- -----------------------------------------------------------------
CREATE TABLE reroute_events (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    run_id      INT         NOT NULL,
    from_node   VARCHAR(20) NOT NULL,
    to_node     VARCHAR(20) NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- 11. AI EVENTS  (the full AI Event Timeline — pipeline output)
--    One row per detection event. Used for future deep analysis.
-- -----------------------------------------------------------------
CREATE TABLE ai_events (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    run_id      INT             NOT NULL,
    timestamp_ms    BIGINT      NOT NULL,   -- ms since run start
    node_id     VARCHAR(20)     NOT NULL,
    event_type  VARCHAR(50)     NOT NULL,   -- 'Bird', 'Gunshot', etc.
    confidence  FLOAT           NOT NULL,   -- 0.0 - 1.0
    latency_ms  INT             NOT NULL,   -- inference latency
    energy_mj   FLOAT           NOT NULL,   -- energy cost in millijoules
    INDEX idx_run_time (run_id, timestamp_ms),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- Useful indexes for common dashboard queries
-- -----------------------------------------------------------------
CREATE INDEX idx_run_metrics_run    ON run_metrics(run_id);
CREATE INDEX idx_det_type_run       ON detections_by_type(run_id);
CREATE INDEX idx_latency_rank_run   ON latency_by_rank(run_id);
CREATE INDEX idx_acc_curve_run      ON accuracy_confidence_curve(run_id);
CREATE INDEX idx_nodes_run          ON network_nodes(run_id);
CREATE INDEX idx_edges_run          ON network_edges(run_id);
CREATE INDEX idx_reroutes_run       ON reroute_events(run_id);
