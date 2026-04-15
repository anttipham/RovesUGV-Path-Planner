# RovesUGV Path Planner

A Streamlit + OSMnx application for planning UGV routes in Seinäjoki.

## Features

- Road graph generation from OpenStreetMap
- Building access node generation
- Shortest-path routing with configurable penalties
- Edge centrality calculation from all building-to-building routes
- Interactive map UI (Folium via Streamlit)
- Optional 2D premise path generation from topographic WMS imagery

## Project Structure

- `src/main.py` – Streamlit entrypoint and app lifecycle
- `src/map.py` – Folium map/layer construction
- `src/graph.py` – OSM data fetch and graph preprocessing
- `src/path.py` – graph routing + virtual premise path insertion
- `src/path_image.py` – raster-based 2D pathfinding
- `src/config.py` – app constants and routing parameters
- `mapproxy.yaml` – MapProxy layer configuration

## Prerequisites

- Python 3.12 (Might also work with other versions as well)
- MapProxy
- Internet access for maps and OSM (OpenStreetMap) downloads

## Installation

1. Clone the repository
2. Install dependencies

```bash
pip install -r requirements.txt
```

## Running the Application

Start MapProxy:

```bash
mapproxy-util serve-develop ./mapproxy.yaml
```

In another terminal, run Streamlit:

```bash
streamlit run ./src/main.py
```

The application will be available at `http://localhost:8501`

## Configuration

Most routing and image-processing parameters are in `src/config.py`, for example:

- edge traversal costs (`COST_*`)
- crossing penalties
- centrality factor (`COST_CENTRALITY_FACTOR`)
- raster pathfinding parameters (`TRAVERSABLE_THRESHOLD`, `GOAL_BLOCK_DIAMETER`, etc.)

You can override centrality factor from query params:

- `http://localhost:8501/?cb=0.5`

## Routing Model Notes

Custom edge/node attributes used by the app:

- `ugv_sidewalk=True` (edge): edge is sidewalk-eligible, making it suitable for UGV navigation.
- `ugv_building_access=True` (node): Access points for buildings from or to which paths are calculated. These nodes have the same ID as the buildings they represent. If a building does not have a building access node, it is automatically added to the network at the center of the building.
- `ugv_closest_node_connection=True` (edge): temporary building-to-network connector
- `ugv_virtual=True` (edge): virtual premise path edge
- `centrality=True` (edge): path-frequency count across building pairs

## Troubleshooting

- If tiles do not load, verify MapProxy is running on `localhost:8080`.
- If graph/path updates seem stale, place a new marker or refresh session state.
- First graph build can be slow due to OSM fetch + path-pair centrality computation.

## Todos

- Optimize caching.
- Update edge lengths when a new edge is added. Length is now calculated for each edge on every update.
- Implement saving and loading of the graph and buildings to enable persistence across sessions.
- Disable the screen from going dark when the app is doing heavy computations. (Maybe with CSS or JavaScript?)
- Modify parameters for the pathfinding algorithm from the UI. Currently, the parameters are set from the config.py file and betweeness centrality factor can be set via query params, e.g. `http://localhost:8501/?cb=0.5`.
- In some cases, the end of the virtual path connects to itself instead of connecting to the road when the second to last node point is very close to the building access point. This is because the second to last node is closer to the building access point than the last node. (The logic connects the end of the path to the closest node.) This can be fixed by adding the ends of the paths before adding the virtual path nodes and edges, so that the path nodes are not considered candidates for the closest node connection.
- If needed, a turn-aware Dijkstra's algorithm could be used instead to track turning from a sidewalk (`ugv_sidewalk=True`) to a roadway (`ugv_sidewalk=False`).
