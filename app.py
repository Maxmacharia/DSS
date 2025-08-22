
import streamlit as st
import ee
import geopandas as gpd
import os
from shapely.geometry import mapping
import folium

from gee_client import (
    init_ee, get_kajiado_roi, build_monthly_rainfall, build_monthly_mean_image,
    build_anomaly_collection, build_pnr_collection, build_spi_collection,
    build_heavy_rain, build_annual_drought_flood, get_tile_url_for_image
)
from map_utils import build_base_map, add_ee_layer, display_map_in_streamlit
from charts import fetch_time_series_mean, plot_time_series

st.set_page_config(layout='wide', page_title='GEE DSS - Nairobi metropolitan')
st.title('Droughts and Floods Decision Support System')

# 🔑 EE Initialization
SERVICE_ACCOUNT = os.getenv("EE_SERVICE_ACCOUNT")
KEY_FILE = os.getenv("EE_KEY_FILE", "service_account.json")  # ensure this file exists in your repo

ee_ready = False
try:
    if SERVICE_ACCOUNT and os.path.exists(KEY_FILE):
        init_ee(SERVICE_ACCOUNT, KEY_FILE)
        ee_ready = True
        st.sidebar.success("Earth Engine initialized with service account")
    else:
        ee.Initialize()
        ee_ready = True
        st.sidebar.success("Earth Engine initialized with local credentials")
except Exception as e:
    st.sidebar.error(f"Failed to initialize Earth Engine: {e}")

# Sidebar: query inputs
st.sidebar.header('Query Inputs')
year = st.sidebar.number_input('Year to visualise (single year)', min_value=2015, max_value=2025, value=2023, step=1)
month = st.sidebar.selectbox('Month (for climatology & anomaly)', list(range(1, 13)), index=2)

# ROI controls
roi_choice = st.sidebar.radio(
    'ROI option',
    ['Default: Nairobi metropolitan', 'Upload GeoJSON/SHAPEFILE(not implemented)', 'Draw polygon (not implemented)']
)
uploaded_roi = None
if roi_choice == 'Upload GeoJSON/SHAPEFILE':
    uploaded = st.sidebar.file_uploader('Upload GeoJSON or ZIP Shapefile', type=['geojson', 'json', 'zip', 'shp'])
    if uploaded is not None:
        try:
            gdf = gpd.read_file(uploaded)
            uploaded_roi = ee.FeatureCollection(gdf.geometry.__geo_interface__)
        except Exception as e:
            st.sidebar.error(f'Failed to read file: {e}')

# Build or load ROI
roi_fc = uploaded_roi if uploaded_roi is not None else get_kajiado_roi()

# Main compute & caching
@st.cache_data(show_spinner=True)
def compute_collections(_roi):
    monthly_rain = build_monthly_rainfall(_roi)
    monthly_mean_img = build_monthly_mean_image(monthly_rain)
    anomaly_coll = build_anomaly_collection(monthly_rain, monthly_mean_img)
    pnr_coll = build_pnr_collection(monthly_rain, monthly_mean_img)
    spi_coll = build_spi_collection(monthly_rain, monthly_mean_img)
    heavy = build_heavy_rain(_roi.geometry())
    annual = build_annual_drought_flood(spi_coll)
    return {
        'monthly_rain': monthly_rain,
        'monthly_mean_img': monthly_mean_img,
        'anomaly_coll': anomaly_coll,
        'pnr_coll': pnr_coll,
        'spi_coll': spi_coll,
        'heavy': heavy,
        'annual': annual
    }

if ee_ready:
    coll = compute_collections(roi_fc)
    st.sidebar.success('Collections ready')

    # Map display area
    st.subheader('Map')
    m = build_base_map()

    # Toggleable layers
    st.sidebar.write('Toggle layers to add to the map')
    show_monthly_clim = st.sidebar.checkbox('Monthly Climatology (selected month)', True)
    show_spi = st.sidebar.checkbox('SPI (selected year)', True)
    show_anomaly = st.sidebar.checkbox('Anomaly (selected year & month)', True)
    show_heavy = st.sidebar.checkbox('Heavy Rain Days (>50mm) (selected year)', True)
    show_drought = st.sidebar.checkbox('Annual Drought Frequency (selected year)', True)
    show_flood = st.sidebar.checkbox('Annual Flood Frequency (selected year)', True)

    # Visualization params
    clim_vis = {'min': 0, 'max': 200, 'palette': ['white', 'blue']}
    spi_vis = {'min': -2, 'max': 2, 'palette': ['brown', 'white', 'blue']}
    anomaly_vis = {'min': -100, 'max': 100, 'palette': ['red', 'white', 'green']}
    heavy_vis = {'min': 0, 'max': 20, 'palette': ['white', 'purple']}
    drought_vis = {'min': 0, 'max': 12, 'palette': ['white', 'orange', 'red']}
    flood_vis = {'min': 0, 'max': 12, 'palette': ['white', 'lightblue', 'blue']}

    # Monthly climatology
    month_str = f"prec_{int(month):02d}"
    if coll['monthly_mean_img'].bandNames().size().getInfo() > 0:
        clim_img = coll['monthly_mean_img'].select(month_str).clip(roi_fc.geometry())
        if show_monthly_clim:
            url = get_tile_url_for_image(clim_img, clim_vis)
            add_ee_layer(m, url, f'Climatology Month {month}')

    # SPI
    if coll['spi_coll'].size().getInfo() > 0 and show_spi:
        spi_year = coll['spi_coll'].filter(ee.Filter.eq('year', int(year))).mean().clip(roi_fc.geometry())
        url = get_tile_url_for_image(spi_year, spi_vis)
        add_ee_layer(m, url, f'SPI Mean {year}')

    # Anomaly
    if coll['anomaly_coll'].size().getInfo() > 0 and show_anomaly:
        an_img = coll['anomaly_coll'].filter(ee.Filter.eq('year', int(year))).filter(ee.Filter.eq('month', int(month))).first()
        if an_img and an_img.bandNames().size().getInfo() > 0:
            an_img = an_img.clip(roi_fc.geometry())
            url = get_tile_url_for_image(an_img, anomaly_vis)
            add_ee_layer(m, url, f'Anomaly {year} Month {month}')

    # Heavy Rain
    if coll['heavy'].size().getInfo() > 0 and show_heavy:
        heavy_year = coll['heavy'].filter(ee.Filter.calendarRange(int(year), int(year), 'year')).sum().clip(roi_fc.geometry())
        url = get_tile_url_for_image(heavy_year, heavy_vis)
        add_ee_layer(m, url, f'HeavyRain Days {year}')

    # Drought & Flood
    if coll['annual'].size().getInfo() > 0 and (show_drought or show_flood):
        year_img = coll['annual'].filter(ee.Filter.eq('year', int(year))).first()
        if year_img and year_img.bandNames().size().getInfo() > 0:
            year_img = year_img.clip(roi_fc.geometry())
            if show_drought:
                url = get_tile_url_for_image(year_img.select('drought_freq'), drought_vis)
                add_ee_layer(m, url, f'Drought Frequency {year}')
            if show_flood:
                url = get_tile_url_for_image(year_img.select('flood_freq'), flood_vis)
                add_ee_layer(m, url, f'Flood Frequency {year}')

    folium.LayerControl().add_to(m)
    display_map_in_streamlit(m)

    # Charts stacked vertically in one column
    st.subheader('Time Series Charts (2015-2025)')

    # Rainfall Anomaly
    st.write('Rainfall Anomaly')
    anomaly_df = fetch_time_series_mean(coll['anomaly_coll'], roi_fc.geometry(), band_name='anomaly')
    if not anomaly_df.empty:
        fig = plot_time_series(anomaly_df, 'Rainfall Anomaly - Nairobi Metro (2015–2025)', 'Anomaly (mm)')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write('No anomaly data')

    # SPI Monthly Mean
    st.write('SPI Monthly Mean')
    spi_df = fetch_time_series_mean(coll['spi_coll'], roi_fc.geometry(), band_name='spi')
    if not spi_df.empty:
        fig2 = plot_time_series(spi_df, 'SPI Monthly Mean - Nairobi Metro (2015–2025)', 'SPI')
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.write('No SPI data')

    # Monthly Rainfall
    st.write('Monthly Rainfall')
    rain_df = fetch_time_series_mean(coll['monthly_rain'], roi_fc.geometry(), band_name='precipitation')
    if rain_df.empty:
        rain_df = fetch_time_series_mean(coll['monthly_rain'], roi_fc.geometry(), band_name='sum')
    if not rain_df.empty:
        fig3 = plot_time_series(rain_df, 'Monthly Rainfall - Nairobi Metro (2015–2025)', 'Rainfall (mm)')
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.write('No monthly rainfall data')

else:
    st.info('Please set up your Earth Engine service account & key file in Streamlit Cloud.')
