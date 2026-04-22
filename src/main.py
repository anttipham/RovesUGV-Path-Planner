"""
Streamlit application entrypoint for RovesUGV Path Planner.

The main module orchestrates the Streamlit UI lifecycle, manages the road graph,
handles map interactions, and displays routing diagnostics.

Session State Keys
------------------
map : dict
    Payload from streamlit-folium containing:

    - last_active_drawing: Most recent map interaction (when feature is clicked).
        - bbox: The bounding box of the drawn object.
        - geometry: The GeoJSON geometry of the drawn object.
        - id: The OSM feature ID if the drawn object corresponds to an OSM feature
        - properties: Additional properties of the drawn object, such as OSM tags for buildings.
        - type: The type of the drawn object, e.g. "Feature".

graph : nx.MultiDiGraph
    Current routing graph with all computed attributes and paths.

update_graph : bool
    Flag indicating whether graph attributes and building path pairs need recomputation.
"""

import time

import folium
import networkx as nx
import streamlit as st
from streamlit_folium import st_folium

import config
import map
import graph
import path


def handle_map_click():
    """
    Process the latest map interaction event from Streamlit session state.

    Handles two types of interactions:

    1. **Building polygon click** (Polygon geometry with id):
       - Marks building as selected by updating `chosen_time` node attribute.

    2. **Point marker placement** (Point geometry):
       - Triggers computation of virtual premise paths from raster imagery.
       - Sets `update_graph` flag to refresh centrality and path pairs.
    """
    clicked_object = st.session_state["map"]["last_active_drawing"]

    # Nothing is clicked
    if not clicked_object:
        return

    if clicked_object["geometry"]["type"] == "Polygon":
        # Building is clicked
        if "id" in clicked_object:
            id = int(clicked_object["id"].lstrip("('way', ").rstrip(")"))
            G: nx.MultiDiGraph = st.session_state["graph"]
            G.nodes[id]["chosen_time"] = time.time()
        else:
            # Restriction zone is created
            print("Restriction zone created, but not linked to any building. Ignoring.")
            print(clicked_object)

    # A marker is placed
    if clicked_object["geometry"]["type"] == "Point":
        path.calc_premise_path(
            st.session_state["graph"], clicked_object["geometry"]["coordinates"]
        )
        st.session_state["update_graph"] = True


def main():
    """
    Initialize Streamlit UI, maintain graph lifecycle, and render map with diagnostics.

    Workflow:
    1. Parse centrality factor from query parameters (or use default).
    2. Initialize/fetch graph from session state.
    3. Recompute building paths and centrality when needed.
    4. Render interactive Folium map and capture interactions.
    5. Display selected path cost breakdown if two buildings are chosen.
    """
    # Allow centrality factor override via query parameter, e.g. ?cb=0.5
    cost_centrality_factor = st.query_params.get("cb", config.COST_CENTRALITY_FACTOR)
    config.COST_CENTRALITY_FACTOR = float(cost_centrality_factor)

    # Initialize Streamlit page
    st.set_page_config(
        page_title=f"{config.APP_TITLE} CB_factor={config.COST_CENTRALITY_FACTOR}",
        layout="wide",
    )
    st.title(f"{config.APP_TITLE} CB_factor={config.COST_CENTRALITY_FACTOR}")

    # Build graph once per session
    if "graph" not in st.session_state:
        G = graph.create_road_graph()
        st.session_state["graph"] = G
        st.session_state["update_graph"] = True

    # Refresh derived graph data when requested
    if st.session_state["update_graph"]:
        G: nx.MultiDiGraph = st.session_state["graph"]

        path.update_building_access(G)
        graph.add_custom_attributes(G)

        if config.COST_CENTRALITY_FACTOR == 0:
            path.add_all_building_path_pairs(G)
            path.add_betweenness_centrality(G)
        else:
            # Recalculate paths and centrality until convergence
            # (max centrality no longer changes between iterations)
            old_centrality = G.graph.get("ugv_max_centrality", -1)
            i = 0
            while old_centrality != G.graph.get("ugv_max_centrality", -2):
                old_centrality = G.graph.get("ugv_max_centrality", -2)
                path.add_all_building_path_pairs(G)
                path.add_betweenness_centrality(G)
                i += 1
                print(
                    f"Centrality iteration {i}, "
                    f"max centrality: {G.graph['ugv_max_centrality']}"
                )

        st.session_state["graph"] = G
        st.session_state["update_graph"] = False
    G: nx.MultiDiGraph = st.session_state["graph"]

    # Load and build the map
    m = map.build_map(G)

    # Display the map in Streamlit and capture interaction data
    st_data = st_folium(
        m,
        key="map",
        use_container_width=True,
        returned_objects=["last_active_drawing"],
        feature_group_to_add=path.show_path(G),
        on_change=handle_map_click,
        layer_control=folium.LayerControl(),
    )

    # Debug output: selected route and per-edge costs
    ids = path.get_chosen_building_nodes(G)
    if len(ids) == 2:
        source, target = ids[0], ids[1]
        path_data = G.graph["ugv_all_building_path_pairs"].get((source, target))

        total_cost = sum(path.calculate_cost(G, (u, v, key)) for u, v, key in path_data)

        st.header("Path details:")

        st.write(f"max_centrality: `{G.graph['ugv_max_centrality']}`")

        st.write(f"Total path cost: `{total_cost}`")
        st.write("---")

        for u, v, key in path_data:
            st.write(f"Cost {u} -> {v}: `{path.calculate_cost(G, (u, v, key))}`")
            st.text(f"Node {u}: {G.nodes[u]}")
            st.text(f"Edge {u} -> {v}: {G.edges[u, v, key]}")
            st.text(f"Node {v}: {G.nodes[v]}")
            st.write("---")

    st.header("Map interaction data:")
    st.write(st.session_state)


if __name__ == "__main__":
    main()
