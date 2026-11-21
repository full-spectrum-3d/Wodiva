from app.water.sources import parcels_parquet


def test_fallback_reads_only_the_voivodeship_file():
    assert parcels_parquet.region_url("141201_1.0001.6509").endswith("/PARQUET/14_dzialki.parquet")
    assert parcels_parquet.region_url("020101_1.0001.12").endswith("/PARQUET/02_dzialki.parquet")
    assert parcels_parquet.region_url("991201_1.0001.1").endswith("/PARQUET/0_dzialki.parquet")
    source = parcels_parquet.data_source(parcel_id="141201_1.0001.6509")
    assert "14_dzialki.parquet" in source.name and source.url.endswith("14_dzialki.parquet")
