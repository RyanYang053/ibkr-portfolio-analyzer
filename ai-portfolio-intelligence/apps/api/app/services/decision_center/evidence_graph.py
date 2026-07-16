from __future__ import annotations

from typing import Any


def build_evidence_graph(context: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    root = context.get("instrument_key") or context.get("symbol") or "holding"
    nodes.append({"id": root, "type": "holding"})
    for item in context.get("evidence") or []:
        node_id = f"{root}:{item.get('type')}"
        nodes.append({"id": node_id, "type": str(item.get("type")), "present": item.get("present")})
        edges.append({"from": root, "to": node_id, "rel": "has_evidence"})
    for lens in context.get("lens_results") or []:
        node_id = f"{root}:lens:{lens.get('lens_id')}"
        nodes.append(
            {
                "id": node_id,
                "type": "lens",
                "status": lens.get("status"),
                "score": lens.get("score"),
            }
        )
        edges.append({"from": root, "to": node_id, "rel": "evaluated_by"})
    return {"nodes": nodes, "edges": edges, "methodology_status": "experimental"}
