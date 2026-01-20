import streamlit as st
from streamlit_folium import st_folium

import map

if __name__ == "__main__":
    st.set_page_config(page_title="UGV Roves", layout="wide")
    m = map.build_map()
    st_data = st_folium(m, use_container_width=True)
    st.text("Map interaction data:")
    st.write(st_data)
