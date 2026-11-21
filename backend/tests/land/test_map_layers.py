import numpy as np
import rasterio
from fastapi.testclient import TestClient
from shapely import wkt
from shapely.geometry import box, shape

from app.assistant import kolba
from app.core.main import create_app
from app.land import overlay, service
from app.land.sources import bdot, pigpib

from .test_service import _report


def test_well_gets_wgs84_coordinates():
    feature = {"attributes": {"NR_PKT_MONIT_ILOSC": "II_1"}, "geometry": {"x": 457058.6, "y": 546924.4}}
    well = pigpib._well(feature, 446603.0, 528598.0, None)
    assert 18.0 < well["lon"] < 18.5 and 52.6 < well["lat"] < 52.9


def test_nearest_water_object_has_geometry_and_point():
    transform = rasterio.Affine(5.0, 0, 446000.0, 0, -5.0, 529000.0)
    mask = np.zeros((200, 200), dtype=bool)
    mask[100, 20:180] = True
    mask[60:63, 60:63] = True
    layers = bdot.HydroLayers({"ditch": mask}, transform, 5.0)
    parcel = box(446400, 528300, 446600, 528400)
    point = bdot._nearest_pixel(layers, "ditch", parcel)
    geometry = bdot.component_geometry(layers, "ditch", point, parcel)
    assert geometry is not None and shape(geometry).bounds[0] > 18.0
    assert shape(geometry).length > shape(bdot.component_geometry(layers, "ditch", (446302.5, 528697.5), parcel)).length
    assert set(bdot.nearest_point(point)) == {"lon", "lat"}


def test_ndvi_overlay_png_and_bounds():
    geom = box(500000, 5800000, 500200, 5800200)
    transform = rasterio.Affine(10.0, 0, 499980.0, 0, -10.0, 5800220.0)
    ndvi = np.linspace(0, 0.9, 24 * 24, dtype=np.float32).reshape(24, 24)
    result = overlay.ndvi_overlay(ndvi, transform, 32634, geom)
    assert result["png"][:4] == b"\x89PNG"
    (south, west), (north, east) = result["bounds"]
    assert south < north and west < east and 52.0 < south < 53.0
    assert overlay.from_cache(overlay.to_cache(result))["png"] == result["png"]


def test_report_serves_ndvi_overlay_and_kolba_skips_geometry(monkeypatch, parcel, water, soil, irrigation, land):
    geom = wkt.loads(parcel.geometry_wkt_2180)
    png = overlay.ndvi_overlay(
        np.full((30, 30), 0.6, np.float32),
        rasterio.Affine(10.0, 0, geom.bounds[0] - 50, 0, -10.0, geom.bounds[3] + 50),
        2180,
        geom,
    )
    artifacts = service.collect.LandArtifacts(ndvi=png)
    monkeypatch.setattr(service, "artifacts_for", lambda *a: artifacts)
    land.hydro.features = [
        {
            "group": "ditch",
            "type": "rów melioracyjny",
            "distance_m": 60.0,
            "geometry": {"type": "Point", "coordinates": [22.5, 51.4]},
        }
    ]
    report = _report(parcel, water, soil, irrigation, land)
    info = report.satellite.details["ndvi_overlay"]
    assert info["url"] == f"/api/report/{report.id}/ndvi.png" and info["range"] == [0.0, 0.9]
    client = TestClient(create_app())
    assert client.get(info["url"]).content[:4] == b"\x89PNG"
    assert client.get("/api/report/0123456789ab/ndvi.png").status_code == 404
    assert report.hydro.ditches[0]["geometry"]["type"] == "Point"
    assert '"coordinates"' not in kolba._report_context(report)
