"""
Handles streamlit stuff
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
        ox.distance.add_edge_lengths(G)
        path.add_weight(G)
        path.add_centrality(G)
        st.session_state["graph"] = G
        st.session_state["update_graph"] = False
    G: nx.MultiDiGraph = st.session_state["graph"]

    # Load and build the map
    m = map.build_map(G)

    # Display nodes in map for debugging
    # gdf = ox.graph_to_gdfs(G, nodes=True, edges=False)
    # folium.GeoJson(
    #     gdf,
    #     style_function=lambda _: {
    #         "fillColor": "blue",
    #         "color": "black",
    #         "weight": 3,
    #         "fillOpacity": 0.5,
    #     },
    # ).add_to(m)

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
    st.text("Map interaction data:")
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
