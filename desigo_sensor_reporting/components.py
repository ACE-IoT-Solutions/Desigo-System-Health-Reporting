import json
from datetime import datetime
import pytz

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from firestore import get_db, get_site_data
from streamlit_option_menu import option_menu

key_dict = json.loads(st.secrets["textkey"])
db = get_db(key_dict)


def get_vis_data_by_panel(df: pd.DataFrame) -> pd.DataFrame:
    panel_vis_data = pd.DataFrame(df["panel_counts"].values.tolist())
    panel_vis_data.index = df.index
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


def draw_site_plot(plot_df: pd.DataFrame):
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


def plot_site_overview(site_samples_pivot: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for report_type in ("Failed", "Operator", "Alarms"):
        fig.add_trace(
            go.Scatter(
                x=site_samples_pivot.index,
                y=site_samples_pivot[f"Total {report_type}"],
                name=report_type,
                line_shape="linear",
            )
        )
    return fig


def plot_metric(label, column):

    metric_this_month = int(column.iloc[-1])
    metric_last_month = int(column.iloc[-2])
    metric_avg = int(column.mean())
    metric_avg_last_month = int(column.iloc[:-2].mean())
    metric_avg_delta = int(column.diff().mean())
    st.metric(
        label=f"{label} Month over Month",
        value=metric_this_month,
        delta=metric_this_month - metric_last_month,
        delta_color="inverse",
    )
    st.metric(
        label=f"{label} Average",
        value=metric_avg,
        delta=metric_avg - metric_avg_last_month,
        delta_color="inverse",
    )
    st.metric(
        label=f"{label} Average Delta",
        value=metric_avg_delta,
        delta_color="inverse",
    )


def report_type_page(report_type, section_label):
    st.header(f"{section_label} Report")
    site_name = st.selectbox(
        "Site Name",
        [record.to_dict()["name"] for record in db.collection("sites").get()],
    )
    if site_name:
        site_samples = get_site_data(db, site_name)
        section_samples = site_samples[site_samples["report_type"] == report_type]
        if not section_samples.empty:
            st.dataframe(
                section_samples[["total_count", "total_panels", "sensor_type"]].rename(
                    columns={
                        "total_count": f"Total {section_label}",
                        "total_panels": f"Panels with {section_label}",
                        "sensor_type": "Sensor Type",
                    }
                ),
                use_container_width=True,
            )
            plot_df = get_site_plot_df(
                section_samples,
                {
                    "total_count": f"Total {section_label}",
                    "total_panels": f"Panels with {section_label}",
                },
            )
            draw_site_plot(plot_df)
            panel_df = get_vis_data_by_panel(section_samples)
            draw_site_plot(panel_df)
            selected_panel = st.selectbox("select a Panel", panel_df.columns)
            def create_point_df(df):
                new_dfs = []
                for row in df.to_dict(orient="records"):
                    for point in row["points"]:
                        new_row = row.copy()
                        del new_row["points"]
                        del new_row["panel_counts"]

                        new_row.update({f"point_{point_col}": str(point_val) for point_col, point_val in point.items()})
                        new_dfs.append(new_row)
                df = pd.DataFrame(new_dfs, columns=["sensor_type", "timestamp", "point_panel_name", "point_name", "point_value", "point_status"])
                # df["v"]
                return df
            if selected_panel:
                draw_site_plot(panel_df[[selected_panel]])
                selected_sample = st.selectbox("select a sample time", panel_df[selected_panel].index)
                if selected_sample:
                    point_data = create_point_df(section_samples)
                    st.dataframe(point_data[(point_data["point_panel_name"] == selected_panel) & (point_data["timestamp"] == selected_sample)])
 
                    # points = section_samples[section_samples["panel_name"] == selected_panel]["points"]
                    # st.dataframe(
                    #     points
                    # )
        else:
            st.write("No failed points found for site")
