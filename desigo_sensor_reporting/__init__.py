import json
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components import option_menu, plot_metric, plot_site_overview, report_type_page, draw_panel_vis, draw_site_plot, get_site_plot_df, get_vis_data_by_panel
from firestore import get_db, get_site_data
from parsers import (
    get_report_type_from_file_name,
    get_site_sample,
    get_system_type_from_file_name,
)

key_dict = json.loads(st.secrets["textkey"])
db = get_db(key_dict)


st.set_page_config(
    page_title="Desigo Site Reporting interface",
    page_icon=":bar_chart:",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.title("Desigo Site Reporting interface")
    section = option_menu(
        "Main Menu",
        ["Site Report", "Upload Reports", "Failed Points", "Alarms", "Overrides"],
    )


if section == "Upload Reports":
    sensor_file = st.file_uploader("Upload sensor data", type=["xlsx"])
    if sensor_file:
        if sensor_type := get_system_type_from_file_name(sensor_file.name) is None:
            sensor_type = st.selectbox("Select System Type", ["apogee", "bacnet"])
        if report_type := get_report_type_from_file_name(sensor_file.name) is None:
            report_type = st.selectbox(
                "Select Report Type", ["failed", "operator", "alarm"]
            )
        sample_time = st.date_input("Sample Time", datetime.utcnow())
        sensor_data = pd.read_excel(sensor_file, header=2, skipfooter=2)
        sites = db.collection("sites").get()
        site_options = ["New Site"] + [site.to_dict()["name"] for site in sites]
        site_option_name = st.selectbox("Select Site", site_options)
        if site_option_name == "New Site":
            site_name_input = st.text_input("Site Name", value="New Site")
        if st.button(
            "Import Data",
        ):
            with st.spinner("Importing Data..."):
                if (
                    site_option_name == "New Site"
                    and site_option_name != site_name_input
                ):
                    site_ref = db.collection("sites").add({"name": site_name_input})
                    site_name = site_name_input
                else:
                    site_name = site_option_name
                    site_ref = [
                        site for site in sites if site.to_dict()["name"] == site_name
                    ][0].reference
                site_sample = get_site_sample(
                    sensor_data,
                    sensor_type,
                    site_name,
                    report_type,
                    sample_time,
                    site_ref,
                )
                site_sample["site_ref"] = site_ref
                site_sample_ref = db.collection("site-samples").add(site_sample)
                sensor_file.close()
                st.subheader("Data Imported Successfully")
                st.balloons()


if section == "Site Report":
    with st.spinner("Loading Site Data..."):
        site_name = st.selectbox(
            "Site Name",
            [record.to_dict()["name"] for record in db.collection("sites").get()],
        )
        site_samples = get_site_data(
            db,
            site_name,
        )
        if site_name and not site_samples.empty:
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
            fig = plot_site_overview(site_samples_pivot)
            st.plotly_chart(fig, use_container_width=True)

            col1, col2, col3 = st.columns(3)
            failed_samples = site_samples_pivot[["Total Failed"]]
            alarm_samples = site_samples_pivot[["Total Alarms"]]
            operator_samples = site_samples_pivot[["Total Operator"]]
            if alarm_samples.shape[0] > 1:
                with col1:
                    plot_metric(
                        "Alarms", alarm_samples["Total Alarms"]
                    )
            if operator_samples.shape[0] > 1:
                with col2:
                    plot_metric(
                        "Operator", operator_samples["Total Operator"]
                    )
            if failed_samples.shape[0] > 1:
                with col3:
                    plot_metric(
                        "Failed", failed_samples["Total Failed"]
                    )

if section == "Failed Points":
    report_type_page("failed", "Failed Points")

if section == "Alarms":
    report_type_page("alarm", "Alarms")

if section == "Overrides":
    report_type_page("operator", "Overrides")
