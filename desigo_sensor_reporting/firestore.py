import json

import firebase_admin
import pandas as pd
import streamlit as st
from firebase_admin import credentials, firestore


def get_db(key_dict):
    cred = credentials.Certificate(key_dict)
    try:
        default_app = firebase_admin.get_app("DEFAULT")
    except ValueError:
        default_app = firebase_admin.initialize_app(cred, name="DEFAULT")
    db = firebase_admin.firestore.client(default_app)
    return db


def get_site_data(db, site_name: str, report_type: str = None, fields: tuple = None):
    if fields is None:
        fields = (
            "report_type",
            "panel_counts",
            "total_count",
            "timestamp",
            "total_panels",
            "sensor_type",
        )
    query = db.collection("site-samples").where(
        field_path="site_name", op_string="==", value=site_name
    )
    if report_type is not None:
        query = query.where(field_path="report_type", op_string="==", value=report_type)
    site_sample_records = query.select(fields).get()
    if site_sample_records:
        site_samples = pd.DataFrame([x.to_dict() for x in site_sample_records])
        site_samples = site_samples.drop_duplicates(
            subset=["timestamp", "report_type", "sensor_type"], keep="last"
        )
        site_samples["timestamp"] = pd.to_datetime(site_samples["timestamp"])
        site_samples.set_index("timestamp", inplace=True)
        site_samples.sort_index(inplace=True)
        return site_samples
    else:
        return pd.DataFrame()
