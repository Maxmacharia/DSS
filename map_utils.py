import folium
from streamlit_folium import st_folium

def build_base_map(center=[-2.1, 37.8], zoom_start=8):
    m = folium.Map(location=center, zoom_start=zoom_start)
    return m


def add_ee_layer(folium_map, tile_url, name, opacity=1.0, overlay=True):
    folium.TileLayer(tiles=tile_url, attr='Google Earth Engine', name=name, overlay=overlay, opacity=opacity).add_to(folium_map)


def display_map_in_streamlit(folium_map, width=700, height=500):
    # returns the folium map component
    return st_folium(folium_map, width=width, height=height)
