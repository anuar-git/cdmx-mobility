import csv

GBFS_REQUIRED = frozenset({"last_updated", "ttl", "data"})

# GTFS column names are lowercase by spec.
GTFS_STATIC_REQUIRED: dict[str, frozenset[str]] = {
    "stops": frozenset({"stop_id", "stop_name", "stop_lat", "stop_lon"}),
    "routes": frozenset({"route_id", "route_short_name", "route_type"}),
    "trips": frozenset({"route_id", "service_id", "trip_id"}),
    "stop_times": frozenset({"trip_id", "stop_id", "stop_sequence"}),
    "calendar": frozenset({"service_id", "monday", "start_date", "end_date"}),
    "shapes": frozenset({"shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"}),
}

# Confirmed from afluenciastc_simple_03_2026.csv: fecha,anio,mes,linea,estacion,afluencia
METRO_AFFLUENCE_REQUIRED: frozenset[str] = frozenset(
    {"fecha", "anio", "mes", "linea", "estacion", "afluencia"}
)


def validate_gbfs_envelope(payload: dict, feed_name: str) -> None:
    """Raise ValueError if the GBFS top-level envelope is missing required keys."""
    missing = GBFS_REQUIRED - payload.keys()
    if missing:
        raise ValueError(f"GBFS {feed_name}: missing keys {sorted(missing)}")


def validate_csv_header(data: bytes, required_cols: frozenset[str], source: str) -> None:
    """Raise ValueError if a CSV's header row is missing required column names.

    Comparison is case-insensitive so LINEA and linea are both accepted.
    Only the first line is decoded — safe for large GTFS files.
    """
    header_line = data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    actual_cols = {col.strip().lower() for col in next(csv.reader([header_line]))}
    missing = {col.lower() for col in required_cols} - actual_cols
    if missing:
        raise ValueError(f"{source}: CSV missing columns {sorted(missing)}")
