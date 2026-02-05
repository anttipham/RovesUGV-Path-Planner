"""
Handles streamlit stuff
"""

import time

import folium
import networkx as nx
import streamlit as st
from streamlit_folium import st_folium

import config
import map
import osm_gis
import path


def choose_building():
    G: nx.MultiDiGraph = st.session_state["graph"]
    clicked_object = st.session_state["map"]["last_active_drawing"]
    # Update properties when clicked
    if clicked_object and clicked_object["geometry"]["type"] == "Polygon":
        id = int(clicked_object["id"].lstrip("('way', ").rstrip(")"))
        G.nodes[id]["chosen_time"] = time.time()


def main():
    # Initialize Streamlit app
    st.set_page_config(page_title=config.APP_TITLE, layout="wide")
    st.title(config.APP_TITLE)

    # Create graph
    if "graph" not in st.session_state:
        G = osm_gis.create_road_graph()
        path.add_weight(G)
        path.add_centrality(G)
        st.session_state["graph"] = G
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
        on_change=choose_building,
    )
    st.text("Map interaction data:")
    st.write(st.session_state)


if __name__ == "__main__":
    main()
