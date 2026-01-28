import streamlit as st
from streamlit_folium import st_folium

import config
import map


def main():
    # Initialize Streamlit app
    st.set_page_config(page_title=config.APP_TITLE, layout="wide")
    st.title(config.APP_TITLE)

    # Load and build the map
    m = map.build_map()

    # Display the map in Streamlit and capture interaction data
    st_data = st_folium(
        m,
        use_container_width=True,
        returned_objects=["last_active_drawing"],
    )
    st.text("Map interaction data:")
    st.write(st_data)


if __name__ == "__main__":
    main()
