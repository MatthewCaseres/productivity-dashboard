import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

@st.cache(ttl=3600)
def loadData(DATA_URL):
  csvFromSheet = '/'.join(DATA_URL.split('/')[:-1] + ['export?format=csv'])
  df = pd.read_csv(csvFromSheet, parse_dates=['start', 'end'])
  rawData = df[df['start'] != df['end']].sort_values('start')
  return rawData

def fillDays(rawData):
  fillAfter = rawData.loc[rawData['start'].shift(-1) != rawData['end'], 'end']
  NAsDict = {'activity': ["N/A"]*len(fillAfter), "start": fillAfter, "end": [None]*len(fillAfter)}
  NAs = pd.DataFrame(NAsDict)[:-1]

  # These are for the beginning and end
  beginningEndDict = {
      'activity': ["N/A"]*2, 
      "start": [min(rawData['start']).floor('D'), max(rawData['end'])], 
      "end": [min(rawData['start']), max(rawData['end']).ceil('D')]
  }
  beginningEnd = pd.DataFrame(beginningEndDict)

  # This should come after everything is partitioned
  midnightSeries = pd.date_range(min(rawData['start']).ceil('D'), max(rawData['end']).floor('D'))
  midnightsDict = {'activity': [None]*len(midnightSeries), 'start': midnightSeries, 'end': [None]*len(midnightSeries)}
  midnights = pd.DataFrame(midnightsDict)

  # combine the NA with the non-NA
  all = pd.concat([rawData, NAs, beginningEnd, midnights], ignore_index=True)
  all = all.sort_values('start')
  # Fill NA for added rows with correct values
  all['end'] = all['end'].fillna(all['start'].shift(-1))
  all['activity'] = all['activity'].fillna(method='ffill')
  # For days crossing over, truncate at midnight
  all.loc[all['start'].dt.day != all['end'].dt.day, 'end'] = all['start'].dt.ceil('D')
  all.loc[all['start'] == all['end'], 'end'] = all['start'].shift(-1)
  all['Hour'] = (all['end'] - all['start']).dt.total_seconds()/3600
  all['day'] = all['start'].dt.floor('D')
  return all

# Create a text element and let the reader know the data is loading.
dataLoadState = st.text('Loading data...')
# Load 10,000 rows of data into the dataframe.
rawData = loadData("https://docs.google.com/spreadsheets/d/1Qq13N2dgpU8TWwLLJKsmauKQM1Damvykkn2nOnFQ56A/edit#gid=580980480")
# Notify the reader that the data was successfully loaded.
dataLoadState.text('Loading data...done!')
dayData = fillDays(rawData)

selection = alt.selection_multi(fields=['activity'])
# multi = alt.selection_multi()
c1 = alt.Chart(dayData).mark_bar().encode(
    x = alt.X('monthdate(start):O', axis=alt.Axis(title='Date')),
    y=alt.Y('Hour', axis=alt.Axis(title="Time"), scale=alt.Scale(domain=(2, 20), clamp=True)), 
    order=alt.Order('start'), 
    color=alt.condition(alt.datum.activity == 'N/A', alt.value('white'), alt.Color('activity', legend=None)),
    opacity=alt.condition(selection, alt.value(1), alt.value(.2)),
    tooltip=[
        'activity:N', 
        alt.Tooltip('Hour:Q', format='.2f', title='hours'), 
        alt.Tooltip('start:T', format='%-I:%M %p', title='started'),
        alt.Tooltip('end:T', format='%-I:%M %p', title='ended')]
).add_selection(
    selection
)

st.altair_chart(c1, use_container_width=True)


