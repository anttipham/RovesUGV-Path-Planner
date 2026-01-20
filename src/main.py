import streamlit as st
from streamlit_folium import st_folium

import map

if __name__ == "__main__":
    m = map.build_map()
    st_data = st_folium(m, use_container_width=True)
