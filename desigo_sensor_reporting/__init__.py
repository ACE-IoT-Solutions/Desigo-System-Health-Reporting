import json
from datetime import datetime
import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import plotly.graph_objects as go

from parsers import get_site_sample
from firestore import get_db, get_site_data

key_dict = json.loads(st.secrets["textkey"])
db = get_db(key_dict)

st.set_page_config(
    page_title="Desigo Site Reporting interface",
    page_icon=":bar_chart:",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    section = option_menu(
        "Main Menu",
        ["Site Report", "Upload Reports", "Failed Points", "Alarms", "Overrides"],
    )


if section == "Upload Reports":
    sensor_file = st.file_uploader("Upload sensor data", type=["xlsx"])
    if sensor_file:
        if "apogee" in sensor_file.name.lower():
            sensor_type = "apogee"
        elif "bacnet" in sensor_file.name.lower():
            sensor_type = "bacnet"
        else:
            st.selectbox("Select System Type", ["apogee", "bacnet"])
        if "failed" in sensor_file.name.lower():
            report_type = "failed"
        elif "operator" in sensor_file.name.lower():
            report_type = "operator"
        elif "alarm" in sensor_file.name.lower():
            report_type = "alarm"
        else:
            st.selectbox("Select Report Type", ["failed", "operator", "alarm"])
        sample_time = st.date_input("Sample Time", datetime.utcnow())
        sensor_data = pd.read_excel(sensor_file, header=2, skipfooter=2)
        sites = db.collection("sites").get()
        site_options = ["New Site"] + [site.to_dict()["name"] for site in sites]
        site_option_name = st.selectbox("Select Site", site_options)
        if site_option_name == "New Site":
            site_name_input = st.text_input("Site Name", value="New Site")
        if st.button("Import Data"):
            if site_option_name == "New Site" and site_option_name != site_name_input:
                site_ref = db.collection("sites").add({"name": site_name_input})
                site_name = site_name_input
            else:
                site_name = site_option_name
                site_ref = [
                    site for site in sites if site.to_dict()["name"] == site_name
                ][0].reference
            site_sample = get_site_sample(
                sensor_data, sensor_type, site_name, report_type, sample_time, site_ref
            )
            site_sample["site_ref"] = site_ref
            site_sample_ref = db.collection("site-samples").add(site_sample)
            sensor_file.close()
            st.subheader("Data Imported Successfully")


def get_vis_data_by_panel(df: pd.DataFrame) -> pd.DataFrame:
    panel_vis_data = pd.DataFrame(df["panel_counts"].values.tolist())
    panel_vis_data.index = df.index
    # panel_vis_data = pd.concat((df.index, panel_df), axis=1, join="inner")
    # panel_vis_data = panel_vis_data.set_index("timestamp").sort_index().groupby("timestamp").sum()
    panel_vis_data = panel_vis_data.sort_index().groupby("timestamp").sum()
    return panel_vis_data


def get_site_plot_df(site_samples: pd.DataFrame, column_renames: dict) -> pd.DataFrame:
    plot_df = site_samples[["total_count", "total_panels"]].groupby("timestamp").sum()
    plot_df.rename(columns=column_renames, inplace=True)
    return plot_df


def draw_panel_vis(panel_df: pd.DataFrame, subheader: str = None):
    fig = go.Figure()
    for panel in (col for col in panel_df.columns if col != "timestamp"):
        fig.add_trace(
            go.Scatter(
                x=panel_df.index, y=panel_df[panel], name=panel, line_shape="linear"
            )
        )
    header_text = subheader if subheader else "Panel Counts"
    if subheader is not False:
        st.subheader(header_text)
    st.plotly_chart(fig, use_container_width=True)


def draw_site_plot(df: pd.DataFrame):
    fig = go.Figure()
    for panel in (col for col in plot_df.columns if col != "timestamp"):
        fig.add_trace(
            go.Scatter(
                x=plot_df.index, y=plot_df[panel], name=panel, line_shape="linear"
            )
        )
    fig.update_layout(
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        }
    )
    st.subheader("Total Counts")
    st.plotly_chart(fig, use_container_width=True)


if section == "Site Report":
    site_name = st.selectbox(
        "Site Name",
        [record.to_dict()["name"] for record in db.collection("sites").get()],
    )
    site_sample_records = (
        db.collection("site-samples")
        .where("site_name", "==", site_name)
        .select(
            ("report_type", "panel_counts", "total_count", "timestamp", "total_panels")
        )
        .get()
    )
    if site_name and site_sample_records:
        site_samples = pd.DataFrame([x.to_dict() for x in site_sample_records])
        site_samples["timestamp"] = pd.to_datetime(site_samples["timestamp"])
        site_samples["month"] = site_samples["timestamp"].apply(
            lambda x: x.strftime("%Y-%m")
        )
        site_samples_pivot = (
            site_samples.groupby(["month", "report_type"])
            .last()
            .reset_index()
            .pivot(index="month", columns="report_type", values="total_count")
            .rename(
                columns={
                    "failed": "Total Failed",
                    "operator": "Total Operator",
                    "alarm": "Total Alarms",
                }
            )
        )
        st.dataframe(site_samples_pivot, use_container_width=True)
        failed_samples = site_samples_pivot[["Total Failed"]]
        alarm_samples = site_samples_pivot[["Total Alarms"]]
        operator_samples = site_samples_pivot[["Total Operator"]]
        # st.dataframe(pd.concat((failed_samples, operator_samples, alarm_samples), axis=1, ))
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=failed_samples.index,
                y=failed_samples["Total Failed"],
                name="Failed",
                line_shape="linear",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=operator_samples.index,
                y=operator_samples["Total Operator"],
                name="Operator",
                line_shape="linear",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=alarm_samples.index,
                y=alarm_samples["Total Alarms"],
                name="Alarm",
                line_shape="linear",
            )
        )
        st.plotly_chart(fig, use_container_width=True)

        def plot_metric(label, column):
            metric_this_month = int(column.iloc[-1])
            metric_last_month = int(column.iloc[-2])
            return st.metric(
                label=label,
                value=metric_this_month,
                delta=metric_this_month - metric_last_month,
                delta_color="inverse",
            )

        col1, col2, col3 = st.columns(3)
        if alarm_samples.shape[0] > 1:
            with col1:
                plot_metric("Alarms Month over Month", alarm_samples["Total Alarms"])
        if operator_samples.shape[0] > 1:
            with col2:
                plot_metric(
                    "Operator Month over Month", operator_samples["Total Operator"]
                )
        if failed_samples.shape[0] > 1:
            with col3:
                plot_metric("Failed Month over Month", failed_samples["Total Failed"])

if section == "Failed Points":
    site_name = st.selectbox(
        "Site Name",
        [record.to_dict()["name"] for record in db.collection("sites").get()],
    )
    if site_name:
        site_samples = get_site_data(db, site_name, "failed")
        if not site_samples.empty:
            st.dataframe(
                site_samples[["total_count", "total_panels", "sensor_type"]],
                use_container_width=True,
            )
            plot_df = get_site_plot_df(
                site_samples,
                {
                    "total_count": "Total Failed Points",
                    "total_panels": "Panels with Failed Points",
                },
            )
            st.dataframe(plot_df, use_container_width=True)
            draw_site_plot(plot_df)
            panel_df = get_vis_data_by_panel(site_samples)
            draw_panel_vis(panel_df)
        else:
            st.write("No failed points found for site")

if section == "Alarms":
    site_name = st.selectbox(
        "Site Name",
        [record.to_dict()["name"] for record in db.collection("sites").get()],
    )
    if site_name:
        site_samples = get_site_data(db, site_name, "alarm")
        if not site_samples.empty:
            st.dataframe(
                site_samples[["total_count", "total_panels", "sensor_type"]],
                use_container_width=True,
            )
            plot_df = get_site_plot_df(
                site_samples,
                {"total_count": "Total Alarms", "total_panels": "Panels with Alarms"},
            )
            st.dataframe(plot_df, use_container_width=True)
            draw_site_plot(plot_df)
            panel_df = get_vis_data_by_panel(site_samples)
            draw_panel_vis(panel_df)
        else:
            st.write("No alarm points found for site")

if section == "Overrides":
    site_name = st.selectbox(
        "Site Name",
        [record.to_dict()["name"] for record in db.collection("sites").get()],
    )
    if site_name:
        site_samples = get_site_data(db, site_name, "operator")
        if not site_samples.empty:
            st.dataframe(
                site_samples[["total_count", "total_panels", "sensor_type"]],
                use_container_width=True,
            )
            plot_df = get_site_plot_df(
                site_samples,
                {
                    "total_count": "Total Points in Operator",
                    "total_panels": "Panels with Operator Points",
                },
            )
            st.dataframe(plot_df, use_container_width=True)
            draw_site_plot(plot_df)
            panel_df = get_vis_data_by_panel(site_samples)
            draw_panel_vis(panel_df)
        else:
            st.write("No overrides points found for site")
