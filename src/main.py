import folium
import streamlit as st
from streamlit_folium import st_folium

import map

css = """
    <style>
    .leaflet-div-icon.leaflet-editing-icon {
        border-radius: 50%;
    }
    </style>
"""

if __name__ == "__main__":
    # Initialize Streamlit app
    st.set_page_config(page_title="UGV Roves", layout="wide")

    # Load and build the map
    m = map.build_map()
    # Custom CSS to style the edit vertices as circles
    m.get_root().header.add_child(folium.Element(css))

    # Display the map in Streamlit and capture interaction data
    st_data = st_folium(m, use_container_width=True)
    st.text("Map interaction data:")
    st.write(st_data)
