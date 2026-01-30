import streamlit as st
from streamlit_folium import st_folium

import config
import map
import osm_gis
import path


def main():
    # Initialize Streamlit app
    st.set_page_config(page_title=config.APP_TITLE, layout="wide")
    st.title(config.APP_TITLE)

    # Create graph
    G = osm_gis.create_road_graph()
    path.add_weight(G)
    path.add_centrality(G)

    # Load and build the map
    m = map.build_map(G)

    # Display the map in Streamlit and capture interaction data
    st_data = st_folium(
        m,
        use_container_width=True,
        returned_objects=["last_active_drawing"],
    )
    st.text("Map interaction data:")
    st.write(st_data)

    # Edit graph
    clicked_object = st_data["last_active_drawing"]
    if clicked_object and clicked_object["geometry"]["type"]:
        id_str: str = clicked_object["id"]
        id = int(id_str.lstrip("('way', ").rstrip(")"))
        print(id)
        print(G.nodes[id])


if __name__ == "__main__":
    main()
