import ee
import pandas as pd
from datetime import datetime
import plotly.express as px

def fetch_time_series_mean(image_collection, roi_geometry, band_name='anomaly', scale=5000):
    """Fetch time-series mean values for an ImageCollection, safely handling empty collections."""
    if image_collection.size().getInfo() == 0:
        return pd.DataFrame(columns=['date', 'value'])

    def reducer_fn(img):
        band_count = img.bandNames().size()
        return ee.Algorithms.If(
            band_count.gt(0),
            ee.Feature(
                None,
                {
                    'date': ee.Date(img.get('system:time_start')).format('YYYY-MM-dd'),
                    'value': img.reduceRegion(ee.Reducer.mean(), roi_geometry, scale).get(band_name)
                }
            ),
            ee.Feature(None, {'date': None, 'value': None})
        )

    feats = image_collection.map(lambda img: reducer_fn(img)).filter(ee.Filter.notNull(['value'])).getInfo()

    records = []
    for f in feats['features']:
        props = f['properties']
        if props['date'] is not None:
            records.append({'date': props['date'], 'value': props['value']})

    df = pd.DataFrame(records)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
    return df

def plot_time_series(df, title, yaxis_title):
    fig = px.line(df, x='date', y='value', title=title, markers=True)
    fig.update_layout(yaxis_title=yaxis_title, xaxis_title='Date')
    return fig
