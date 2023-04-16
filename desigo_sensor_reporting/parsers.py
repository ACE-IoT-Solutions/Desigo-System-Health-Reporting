from typing import Union
from datetime import datetime
import pandas as pd

def index_or_none(self, x):
    try:
        return self.index(x)
    except ValueError:
        return None

def get_panel_name_from_point_name(point_name: str) -> str:
    token_list = point_name.split(".")
    if i := index_or_none(token_list, "Hardware"):
        if len(token_list[i:]) > 2:
            return token_list[i + 1]
        else:
            return token_list[-1]

    elif i := index_or_none(token_list, "OfflineTrends"):
        return token_list[i + 2]
    elif i := index_or_none(token_list, "FieldNetworks"):
        if len(token_list[i:]) > 3:
            return token_list[-3]
        elif len(token_list[i:]) > 2:
            return token_list[-2]
    elif i := index_or_none(token_list, "APOGEEZones"):
        return token_list[-1]
    elif i := index_or_none(token_list, "Servers"):
        return f"{token_list[-2]}-{token_list[-1]}"
    return "N/A Panel"

def get_system_type_from_file_name(file_name: str):
    name_lower = file_name.lower()
    if "apogee" in name_lower:
        return "apogee"
    elif "bacnet" in name_lower:
        return "bacnet"
    else:
        return None

def get_report_type_from_file_name(file_name: str):
    name_lower = file_name.lower()
    if "failed" in name_lower:
        return "failed"
    elif "operator" in name_lower:
        return "operator"
    elif "alarm" in name_lower:
        return "alarm"
    else:
        return None


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


def get_site_sample(
    df: pd.DataFrame,
    system_type: str,
    site_name: str,
    report_type: str,
    sample_time: datetime,
    site_ref,
) -> dict:
    site_sample = {
        "timestamp": sample_time.isoformat(),
        "sensor_type": system_type,
        "site_name": site_name,
        "report_type": report_type,
    }
    point_converter = create_point_decoder(
        system_type, site_name, sample_time.isoformat()
    )
    if system_type == "apogee":
        for point in df.to_dict(orient="records"):
            site_sample["panel_counts"] = site_sample.get("panel_counts", {}) | {
                point["Panel Name"]: site_sample.get("panel_counts", {}).get(
                    point["Panel Name"], 0
                )
                + 1
            }
            site_sample["total_count"] = site_sample.get("total_count", 0) + 1
            site_sample["points"] = site_sample.get("points", []) + [
                point_converter(point)
            ]

    elif system_type == "bacnet":
        for point in df.to_dict(orient="records"):
            panel_name = get_panel_name_from_point_name(point["Object Designation"])
            site_sample["panel_counts"] = site_sample.get("panel_counts", {}) | {
                panel_name: site_sample.get("panel_counts", {}).get(panel_name, 0) + 1
            }
            site_sample["total_count"] = site_sample.get("total_count", 0) + 1
            site_sample["points"] = site_sample.get("points", []) + [
                point_converter(point)
            ]
    site_sample["total_panels"] = len(site_sample.get("panel_counts", ()))

    return site_sample