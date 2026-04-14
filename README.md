# RovesUGV Path Planner

## Getting Started

### Prerequisites

- MapProxy
- Streamlit
- Python 3.x

### Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`

### Running the Application

Start the MapProxy development server:

```bash
mapproxy-util serve-develop ./mapproxy.yaml
```

In another terminal, run the Streamlit application:

```bash
streamlit run ./src/main.py
```

The application will be available at `http://localhost:8501`

## Details

The application consists of two main components:

1. **MapProxy**: Serves map tiles from OpenStreetMap. The configuration is defined in `mapproxy.yaml`.
2. **Streamlit App**: The main application logic is in `src/main.py`. It uses OSMnx to fetch and manipulate the graph data, and Folium to display the map and paths.

### Graph Construction

The graph is built using OSMnx. Nodes and edges retain the original attributes from OpenStreetMap (OSM). The graph contains the following custom attributes, prefixed with `ugv_`:

- `ugv_sidewalk=True`: This attribute indicates that the edge is a sidewalk, making it suitable for UGV navigation. It is determined based on the presence of certain OSM tags.
- `ugv_building_access=True`: Access points for buildings from or to which paths are calculated. These nodes have the same ID as the buildings they represent. If a building does not have a building access node, it is automatically added to the network at the center of the building.
- `ugv_closest_node_connection=True`: Connects the building access points to the nearest node. These edges are temporary and are recreated each time the graph is updated. They are excluded from virtual path calculations and visualizations.
- `ugv_virtual=True`: This attribute indicates that the edge is a virtual edge, used for connecting the graph to building premises.

## Todos

- Optimize caching.
- Update edge lengths when a new edge is added. Length is now calculated for each edge on every update.
- Implement saving and loading of the graph and buildings to enable persistence across sessions.
- Disable the screen from going dark when the app is doing heavy computations. (Maybe with CSS or JavaScript?)
- Modify parameters for the pathfinding algorithm from the UI. Currently, the parameters are set from the config.py file and betweeness centrality factor can be set via query params, e.g. `http://localhost:8501/?cb=0.5`.
- In some cases, the end of the virtual path connects to itself instead of connecting to the road when the second to last node point is very close to the building access point. This is because the second to last node is closer to the building access point than the last node. (The logic connects the end of the path to the closest node.) This can be fixed by adding the ends of the paths before adding the virtual path nodes and edges, so that the path nodes are not considered candidates for the closest node connection.
