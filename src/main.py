"""
Handles streamlit stuff.

st.session state structure:
{
    "map": {
        "last_active_drawing": {
            "bbox": [...],
            "geometry": {
                "type": "...",
                "coordinates": [...]
            },
            "id": "..."
            "properties": {...},
            "type": "Feature"
        }
    },
    "graph": <networkx graph object>,
    "update_graph": True/False
}
"""

import time

import folium
import networkx as nx
import streamlit as st
from streamlit_folium import st_folium
import osmnx as ox

import config
import map
import osm_gis
import path


def handle_map_click():
    """
    Handle map click events by checking the last active drawing in the session state.
    """
    clicked_object = st.session_state["map"]["last_active_drawing"]

    # Nothing is clicked
    if not clicked_object:
        return

    # Building is clicked
    if clicked_object["geometry"]["type"] == "Polygon" and "id" in clicked_object:
        id = int(clicked_object["id"].lstrip("('way', ").rstrip(")"))
        G: nx.MultiDiGraph = st.session_state["graph"]
        G.nodes[id]["chosen_time"] = time.time()

    # A marker is placed
    if clicked_object["geometry"]["type"] == "Point":
        path.calc_premise_path(
            st.session_state["graph"], clicked_object["geometry"]["coordinates"]
        )
        st.session_state["update_graph"] = True


def main():
    # Initialize Streamlit app
    st.set_page_config(page_title=config.APP_TITLE, layout="wide")
    st.title(config.APP_TITLE)

    # Create graph
    if "graph" not in st.session_state:
        G = osm_gis.create_road_graph()
        st.session_state["graph"] = G
        st.session_state["update_graph"] = True

    # Update graph
    if st.session_state["update_graph"]:
        G: nx.MultiDiGraph = st.session_state["graph"]

        path.update_building_access(G, osm_gis.get_building_gdf())
        osm_gis.add_custom_attributes(G)

        # path.add_all_building_path_pairs(G)
        # path.add_betweenness_centrality(G)

        # Recalculate paths and centrality until the paths converge, i.e. centrality
        # doesn't change anymore
        old_centrality = G.graph.get("max_centrality", -1)
        i = 0
        while old_centrality != G.graph.get("max_centrality", -2):
            old_centrality = G.graph.get("max_centrality", -2)
            path.add_all_building_path_pairs(G)
            path.add_betweenness_centrality(G)
            i += 1
            print(
                f"Centrality iteration {i}, max centrality: {G.graph['max_centrality']}"
            )

        st.session_state["graph"] = G
        st.session_state["update_graph"] = False
    G: nx.MultiDiGraph = st.session_state["graph"]

    # Load and build the map
    m = map.build_map(G)

    # Display nodes in map for debugging
    H = G.subgraph(
        [node for node, crossing in G.nodes(data="ugv_crossing") if crossing == True]
    )
    gdf = ox.graph_to_gdfs(H, nodes=True, edges=False)
    folium.GeoJson(
        gdf,
        style_function=lambda _: {
            "fillColor": "blue",
            "color": "black",
            "weight": 3,
            "fillOpacity": 0.5,
        },
    ).add_to(m)

    # Presentation markers
    # markers = folium.FeatureGroup("Yritykset")
    # for name, coords in config.MARKERS.items():
    #     node = ox.nearest_nodes(G, coords[1], coords[0])
    #     node_attr = G.nodes[node]
    #     folium.Marker((node_attr["y"], node_attr["x"]), tooltip=name).add_to(markers)
    # markers.add_to(m)

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

    # Debug prints

    # Path costs
    ids = path.get_chosen_building_nodes(G)
    if len(ids) == 2:
        source, target = ids[0], ids[1]
        path_data = G.graph["all_building_path_pairs"].get((source, target))

        total_cost = sum(path.calculate_cost(G, u, v) for u, v, _ in path_data)

        st.header("Path details:")

        st.write(f"max_centrality: `{G.graph['max_centrality']}`")

        st.write(f"Total path cost: `{total_cost}`")

        for u, v, key in path_data:
            st.write(f"{u} -> {v}: `{path.calculate_cost(G, u, v)}`")
            st.text(G.nodes[u])
            st.text(G.edges[u, v, key])
            st.text(G.nodes[v])

    # Write path cost
    cost = G.graph["all_building_path_pairs"]

    st.header("Map interaction data:")
    st.write(st.session_state)
    # st_session_state = {
    #     "map": {
    #         "last_active_drawing": {
    #             "type": "Feature",
    #             "properties": {"id": 1774776370760},
    #             "geometry": {"type": "Point", "coordinates": [22.875037, 62.786973]},
    #         }
    #     },
    #     "graph": "<networkx.classes.multidigraph.MultiDiGraph object at 0x00000191F0607E00>",
    # }


if __name__ == "__main__":
    main()
