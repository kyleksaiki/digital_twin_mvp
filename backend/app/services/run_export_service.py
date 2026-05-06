import csv
import io
import re
from typing import Iterator

from sqlalchemy.orm import Session

from app.db_models import (
    DetectionByTypeRow,
    NetworkEdgeRow,
    NetworkNodeRow,
    RunMetricsRow,
    RunRow,
)


class _CsvStream:
    def __init__(self) -> None:
        self.buffer = io.StringIO(newline="")
        self.writer = csv.writer(self.buffer)

    def write_comment(self, text: str) -> bytes:
        self.buffer.write(f"# {text}\n")
        return self._flush()

    def write_row(self, row: list) -> bytes:
        self.writer.writerow(row)
        return self._flush()

    def _flush(self) -> bytes:
        data = self.buffer.getvalue()
        self.buffer.seek(0)
        self.buffer.truncate(0)
        return data.encode("utf-8")


class RunExportService:
    """Streams run exports in analysis-friendly CSV sections."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_run(self, run_id: int) -> RunRow | None:
        return self.db.query(RunRow).filter(RunRow.id == run_id).first()

    def build_filename(self, run_id: int) -> str:
        raw_name = f"run_{run_id}_export.csv"
        return re.sub(r"[^A-Za-z0-9._-]", "_", raw_name)

    def stream_run_export(
        self,
        run: RunRow,
        include_nodes: bool = True,
        include_edges: bool = True,
    ) -> Iterator[bytes]:
        stream = _CsvStream()

        yield stream.write_comment("RUN SUMMARY")
        yield stream.write_row(
            [
                "run_id",
                "name",
                "date",
                "scenario",
                "duration",
                "status",
                "shamanIProcessor",
                "shamanIIProcessor",
            ]
        )
        yield stream.write_row(
            [
                run.id,
                run.name,
                run.date.isoformat() if run.date else "",
                run.scenario,
                run.duration,
                run.status,
                run.shamani,
                run.shamanii,
            ]
        )

        metrics = (
            self.db.query(RunMetricsRow)
            .filter(RunMetricsRow.run_id == run.id)
            .first()
        )
        yield stream.write_comment("METRICS")
        yield stream.write_row(
            [
                "accuracy",
                "fpr",
                "latency_ms",
                "detection_count",
                "battery_health",
                "congestion",
                "throughput",
                "conf_threshold",
            ]
        )
        yield stream.write_row(
            [
                metrics.accuracy if metrics else "",
                metrics.fpr if metrics else "",
                metrics.latency_ms if metrics else "",
                metrics.detection_count if metrics else "",
                metrics.battery_health if metrics else "",
                metrics.congestion if metrics else "",
                metrics.throughput if metrics else "",
                metrics.conf_threshold if metrics else "",
            ]
        )

        if include_nodes:
            yield stream.write_comment("NODES")
            yield stream.write_row(
                [
                    "node_id",
                    "label",
                    "role",
                    "battery",
                    "drain",
                    "traffic",
                    "health",
                    "packets_in",
                    "packets_out",
                    "retries",
                    "collisions",
                    "ai_det",
                    "parent_node_id",
                ]
            )
            nodes_query = (
                self.db.query(NetworkNodeRow)
                .filter(NetworkNodeRow.run_id == run.id)
                .order_by(NetworkNodeRow.node_id, NetworkNodeRow.id)
            )
            for node in nodes_query.yield_per(1000):
                yield stream.write_row(
                    [
                        node.node_id,
                        node.label,
                        node.role,
                        node.battery,
                        node.drain,
                        node.traffic,
                        node.health,
                        node.packets_in,
                        node.packets_out,
                        node.retries,
                        node.collisions,
                        node.ai_det,
                        node.parent_node_id or "",
                    ]
                )

        if include_edges:
            yield stream.write_comment("EDGES")
            yield stream.write_row(
                [
                    "from_node",
                    "to_node",
                    "congestion",
                    "packet_loss",
                    "latency",
                    "avg_delay",
                    "reroutes",
                ]
            )
            edges_query = (
                self.db.query(NetworkEdgeRow)
                .filter(NetworkEdgeRow.run_id == run.id)
                .order_by(NetworkEdgeRow.from_node, NetworkEdgeRow.to_node, NetworkEdgeRow.id)
            )
            for edge in edges_query.yield_per(1000):
                yield stream.write_row(
                    [
                        edge.from_node,
                        edge.to_node,
                        edge.congestion,
                        edge.packet_loss,
                        edge.latency,
                        edge.avg_delay,
                        edge.reroutes,
                    ]
                )

        yield stream.write_comment("DETECTIONS")
        yield stream.write_row(["event_type", "count"])
        detections_query = (
            self.db.query(DetectionByTypeRow)
            .filter(DetectionByTypeRow.run_id == run.id)
            .order_by(DetectionByTypeRow.event_type, DetectionByTypeRow.id)
        )
        for detection in detections_query.yield_per(1000):
            yield stream.write_row([detection.event_type, detection.count])
