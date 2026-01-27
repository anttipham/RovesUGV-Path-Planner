import geopandas as gpd
import osmnx as ox
import networkx as nx
import shapely
import shapely.ops

import config


def get_building_geometries():
    # Fetch building geometries from OSMnx
    gdf = ox.features_from_place(
        config.PLACE_NAME,
        {"building": True},
    )
    return gdf


def create_road_graph():
    # Add undirected OSMnx graph data to draw plugin
    graph = ox.graph.graph_from_place(
        config.PLACE_NAME,
        network_type="all",
        retain_all=True,
    )
    return graph


def add_access_ways(
    graph: nx.MultiDiGraph, building_geometries: gpd.GeoDataFrame
) -> None:
    node_id = max(graph.nodes)
    access_ways: list[tuple[int, int, int, int]] = []
    # Find the nearest point to be used as access way for each building
    for centroid in building_geometries.centroid:
        node_id += 1
        # Distance to nearest node
        nearest_node = ox.distance.nearest_nodes(graph, centroid.x, centroid.y)
        access_ways.append((node_id, centroid.y, centroid.x, nearest_node))
        # nearest_node_y = graph.nodes[nearest_node]["y"]
        # nearest_node_x = graph.nodes[nearest_node]["x"]
        # node_distance = ox.distance.euclidean(
        #     centroid.y,
        #     centroid.x,
        #     nearest_node_y,
        #     nearest_node_x,
        # )
        # print(node_distance)

        # # Distance to nearest edge
        # nearest_edge = ox.distance.nearest_edges(
        #     graph, centroid.x, centroid.y, return_dist=True
        # )
        # print(nearest_edge)
        # edge_distance = float("inf")
        # if "geometry" in graph.edges[nearest_edge]:
        #     edge_geometry: shapely.Point = graph.edges[nearest_edge]["geometry"]
        #     edge_distance = edge_geometry.distance(centroid)  # TODO
        #     nearest_point = shapely.ops.nearest_points(edge_geometry, centroid)
        # print(edge_distance)

        # If the nearest geometry is a node,
        # just connect the building centroid to the road

        # if node_distance <= edge_distance:
        # else:
        #     # Add a middle node to the edge
        #     middle_node = f"{nearest_point.y},{nearest_point.x}"
        #     graph.add_node(middle_node, y=nearest_point.y, x=nearest_point.x)
        #     # Connect middle node
        #     geom1, geom2 = shapely.ops.split(edge_geometry, nearest_point).geoms
        #     print(dict(graph.edges[nearest_edge].values()))
        #     # graph.add_edge(node_name, middle_node, graph.edges[nearest_edge].)
    for node1, y, x, node2 in access_ways:
        # Add building centroid to graph
        graph.add_node(node1, y=y, x=x)
        graph.add_edge(node1, node2)
        graph.add_edge(node2, node1)
    ox.distance.add_edge_lengths(graph)
