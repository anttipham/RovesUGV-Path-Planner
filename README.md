# RovesUGV

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

The graph is built using OSMnx, and building access nodes are added to the graph in the center of each building. Access nodes are connected to the nearest graph nodes with edges attributed with `temporary_connection=True`. Temporary connections are recreated each time the graph is updated.

## Todos

- Optimize caching.
- Update edge lengths when a new edge is added. Length is now calculated for each edge on every update.
- Implement saving and loading of the graph and buildings to enable persistence across sessions.
- Disable the screen from going dark when the app is doing heavy computations. (Maybe with CSS or JavaScript?)
