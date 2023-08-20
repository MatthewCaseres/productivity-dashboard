import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import datetime


@st.cache_data(ttl=3600)
def loadData(DATA_URL):
    csvFromSheet = "/".join(DATA_URL.split("/")[:-1] + ["export?format=csv"])
    df = pd.read_csv(csvFromSheet, parse_dates=["start", "end"])
    rawData = df[df["start"] != df["end"]].sort_values("start")
    return rawData


def fillDays(rawData):
    fillAfter = rawData.loc[rawData["start"].shift(-1) != rawData["end"], "end"]
    NAsDict = {
        "category": ["N/A"] * len(fillAfter),
        "activity": ["N/A"] * len(fillAfter),
        "start": fillAfter,
        "end": [None] * len(fillAfter),
    }
    NAs = pd.DataFrame(NAsDict)[:-1]

    # These are for the beginning and end
    beginningEndDict = {
        "category": ["N/A"] * 2,
        "activity": ["N/A"] * 2,
        "start": [min(rawData["start"]).floor("D"), max(rawData["end"])],
        "end": [min(rawData["start"]), max(rawData["end"]).ceil("D")],
    }
    beginningEnd = pd.DataFrame(beginningEndDict)

    # This should come after everything is partitioned
    midnightSeries = pd.date_range(
        min(rawData["start"]).ceil("D"), max(rawData["end"]).floor("D")
    )
    midnightsDict = {
        "activity": [None] * len(midnightSeries),
        "start": midnightSeries,
        "end": [None] * len(midnightSeries),
    }
    midnights = pd.DataFrame(midnightsDict)

    # combine the NA with the non-NA
    all = pd.concat([rawData, NAs, beginningEnd, midnights], ignore_index=True)
    all = all.sort_values("start")
    # Fill NA for added rows with correct values
    all["end"] = all["end"].fillna(all["start"].shift(-1))
    all["activity"] = all["activity"].fillna(method="ffill")
    all["category"] = all["category"].fillna(method="ffill")
    # For days crossing over, truncate at midnight
    all.loc[all["start"].dt.day != all["end"].dt.day, "end"] = all["start"].dt.ceil("D")
    all.loc[all["start"] == all["end"], "end"] = all["start"].shift(-1)
    all["Hour"] = (all["end"] - all["start"]).dt.total_seconds() / 3600
    all["day"] = all["start"].dt.floor("D")
    # There are strange issues, let's sidestep them https://github.com/streamlit/streamlit/issues/4342
    all["startclock"] = all["start"].dt.strftime("%I:%M %p")
    all["endclock"] = all["end"].dt.strftime("%I:%M %p")
    all["date"] = all["start"].dt.strftime("%b %d")
    return all


def getRollingAvgs(ACTIVITY_OR_CATEGORY, allData, low, high, WINDOW_SIZE):
    # allData = allData.iloc[:, 1:4]
    allData = allData.loc[:, [ACTIVITY_OR_CATEGORY, "start", "end"]]
    allData["s_trunc"] = allData["start"].dt.floor("D") + datetime.timedelta(hours=low)
    allData["e_trunc"] = allData["start"].dt.floor("D") + datetime.timedelta(hours=high)
    allData["log"] = (
        allData[["end", "e_trunc"]].min(axis=1)
        - allData[["start", "s_trunc"]].max(axis=1)
    ).dt.total_seconds()
    allData["log"] = np.where(allData["log"] < 0, 0, allData["log"]) / 3600
    allData["day"] = allData["start"].dt.floor("D")
    all_pivot = pd.pivot_table(
        allData,
        values="log",
        index="day",
        columns=[ACTIVITY_OR_CATEGORY],
        aggfunc=np.sum,
        fill_value=0,
    )
    rolling_avgs = all_pivot.rolling(WINDOW_SIZE, min_periods=1).mean()
    rolling_sums = all_pivot.rolling(WINDOW_SIZE).sum()
    tidy_rolling_avgs = rolling_avgs.reset_index().melt(
        id_vars=["day"], value_name="mean"
    )
    tidy_rolling_sums = rolling_sums.reset_index().melt(
        id_vars=["day"], value_name="total"
    )
    tidy_rolling_avgs["total"] = tidy_rolling_sums["total"]
    tidy_rolling_avgs["lookback"] = tidy_rolling_sums["day"] + pd.DateOffset(
        days=-WINDOW_SIZE + 1
    )
    return tidy_rolling_avgs


# Create a text element and let the reader know the data is loading.
dataLoadState = st.text("Loading data...")

user_input = st.text_input(
    'input the URL of a PUBLIC "better tracker" sheet',
    "https://docs.google.com/spreadsheets/d/1Qq13N2dgpU8TWwLLJKsmauKQM1Damvykkn2nOnFQ56A/edit#gid=580980480",
)
rawData = loadData(user_input)
# Notify the reader that the data was successfully loaded.
# dataLoadState.markdown('<h1 style="margin-bottom: 40px">Better Tracker</h1>', unsafe_allow_html=True)

dataLoadState.markdown("# Better Tracker ⏱️", unsafe_allow_html=True)
st.markdown("<hr />", unsafe_allow_html=True)


dayData = fillDays(rawData)


ACTIVITY_OR_CATEGORY = st.sidebar.radio(
    "Analyze by category or activity", ["category", "activity"]
)
st.sidebar.markdown("<hr />", unsafe_allow_html=True)
st.sidebar.text(
    f"Your data contains datetimes between: \n{min(rawData['start'])} \n{max(rawData['end'])}"
)
START_END_DATE = st.sidebar.date_input(
    "Filter by date range",
    [min(rawData["start"]).floor("D"), max(rawData["end"]).floor("D")],
)

START_TIME, END_TIME = st.sidebar.slider("Filter by hour", 0.0, 24.0, (0.0, 24.0), 0.5)

# ALL_ACTIVITIES = st.sidebar.multiselect('Which activities?', dayData.activity.unique(
# ).tolist(), dayData.activity.unique().tolist())

container = st.sidebar.container()
isAllActivities = st.sidebar.checkbox("Select all", True)

if isAllActivities:
    SELECTED_ACTIVITIES = container.multiselect(
        "Select one or more options:",
        dayData[ACTIVITY_OR_CATEGORY].unique().tolist(),
        list(
            filter(
                lambda activity: activity != "N/A",
                dayData[ACTIVITY_OR_CATEGORY].unique().tolist(),
            )
        ),
    )
else:
    SELECTED_ACTIVITIES = container.multiselect(
        "Select one or more options:", dayData[ACTIVITY_OR_CATEGORY].unique().tolist()
    )

HIDDEN = list(set(dayData[ACTIVITY_OR_CATEGORY].unique()) - set(SELECTED_ACTIVITIES))

if len(START_END_DATE) < 2:
    START_END_DATE = (*START_END_DATE, max(rawData["end"]).floor("D"))

START_DATE = START_END_DATE[0]
END_DATE = START_END_DATE[1]
filteredData = dayData[
    (dayData["start"].dt.date >= START_DATE) & (dayData["start"].dt.date <= END_DATE)
]
selection = alt.selection_multi(fields=[ACTIVITY_OR_CATEGORY])

c1 = (
    alt.Chart(filteredData)
    .mark_bar()
    .encode(
        x=alt.X("utcmonthdate(start):O", axis=alt.Axis(title="Date")),
        y=alt.Y(
            "Hour",
            axis=alt.Axis(title="Time"),
            scale=alt.Scale(domain=(START_TIME, END_TIME), clamp=True),
        ),
        order=alt.Order("start"),
        color=alt.condition(
            alt.FieldOneOfPredicate(field=ACTIVITY_OR_CATEGORY, oneOf=["N/A"] + HIDDEN),
            alt.value("white"),
            alt.Color(ACTIVITY_OR_CATEGORY, legend=None),
        ),
        opacity=alt.condition(selection, alt.value(1), alt.value(0.2)),
        tooltip=[
            f"{ACTIVITY_OR_CATEGORY}:N",
            alt.Tooltip("Hour:Q", format=".2f", title="hours"),
            alt.Tooltip("startclock", title="started"),
            alt.Tooltip("endclock", title="ended"),
            alt.Tooltip("end:T", format="%-I:%M %p", title="ended"),
            alt.Tooltip("date", title="date"),
        ],
    )
    .add_selection(selection)
)
st.markdown("See the sidebar to change the scale of the graph.")
st.altair_chart(c1, use_container_width=True)
st.markdown(
    "This website is best viewed on a computer so you can hover over data elements. Click on a time block to highlight all instances of that activity. You can use multiple selections with shift+click."
)

st.markdown("<hr />", unsafe_allow_html=True)

LOOKBACK = st.number_input(
    label="Rolling Average Lookback",
    min_value=1,
    value=1,
    step=1,
    help="This is used to calculate rolling averages and cumulative totals above.",
)

tidy_rolling_avgs = getRollingAvgs(
    ACTIVITY_OR_CATEGORY, dayData, START_TIME, END_TIME, LOOKBACK
)
filtered_rolling_avgs = tidy_rolling_avgs[
    (tidy_rolling_avgs["day"].dt.date >= START_DATE)
    & (tidy_rolling_avgs["day"].dt.date <= END_DATE)
]
selection2 = alt.selection_multi(fields=[ACTIVITY_OR_CATEGORY])

c2 = (
    alt.Chart(filtered_rolling_avgs)
    .mark_bar()
    .encode(
        x=alt.X("monthdate(day):O", axis=alt.Axis(title="Date")),
        y=alt.Y("mean", axis=alt.Axis(title=f"{LOOKBACK}-Day Rolling Average")),
        order=alt.Order("mean", sort="descending"),
        color=alt.Color(ACTIVITY_OR_CATEGORY, legend=None),
        opacity=alt.condition(selection2, alt.value(1), alt.value(0.2)),
        tooltip=[
            f"{ACTIVITY_OR_CATEGORY}:N",
            alt.Tooltip("mean:Q", format=".2f", title="mean"),
            alt.Tooltip("total:Q", format=".2f", title="total"),
            alt.Tooltip("monthdate(lookback):O", title="lookback"),
            alt.Tooltip("monthdate(day):O", title="day"),
        ],
    )
    .transform_filter(
        alt.FieldOneOfPredicate(field=ACTIVITY_OR_CATEGORY, oneOf=SELECTED_ACTIVITIES)
    )
    .add_selection(selection2)
)

st.altair_chart(c2, use_container_width=True)
