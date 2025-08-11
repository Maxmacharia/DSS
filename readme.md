```
# Streamlit GEE Decision Support System (Kajiado)

## Overview
This Streamlit app queries Google Earth Engine dynamically using a service account JSON key. Users enter a single year and pick a month (for climatology/anomaly), view toggleable Leaflet (folium) map layers and three Plotly charts (fixed 2015-2025). ROI defaults to Kajiado with options to upload shapefile/GeoJSON or draw a polygon.

## Setup
1. Create a GCP service account with access to the Earth Engine project and enable the Earth Engine API.
2. Download the service account JSON and place it at `assets/service_account.json`.
3. Install:
   ```bash
   pip install -r requirements.txt
   ```
4. Run locally:
   ```bash
   streamlit run app.py
   ```

## Notes
- Caching per (ROI, year, month, layer) is implemented via Streamlit cache.
- No exporting enabled in this initial scaffold.
```

---
