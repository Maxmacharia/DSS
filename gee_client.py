import ee
import json
from pathlib import Path

# Initialize Earth Engine with a service account key JSON
def init_ee(service_account_email: str, key_file: str):
    if ee.data._credentials is None:
        credentials = ee.ServiceAccountCredentials(service_account_email, key_file)
        ee.Initialize(credentials)
    else:
        try:
            ee.Initialize()
        except Exception:
            credentials = ee.ServiceAccountCredentials(service_account_email, key_file)
            ee.Initialize(credentials)

# ROI helpers
def get_kajiado_roi():
    admin = ee.FeatureCollection("FAO/GAUL_SIMPLIFIED_500m/2015/level2")
    roi = admin.filter(ee.Filter.eq('ADM2_NAME', 'Kajiado'))
    return roi

# Convert month number to two-digit string
def mm(m):
    return ee.Number(m).format('%02d')

# Helper to filter out images with 0 bands
def filter_empty(img):
    return ee.Algorithms.If(
        img.bandNames().size().gt(0),
        img,
        None
    )

# Build monthly_rainfall ImageCollection
def build_monthly_rainfall(roi):
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY") \
        .filterBounds(roi) \
        .filterDate('1981-01-01', '2025-12-31')

    years = ee.List.sequence(1981, 2025)
    months = ee.List.sequence(1, 12)

    def per_year(year):
        year = ee.Number(year)
        def per_month(m):
            m = ee.Number(m)
            start = ee.Date.fromYMD(year, m, 1)
            end = start.advance(1, 'month')
            monthly = chirps.filterDate(start, end).sum()
            return ee.Algorithms.If(
                monthly.bandNames().size().gt(0),
                monthly.set({
                    'system:time_start': start.millis(),
                    'year': year,
                    'month': m
                }),
                None
            )
        return months.map(per_month)

    coll = ee.ImageCollection(years.map(per_year).flatten()) \
        .filter(ee.Filter.notNull(['system:time_start']))
    return coll

# Monthly mean baseline 1981-2015
def build_monthly_mean_image(monthly_rainfall):
    baseline = monthly_rainfall.filter(ee.Filter.calendarRange(1981, 2015, 'year'))
    months = ee.List.sequence(1, 12)

    def per_m(m):
        m = ee.Number(m)
        monthly_images = baseline.filter(ee.Filter.eq('month', m))
        return monthly_images.mean().set('month', m).set(
            'system:time_start', ee.Date.fromYMD(2000, m, 1).millis()
        )

    monthly_mean = ee.ImageCollection(months.map(per_m))
    monthly_mean_image = monthly_mean.toBands().rename([
        'prec_01','prec_02','prec_03','prec_04','prec_05','prec_06',
        'prec_07','prec_08','prec_09','prec_10','prec_11','prec_12'
    ])
    return monthly_mean_image

# Safely select a band or return zero image
def safe_select(image, band_name):
    bands = image.bandNames()
    return ee.Image(
        ee.Algorithms.If(
            bands.contains(band_name),
            image.select(band_name),
            ee.Image.constant(0).rename(band_name)
        )
    )

# Build anomaly collection
def build_anomaly_collection(monthly_rainfall, monthly_mean_image):
    def anomaly_fn(img):
        img = ee.Image(img)
        m = ee.Number(img.get('month')).format('%02d')
        band_name = ee.String('prec_').cat(m)
        clim = safe_select(monthly_mean_image, band_name)
        return img.subtract(clim) \
            .rename('anomaly') \
            .copyProperties(img, ['system:time_start', 'year', 'month']) \
            .set('month', img.get('month'))

    return monthly_rainfall \
        .filter(ee.Filter.calendarRange(2015, 2025, 'year')) \
        .map(lambda i: ee.Image(filter_empty(i))) \
        .filter(ee.Filter.notNull(['system:time_start'])) \
        .map(anomaly_fn)

# Build PNR collection
def build_pnr_collection(monthly_rainfall, monthly_mean_image):
    def pnr_fn(img):
        img = ee.Image(img)
        m = ee.Number(img.get('month')).format('%02d')
        band_name = ee.String('prec_').cat(m)
        clim = safe_select(monthly_mean_image, band_name)
        return img.divide(clim).multiply(100) \
            .rename('pnr') \
            .copyProperties(img, ['system:time_start', 'year', 'month']) \
            .set('month', img.get('month'))

    return monthly_rainfall \
        .filter(ee.Filter.calendarRange(2015, 2025, 'year')) \
        .map(lambda i: ee.Image(filter_empty(i))) \
        .filter(ee.Filter.notNull(['system:time_start'])) \
        .map(pnr_fn)

# Build SPI collection
def build_spi_collection(monthly_rainfall, monthly_mean_image):
    months = ee.List.sequence(1, 12)

    def per_m(m):
        m = ee.Number(m)
        month_data = monthly_rainfall.filter(ee.Filter.calendarRange(1981, 2015, 'year')) \
                                     .filter(ee.Filter.eq('month', m))
        return month_data.reduce(ee.Reducer.stdDev()).set('month', m).set(
            'system:time_start', ee.Date.fromYMD(2000, m, 1).millis()
        )

    clim_stddev = ee.ImageCollection(months.map(per_m)).toBands().rename([
        'prec_01','prec_02','prec_03','prec_04','prec_05','prec_06',
        'prec_07','prec_08','prec_09','prec_10','prec_11','prec_12'
    ])

    def spi_fn(img):
        img = ee.Image(img)
        m = ee.Number(img.get('month')).format('%02d')
        band_name = ee.String('prec_').cat(m)
        clim_mean = safe_select(monthly_mean_image, band_name)
        clim_std = safe_select(clim_stddev, band_name)
        return img.subtract(clim_mean).divide(clim_std) \
            .rename('spi') \
            .copyProperties(img, ['system:time_start', 'year', 'month']) \
            .set('month', img.get('month'))

    return monthly_rainfall \
        .filter(ee.Filter.calendarRange(2015, 2025, 'year')) \
        .map(lambda i: ee.Image(filter_empty(i))) \
        .filter(ee.Filter.notNull(['system:time_start'])) \
        .map(spi_fn)

# Heavy rain days
def build_heavy_rain(roi):
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY") \
                .filterBounds(roi) \
                .filterDate('2015-01-01', '2025-08-11')
    heavy = chirps.map(lambda img: img.gt(50).rename('heavyRain').copyProperties(img, ['system:time_start']))
    return heavy

# Annual drought & flood frequency
def build_annual_drought_flood(spi_collection):
    years = ee.List.sequence(2015, 2025)
    def per_year(y):
        y = ee.Number(y)
        yearly_spi = spi_collection.filter(ee.Filter.eq('year', y))
        drought_mask = yearly_spi.map(lambda img: img.lte(-1.5).selfMask()).sum().rename('drought_freq')
        flood_mask = yearly_spi.map(lambda img: img.gte(1.5).selfMask()).sum().rename('flood_freq')
        return drought_mask.addBands(flood_mask).set('year', y).set(
            'system:time_start', ee.Date.fromYMD(y, 1, 1).millis()
        )
    return ee.ImageCollection(years.map(per_year))

# Utility to get tile URL
def get_tile_url_for_image(img, vis_params):
    mapid_dict = ee.Image(img).getMapId(vis_params)
    return mapid_dict['tile_fetcher'].url_format
