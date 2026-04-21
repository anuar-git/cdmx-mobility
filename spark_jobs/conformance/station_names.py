"""Metro station name canonicalization.

CDMX publishes Metro affluence CSVs with inconsistent station names across
publication months. Two root causes:

1. Renaming with slash notation: SEMOVI has appended secondary names to several
   stations over the years (e.g. Garibaldi → Garibaldi/Lagunilla in 2015). CSVs
   from before the rename use the old short form; CSVs from after use the new form.
   Both appear in the same multi-year dataset.

2. Missing or incorrect accents: Earlier vintages (pre-2018) inconsistently omit
   accent marks (e.g. "Gomez Farias" vs "Gómez Farías"). Confirmed from the live
   afluenciastc_simple_03_2026.csv where both spellings appear in the same file.

The UDF normalises input to .strip().upper() before lookup so the dict keys only
need to cover accent/case variants, not every combination of both.

Add new entries here as they are discovered during the Metro affluence Silver job
rather than in individual SQL models or job files.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

# Silver output path for the EcoBici station-information master table.
# Written once daily by bronze_to_silver_ecobici.py; joined by downstream jobs
# that need station metadata (name, lat/lon, capacity).
ECOBICI_STATION_MASTER_PATH = "gs://cdmx-mobility-data/silver/ecobici/station_master/"

# Keys are .strip().upper() of the observed variant spelling.
# Values are the current official canonical name (properly accented, as published
# by SEMOVI in the most recent dataset vintage).
METRO_STATION_CANONICAL: dict[str, str] = {
    # --- Stations renamed with slash notation ---
    # Garibaldi became Garibaldi/Lagunilla in 2015 (Line B).
    "GARIBALDI": "Garibaldi/Lagunilla",
    # Etiopía renamed in 2020 (Line 8).
    "ETIOPÍA": "Etiopía/Plaza de la Transparencia",
    "ETIOPIA": "Etiopía/Plaza de la Transparencia",
    # Ferrería renamed in 2021 (Line 6).
    "FERRERÍA": "Ferrería/Arena Ciudad de México",
    "FERRERIA": "Ferrería/Arena Ciudad de México",
    # La Villa/Basílica: historical CSVs use either half of the slash name.
    "LA VILLA": "La Villa/Basílica",
    "BASÍLICA": "La Villa/Basílica",
    "BASILICA": "La Villa/Basílica",
    # Viveros renamed (Line 3).
    "VIVEROS": "Viveros/Derechos Humanos",
    # Zócalo: pre-2000 CSVs use the short form.
    "ZOCALO": "Zócalo/Tenochtitlan",
    "ZÓCALO": "Zócalo/Tenochtitlan",
    # Aeropuerto was the historical name before the terminal was renamed.
    "AEROPUERTO": "Terminal Aérea",
    "TERMINAL AEREA": "Terminal Aérea",
    "TERMINAL AÉREA": "Terminal Aérea",
    # --- Missing or incorrect accents (confirmed in live data) ---
    # Both "Gómez Farias" (missing accent on Farías) and "Gomez Farias" (both missing)
    # appear in afluenciastc_simple_03_2026.csv alongside the correct form.
    "GÓMEZ FARIAS": "Gómez Farías",
    "GOMEZ FARIAS": "Gómez Farías",
    "GOMEZ FARÍAS": "Gómez Farías",
    # "Olímpica" appears in two differently-encoded byte sequences in the same CSV.
    "OLIMPICA": "Olímpica",
    # Peñón Viejo: lowercase "viejo" variant seen in pre-2015 vintages.
    # The .upper() normalisation collapses this, so no explicit entry needed —
    # both "Peñón Viejo" and "Peñón viejo" become "PEÑÓN VIEJO" after .upper().
    # Listed here as documentation of the observed variant.
    # "PEÑÓN VIEJO": "Peñón Viejo",  # handled by .upper() normalisation
    "PEÑON VIEJO": "Peñón Viejo",  # missing tilde on Peñón
    "PINO SUAREZ": "Pino Suárez",
    "NIÑOS HEROES": "Niños Héroes",
    "CONSTITUCION DE 1917": "Constitución de 1917",
    "JUAREZ": "Juárez",
    "LAZARO CARDENAS": "Lázaro Cárdenas",
    "LÁZARO CARDENAS": "Lázaro Cárdenas",
    "MARTIN CARRERA": "Martín Carrera",
    "PANTITLAN": "Pantitlán",
    "POLITECNICO": "Politécnico",
    "TACUBAYA": "Tacubaya",  # no variant — kept as sentinel for test fixtures
}


def _canonicalize(name: str | None) -> str | None:
    if name is None:
        return None
    normalised = name.strip().upper()
    return METRO_STATION_CANONICAL.get(normalised, name)


canonicalize_station_udf = udf(_canonicalize, StringType())


def register_udfs(spark: SparkSession) -> None:
    """Register conformance UDFs for SQL-style use.

    Call once at job startup before any spark.sql() calls that reference
    canonicalize_station. Python DataFrame API callers can use the
    canonicalize_station_udf object directly without calling this.
    """
    spark.udf.register("canonicalize_station", _canonicalize, StringType())
