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
