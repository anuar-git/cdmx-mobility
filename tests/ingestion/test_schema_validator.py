import pytest

from ingestion.schema_validator import (
    GTFS_STATIC_REQUIRED,
    METRO_AFFLUENCE_REQUIRED,
    validate_csv_header,
    validate_gbfs_envelope,
)

# --- validate_gbfs_envelope ---


def test_validate_gbfs_envelope_passes_with_all_keys():
    validate_gbfs_envelope({"last_updated": 1700000000, "ttl": 120, "data": {}}, "station_status")


def test_validate_gbfs_envelope_raises_on_missing_ttl():
    with pytest.raises(ValueError, match="ttl"):
        validate_gbfs_envelope({"last_updated": 1, "data": {}}, "station_status")


def test_validate_gbfs_envelope_raises_on_missing_data():
    with pytest.raises(ValueError, match="data"):
        validate_gbfs_envelope({"last_updated": 1, "ttl": 60}, "station_status")


def test_validate_gbfs_envelope_error_names_feed():
    with pytest.raises(ValueError, match="station_information"):
        validate_gbfs_envelope({}, "station_information")


# --- validate_csv_header ---


def _csv(header: str, row: str = "v1,v2") -> bytes:
    return f"{header}\n{row}\n".encode()


def test_validate_csv_header_passes_for_stops():
    data = _csv("stop_id,stop_code,stop_name,stop_lat,stop_lon,zone_id")
    validate_csv_header(data, GTFS_STATIC_REQUIRED["stops"], source="gtfs_static/stops")


def test_validate_csv_header_passes_for_routes():
    data = _csv("route_id,agency_id,route_short_name,route_long_name,route_type")
    validate_csv_header(data, GTFS_STATIC_REQUIRED["routes"], source="gtfs_static/routes")


def test_validate_csv_header_raises_on_missing_stop_lat():
    data = _csv("stop_id,stop_name,stop_lon")
    with pytest.raises(ValueError, match="stop_lat"):
        validate_csv_header(data, GTFS_STATIC_REQUIRED["stops"], source="gtfs_static/stops")


def test_validate_csv_header_raises_on_missing_route_type():
    data = _csv("route_id,route_short_name")
    with pytest.raises(ValueError, match="route_type"):
        validate_csv_header(data, GTFS_STATIC_REQUIRED["routes"], source="gtfs_static/routes")


def test_validate_csv_header_is_case_insensitive():
    # GTFS spec mandates lowercase, but real-world files sometimes use uppercase
    data = _csv("STOP_ID,STOP_NAME,STOP_LAT,STOP_LON")
    validate_csv_header(data, GTFS_STATIC_REQUIRED["stops"], source="gtfs_static/stops")


def test_validate_csv_header_metro_affluence_passes():
    data = _csv("LINEA,ESTACION,AFLUENCIA,FECHA")
    validate_csv_header(data, METRO_AFFLUENCE_REQUIRED, source="metro_affluence/test.csv")


def test_validate_csv_header_metro_affluence_raises_on_missing():
    data = _csv("LINEA,FECHA")
    with pytest.raises(ValueError, match="estacion"):
        validate_csv_header(data, METRO_AFFLUENCE_REQUIRED, source="metro_affluence/test.csv")


def test_validate_csv_header_error_names_source():
    data = _csv("col1,col2")
    with pytest.raises(ValueError, match="gtfs_static/trips"):
        validate_csv_header(data, GTFS_STATIC_REQUIRED["trips"], source="gtfs_static/trips")


def test_validate_csv_header_all_gtfs_feeds_have_required_keys():
    # sanity-check that every feed in GTFS_STATIC_REQUIRED is non-empty
    for feed_name, cols in GTFS_STATIC_REQUIRED.items():
        assert len(cols) > 0, f"{feed_name} has no required columns"
