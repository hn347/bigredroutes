from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from config import GREEN
from route_data import (
    ROUTE_30_INBOUND_STOPS,
    ROUTE_30_OUTBOUND_STOPS,
    ROUTE_81_INBOUND_STOPS,
    ROUTE_81_OUTBOUND_STOPS,
    ROUTE_92_INBOUND_STOPS,
    ROUTE_92_OUTBOUND_STOPS,
    ROUTE_COLORS,
    TRANSFER_STOP_LOOKUP,
)

# identifies a stop on a specific route
NodeKey = Tuple[str, str, str]  # (route_id, stop_name, stop_id)


@dataclass(frozen=True)
class StopNode:
    # represents one stop in route graph
    route: str
    stop_name: str
    stop_id: str
    pixel: Tuple[int, int]
    direction: str
    route_index: int

    @property
    def key(self) -> NodeKey:
        # unique key for this stop
        return (self.route, self.stop_name, self.stop_id)


@dataclass
class PathResult:
    # stores best route found
    nodes: List[StopNode]
    transfers: int
    ride_steps: int


# stores ordered stop lists for each direction
DIRECTIONAL_ROUTE_STOPS = {
    "inbound": {
        "30": ROUTE_30_INBOUND_STOPS,
        "81": ROUTE_81_INBOUND_STOPS,
        "92": ROUTE_92_INBOUND_STOPS,
    },
    "outbound": {
        "30": ROUTE_30_OUTBOUND_STOPS,
        "81": ROUTE_81_OUTBOUND_STOPS,
        "92": ROUTE_92_OUTBOUND_STOPS,
    },
}


def _normalize_direction(direction: str) -> str:
    value = (direction or "").strip().lower()
    if value not in ("inbound", "outbound"):
        raise ValueError("direction must be 'inbound' or 'outbound'")
    return value


# build ordered stop lists for each route from dictionary order
def _build_nodes_by_route(directional_route_stops: Dict[str, List[dict]], direction: str,) -> Dict[str, List[StopNode]]:
    # convert dictionaries into StopNode objects
    route_nodes: Dict[str, List[StopNode]] = {}

    for route_id, ordered_stops in directional_route_stops.items():
        # empty list for route
        route_list = route_nodes.setdefault(route_id, [])
        for item in ordered_stops:
            stop_name = str(item["name"])
            stop_id = str(item["stop_id"])
            pixel = tuple(item["pixel"])
            # add to list as StopNode object
            route_list.append(
                StopNode(
                    route=str(route_id),
                    stop_name=stop_name,
                    stop_id=stop_id,
                    pixel=(int(pixel[0]), int(pixel[1])),
                    direction=direction,
                    route_index=len(route_list),
                )
            )

    return route_nodes


# create a graph - ride edges connect stops on same route and
# transfer edges connect transfer stops
def _build_graph(
    route_nodes: Dict[str, List[StopNode]],
    direction: str,
) -> Tuple[Dict[NodeKey, StopNode], Dict[NodeKey, List[Tuple[NodeKey, str]]], Dict[str, List[NodeKey]]]:

    nodes_by_key: Dict[NodeKey, StopNode] = {} # map each NodeKey to StopNode object
    adjacency: Dict[NodeKey, List[Tuple[NodeKey, str]]] = {} # map each stop to possible next moves
    stop_name_to_keys: Dict[str, List[NodeKey]] = {}
    route_stop_to_keys: Dict[Tuple[str, str], List[NodeKey]] = {}

    for route_id, nodes in route_nodes.items():
        for i, node in enumerate(nodes):
            key = node.key
            nodes_by_key[key] = node
            adjacency.setdefault(key, [])
            stop_name_to_keys.setdefault(node.stop_name, []).append(key)
            route_stop_to_keys.setdefault((node.route, node.stop_id), []).append(key)

            if i + 1 < len(nodes):
                nxt = nodes[i + 1]
                adjacency[key].append((nxt.key, "ride"))

    # transfer edges are constrained by TRANSFER_STOP_LOOKUP + direction
    for stop_name, transfer_items in TRANSFER_STOP_LOOKUP.items():
        allowed_items = [
            item for item in transfer_items
            if str(item.get("direction", "")).strip().lower() == direction
        ]
        # skip stops that don't support a transfer
        if not allowed_items:
            continue

        keys_at_stop = []
        # try to find transfer nodes
        for item in allowed_items:
            route_id = str(item["route"])
            stop_id = str(item["stop_id"])
            keys_at_stop.extend(route_stop_to_keys.get((route_id, stop_id), []))

        # if a transfer mapping route/stop_id does not exist
        if not keys_at_stop:
            allowed_routes = {str(item["route"]) for item in allowed_items}
            keys_at_stop = [
                key for key in stop_name_to_keys.get(stop_name, [])
                if key[0] in allowed_routes
            ]

        # connect routes together at this transfer stop
        for src in keys_at_stop:
            for dst in keys_at_stop:
                if src == dst:
                    continue
                # only create transfer edges between different routes
                if src[0] != dst[0]:
                    adjacency.setdefault(src, []).append((dst, "transfer"))

    return nodes_by_key, adjacency, stop_name_to_keys


# counte for fewer transfers and shortest node path
def _score(transfers: int, ride_steps: int, total_nodes: int) -> Tuple[int, int, int]:

    return (transfers, ride_steps, total_nodes)


# recursive backtracking
def _search_best_path(
    current_key: NodeKey,
    end_keys: Set[NodeKey],
    nodes_by_key: Dict[NodeKey, StopNode],
    adjacency: Dict[NodeKey, List[Tuple[NodeKey, str]]],
    visited: Set[NodeKey],
    current_nodes: List[StopNode],
    transfers: int,
    ride_steps: int,
    best: Optional[PathResult],
) -> Optional[PathResult]:

    # if current stop is one of the possible ending stops, save this path
    if current_key in end_keys:
        candidate = PathResult(nodes=list(current_nodes), transfers=transfers, ride_steps=ride_steps)
        # keep if this is the first valid path
        if best is None:
            return candidate
        # replace current best path if this has a better score
        if _score(candidate.transfers, candidate.ride_steps, len(candidate.nodes)) < _score(
            best.transfers, best.ride_steps, len(best.nodes)
        ):
            return candidate
        return best

    # stop exploring this path if it is alr4ady worse than current best path
    if best is not None and _score(transfers, ride_steps, len(current_nodes)) >= _score(
        best.transfers, best.ride_steps, len(best.nodes)
    ):
        return best

    for next_key, edge_type in adjacency.get(current_key, []):
        if next_key in visited:
            continue

        next_node = nodes_by_key[next_key]
        visited.add(next_key)
        current_nodes.append(next_node)

        # update counter depending on if this is a ride or transfer
        next_transfers = transfers + (1 if edge_type == "transfer" else 0)
        next_ride_steps = ride_steps + (1 if edge_type == "ride" else 0)

        best = _search_best_path(
            current_key=next_key,
            end_keys=end_keys,
            nodes_by_key=nodes_by_key,
            adjacency=adjacency,
            visited=visited,
            current_nodes=current_nodes,
            transfers=next_transfers,
            ride_steps=next_ride_steps,
            best=best,
        )

        # backtrack so another path can be tested
        current_nodes.pop()
        visited.remove(next_key)

    return best


# returns best path (fewest transfers)
def find_best_route(
    start_stop_name: str,
    end_stop_name: str,
    direction: str,
    start_route_id: Optional[str] = None,
    start_stop_id: Optional[str] = None,
    end_route_id: Optional[str] = None,
    end_stop_id: Optional[str] = None,
) -> Optional[dict]:

    # validate direction
    normalized_direction = _normalize_direction(direction)
    directional_route_stops = DIRECTIONAL_ROUTE_STOPS[normalized_direction]
    all_stop_names = {
        str(stop["name"])
        for stops in directional_route_stops.values()
        for stop in stops
    }
    if start_stop_name not in all_stop_names:
        return None
    if end_stop_name not in all_stop_names:
        return None

    # convert route stop data into graph nodes
    route_nodes = _build_nodes_by_route(directional_route_stops, normalized_direction)
    nodes_by_key, adjacency, stop_name_to_keys = _build_graph(route_nodes, normalized_direction)

    start_keys = stop_name_to_keys.get(start_stop_name, [])
    end_keys = set(stop_name_to_keys.get(end_stop_name, []))

    # narrow start search if specific stop id was selected
    if start_route_id is not None:
        start_keys = [key for key in start_keys if key[0] == str(start_route_id)]
    if start_stop_id is not None:
        start_keys = [key for key in start_keys if key[2] == str(start_stop_id)]

    # narrow end search if specific stop id was selected
    if end_route_id is not None:
        end_keys = {key for key in end_keys if key[0] == str(end_route_id)}
    if end_stop_id is not None:
        end_keys = {key for key in end_keys if key[2] == str(end_stop_id)}

    if not start_keys or not end_keys:
        return None

    best: Optional[PathResult] = None

    for start_key in start_keys:
        start_node = nodes_by_key[start_key]
        best = _search_best_path(
            current_key=start_key,
            end_keys=end_keys,
            nodes_by_key=nodes_by_key,
            adjacency=adjacency,
            visited={start_key},
            current_nodes=[start_node],
            transfers=0,
            ride_steps=0,
            best=best,
        )

    if best is None:
        return None

    # convert final path into dict
    path_entries = [
        {
            "route": node.route,
            "stop_name": node.stop_name,
            "stop_id": node.stop_id,
            "pixel": node.pixel,
        }
        for node in best.nodes
    ]

    segments: List[dict] = []
    for node in best.nodes:
        if not segments or segments[-1]["route"] != node.route:
            segments.append({"route": node.route, "stops": [], "pixels": []})
        segments[-1]["stops"].append(node.stop_name)
        segments[-1]["pixels"].append(node.pixel)

    # only store pixels and routes for led drawing
    pixels = [node.pixel for node in best.nodes]
    routes_used = [segment["route"] for segment in segments]

    return {
        "direction": normalized_direction,
        "transfers": best.transfers,
        "ride_steps": best.ride_steps,
        "path": path_entries,
        "segments": segments,
        "pixels": pixels,
        "routes_used": routes_used,
    }


# light up route on matrix and returns if a path was drawn
def light_route_result(led_matrix, route_result: Optional[dict]) -> bool:
    if not route_result:
        return False

    led_matrix.clear()
    # draw each route segment using color
    for segment in route_result.get("segments", []):
        route_id = segment["route"]
        color = ROUTE_COLORS.get(route_id, GREEN)
        for pixel in segment.get("pixels", []):
            led_matrix.set_pixel(pixel[0], pixel[1], color)

    return True


# wrapper for picker menu format
def quick_find_from_entries(
    start_entry: Optional[Tuple[str, str, str]],
    end_entry: Optional[Tuple[str, str, str]],
    direction: str,
) -> Optional[dict]:

    if start_entry is None or end_entry is None:
        return None

    start_route_id, start_stop_name, start_stop_id = start_entry
    end_route_id, end_stop_name, end_stop_id = end_entry
    return find_best_route(
        start_stop_name,
        end_stop_name,
        direction,
        start_route_id=start_route_id,
        start_stop_id=start_stop_id,
        end_route_id=end_route_id,
        end_stop_id=end_stop_id,
    )

