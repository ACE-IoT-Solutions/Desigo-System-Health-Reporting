from datetime import datetime
import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import altair as alt
import plotly.figure_factory as ff
import plotly.graph_objects as go
import json
key_dict = json.loads(st.secrets["textkey"])
cred = credentials.Certificate(key_dict)
try:
    default_app = firebase_admin.get_app("DEFAULT")
except ValueError:
    default_app = firebase_admin.initialize_app(cred, name="DEFAULT")
db = firebase_admin.firestore.client(default_app)

def index_or_none(self, x):
    try:
        return self.index(x)
    except ValueError:
        return None

def get_panel_name_from_point_name(point_name: str) -> str:
    token_list = point_name.split(".")
    if i := index_or_none(token_list, "Hardware"):
        if len(token_list[i:]) > 2:
            return token_list[i+1]
        else:
            return token_list[-1]

    elif i:=index_or_none(token_list, "OfflineTrends"):
        return token_list[i+2]
    elif i:= index_or_none(token_list, "FieldNetworks"):
        if len(token_list[i:]) > 3:
            return token_list[-3]
        elif len(token_list[i:]) > 2:
            return token_list[-2]
    elif i:= index_or_none(token_list, "APOGEEZones"):
        return token_list[-1]
    elif i:= index_or_none(token_list, "Servers"):
        return f"{token_list[-2]}-{token_list[-1]}"
    return "N/A Panel"

def create_point_decoder(system_type: str, site: str, timestamp: str):
    def create_point_sample(row):
        if system_type == "apogee":
            return {
                "name": row["Point System Name"],
                "panel_name": row["Panel Name"],
                "description": row["Description"],
                "system_type": system_type,
                "units": row["Engineering Units"],
                "command_priority": row["Command Priority"],
                "current_value": row["Value/State"],
                "status": row["Status"],
                "site": site,
                "timestamp": timestamp,
            }
        elif system_type == "bacnet":
            panel_name = get_panel_name_from_point_name(row["Object Designation"])

            return {
                "name": row["Object Designation"],
                "panel_name": panel_name,
                "description": row["Object Description"],
                "system_type": system_type,
                "units": row.get("[Units]", row.get("Units")),
                "command_priority": row.get("[Current_Priority]"),
                "current_value": row.get("Main Value", row.get("State")),
                "alarm_category": row.get("Category", ""),
                "object_type": row.get("Type", row.get("Discipline")),
                "status": row.get("[Status_Flags]", ""),
                "site": site,
                "timestamp": timestamp,
                "creation_time": row.get("Creation Date Time", ""),
            }
    return create_point_sample

def get_site_sample(df: pd.DataFrame, system_type: str, site_name: str, report_type: str, sample_time: datetime, site_ref) -> dict:
    site_sample = {
        "timestamp": sample_time.isoformat(),
        "sensor_type": system_type,
        "site_name": site_name,
        "report_type": report_type, 
    }
    point_converter = create_point_decoder(system_type, site_name, sample_time.isoformat())
    if system_type == "apogee":
        for point in sensor_data.to_dict(orient="records"):
            site_sample["panel_counts"] = site_sample.get("panel_counts", {}) | {point["Panel Name"]: site_sample.get("panel_counts", {}).get(point["Panel Name"], 0) + 1}
            site_sample["total_count"] = site_sample.get("total_count", 0) + 1
            site_sample["points"] = site_sample.get("points", []) + [point_converter(point)]

    elif system_type == "bacnet":
        for point in sensor_data.to_dict(orient="records"):
            panel_name = get_panel_name_from_point_name(point["Object Designation"])
            site_sample["panel_counts"] = site_sample.get("panel_counts", {}) | {panel_name: site_sample.get("panel_counts", {}).get(panel_name, 0) + 1}
            site_sample["total_count"] = site_sample.get("total_count", 0) + 1
            site_sample["points"] = site_sample.get("points", []) + [point_converter(point)]
    site_sample["total_panels"] = len(site_sample["panel_counts"])

    return site_sample
                


with st.sidebar:
    section = option_menu("Main Menu", ["Site Report", "Upload Reports", "Failed Points", "Alarms", "Overrides"],)


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
                site_ref = [site for site in sites if site.to_dict()["name"] == site_name][0].reference
            site_sample = get_site_sample(sensor_data, sensor_type, site_name, report_type, sample_time, site_ref)
            site_sample["site_ref"] = site_ref
            site_sample_ref = db.collection("site-samples").add(site_sample)
            # sensor_data.apply(lambda x: db.collection('point-status').add(create_point_decoder(sensor_type, site_name, sample_time.isoformat(), site_ref, site_sample_ref)(x)), axis=1)

def get_site_data(site_name: str, report_type:str):
    site_sample_records = db.collection("site-samples").where("site_name", "==", site_name).where("report_type", "==", report_type).select(('report_type', 'panel_counts', 'total_count', 'timestamp', 'total_panels', 'sensor_type')).get()
    site_samples = pd.DataFrame([x.to_dict() for x in site_sample_records])
    site_samples = site_samples.drop_duplicates(subset=["timestamp", "report_type", "sensor_type"], keep="last")
    site_samples["timestamp"] = pd.to_datetime(site_samples["timestamp"])
    site_samples.set_index("timestamp", inplace=True)
    site_samples.sort_index(inplace=True)
    return site_samples

def get_vis_data_by_panel(df: pd.DataFrame) -> pd.DataFrame:
    panel_vis_data = pd.DataFrame(df["panel_counts"].values.tolist())
    panel_vis_data.index = df.index
    # panel_vis_data = pd.concat((df.index, panel_df), axis=1, join="inner")
    # panel_vis_data = panel_vis_data.set_index("timestamp").sort_index().groupby("timestamp").sum()
    panel_vis_data = panel_vis_data.sort_index().groupby("timestamp").sum()
    return panel_vis_data

def get_site_plot_df(site_samples: pd.DataFrame, column_renames: dict) -> pd.DataFrame:
    plot_df = site_samples[['total_count', 'total_panels']].groupby("timestamp").sum()
    plot_df.rename(columns=column_renames, inplace=True)
    return plot_df


def draw_panel_vis(panel_df: pd.DataFrame, subheader: str=None):
    fig = go.Figure()
    for panel in (col for col in panel_df.columns if col != "timestamp"):
        fig.add_trace(go.Scatter(x=panel_df.index, y=panel_df[panel], name=panel, line_shape='linear'))
    header_text = subheader if subheader else "Panel Counts"
    if subheader is not False:
        st.subheader(header_text)
    st.plotly_chart(fig, use_container_width=True)

def draw_site_plot(df: pd.DataFrame):
    fig = go.Figure()
    for panel in (col for col in plot_df.columns if col != "timestamp"):
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[panel], name=panel, line_shape='linear'))
    fig.update_layout(legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1})
    st.subheader("Total Counts")
    st.plotly_chart(fig, use_container_width=True)

if section == "Site Report":
    site_name = st.selectbox("Site Name", [record.to_dict()['name'] for record in db.collection("sites").get()])
    site_sample_records = db.collection("site-samples").where("site_name", "==", site_name).select(('report_type', 'panel_counts', 'total_count', 'timestamp', 'total_panels')).get()
    if site_name and site_sample_records:
        site_samples = pd.DataFrame([x.to_dict() for x in site_sample_records])
        failed_samples = site_samples[site_samples["report_type"] == "failed"][["timestamp", "total_count"]].set_index("timestamp").groupby("timestamp").sum()
        operator_samples = site_samples[site_samples["report_type"] == "operator"][["timestamp", "total_count"]].set_index("timestamp").groupby("timestamp").sum()
        alarm_samples = site_samples[site_samples["report_type"] == "alarm"][["timestamp", "total_count"]].set_index("timestamp").groupby("timestamp").sum()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=failed_samples.index, y=failed_samples["total_count"], name="Failed", line_shape='linear'))
        fig.add_trace(go.Scatter(x=operator_samples.index, y=operator_samples["total_count"], name="Operator", line_shape='linear'))
        fig.add_trace(go.Scatter(x=alarm_samples.index, y=alarm_samples["total_count"], name="Alarm", line_shape='linear'))
        st.dataframe(site_samples[['timestamp', 'total_count', 'total_panels', 'report_type']], use_container_width=True)
        panel_failed_data = get_vis_data_by_panel(site_samples[site_samples["report_type"] == "failed"].set_index("timestamp"))
        panel_operator_data = get_vis_data_by_panel(site_samples[site_samples["report_type"] == "operator"].set_index("timestamp"))
        panel_alarm_data = get_vis_data_by_panel(site_samples[site_samples["report_type"] == "alarm"].set_index("timestamp"))
        st.plotly_chart(fig, use_container_width=True)
        if not panel_failed_data.empty:
            st.subheader("Failed Points")
            st.dataframe(panel_failed_data)
            draw_panel_vis(panel_failed_data, "Failed Points per Panel")
        if not panel_operator_data.empty:
            st.subheader("Operator Points")
            st.dataframe(panel_operator_data)
            draw_panel_vis(panel_operator_data, "Operator Points per Panel")
        if not panel_alarm_data.empty:
            st.subheader("Alarms")
            st.dataframe(panel_alarm_data)
            draw_panel_vis(panel_alarm_data, "Alarms per Panel")
        fig = go.Figure()

if section == "Failed Points":
    site_name = st.selectbox("Site Name", [record.to_dict()['name'] for record in db.collection("sites").get()])
    if site_name:
        site_samples = get_site_data(site_name, "failed")
        st.dataframe(site_samples[['total_count', 'total_panels', 'sensor_type']], use_container_width=True)
        plot_df = get_site_plot_df(site_samples, {"total_count": "Total Failed Points", "total_panels": "Panels with Failed Points"})
        st.dataframe(plot_df, use_container_width=True)
        draw_site_plot(plot_df)
        panel_df = get_vis_data_by_panel(site_samples)
        draw_panel_vis(panel_df)

if section == "Alarms":
    site_name = st.selectbox("Site Name", [record.to_dict()['name'] for record in db.collection("sites").get()])
    if site_name:
        site_samples = get_site_data(site_name, "alarm")
        st.dataframe(site_samples[['total_count', 'total_panels', 'sensor_type']], use_container_width=True)
        plot_df = get_site_plot_df(site_samples, {"total_count": "Total Alarms", "total_panels": "Panels with Alarms"})
        st.dataframe(plot_df, use_container_width=True)
        draw_site_plot(plot_df)
        panel_df = get_vis_data_by_panel(site_samples)
        draw_panel_vis(panel_df)

if section == "Overrides":
    site_name = st.selectbox("Site Name", [record.to_dict()['name'] for record in db.collection("sites").get()])
    if site_name:
        site_samples = get_site_data(site_name, "operator")
        st.dataframe(site_samples[['total_count', 'total_panels', 'sensor_type']], use_container_width=True)
        plot_df = get_site_plot_df(site_samples, {"total_count": "Total Points in Operator", "total_panels": "Panels with Operator Points"})
        st.dataframe(plot_df, use_container_width=True)
        draw_site_plot(plot_df)
        panel_df = get_vis_data_by_panel(site_samples)
        draw_panel_vis(panel_df)
        


