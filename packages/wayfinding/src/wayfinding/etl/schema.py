"""Output table schemas for the wayfinding ETL pipeline.

Defines Pydantic models for each output table with field types, constraints,
and CRS metadata. These schemas are used for validation and documentation.

Note: These schemas define the logical table structure. In the GeoPackage,
each table is stored as two layers (<table>_26910 and <table>_wgs84) due to
GeoPackage's single-geometry-per-layer constraint. Each physical layer has
ONE registered geometry column named 'geom' in the target CRS, not
separate geom_26910+geom_wgs84 columns in one layer. See ADR-0003.
"""


from pydantic import BaseModel, Field

# CRS constants
CRS_NATIVE = "EPSG:26910"  # NAD83 / UTM zone 10N
CRS_WEB = "EPSG:4326"      # WGS84


class FacilitySchema(BaseModel):
    """Schema for the Facility output table.

    Represents a building or facility (e.g., AQ, SH, ECC).
    """
    facility_id: str = Field(..., description="Unique facility identifier")
    code: str = Field(..., description="3-letter facility code (AQ, SH, ECC)")
    name: str = Field(..., description="Long facility name")
    geom_26910: str = Field(..., description=f"Geometry in {CRS_NATIVE} (WKT or binary)")
    geom_wgs84: str = Field(..., description=f"Geometry in {CRS_WEB} (WKT or binary)")


class LevelSchema(BaseModel):
    """Schema for the Level output table.

    Represents a floor or level within a facility.
    """
    level_id: str = Field(..., description="Unique level identifier")
    facility_id: str = Field(..., description="Foreign key to Facility")
    short_name: str = Field(..., description="Short level name (e.g., '01', 'B1')")
    vertical_order: int = Field(..., description="Vertical ordering for routing (0 = ground)")
    geom_26910: str = Field(..., description=f"Geometry in {CRS_NATIVE} (WKT or binary)")
    geom_wgs84: str = Field(..., description=f"Geometry in {CRS_WEB} (WKT or binary)")


class UnitSchema(BaseModel):
    """Schema for the Unit output table.

    Represents a room, office, or other indoor space.
    """
    unit_id: str = Field(..., description="Unique unit identifier")
    room_id: str | None = Field(None, description="Human-readable room number")
    level_id: str = Field(..., description="Foreign key to Level")
    use_type: str = Field(..., description="Original USE_TYPE from source GDB")
    category: str = Field(..., description="Controlled vocabulary category")
    accessible: bool | None = Field(
        None,
        description="Destination is accessible (e.g., accessible washroom). "
                    "This is NOT route accessibility; see routing profile."
    )
    gender: str | None = Field(
        None, description="Gender (male, female, neutral, unspecified)"
    )
    verified_by: str | None = Field(
        None,
        description=(
            "Provenance of accessibility claim "
            "(e.g., 'source_gdb_use_type', 'facilities_audit_2026')"
        )
    )
    verified_date: str | None = Field(
        None,
        description="ISO 8601 date source was verified (e.g., '2026-08-29'). "
                    "Records source provenance, not ETL run date."
    )
    centroid_26910: str = Field(
        ..., description=f"Centroid geometry in {CRS_NATIVE} (WKT/binary)"
    )
    centroid_method: str = Field(
        ...,
        description="Method used to derive centroid: 'geometry_centroid' or "
                    "'envelope_center_fallback'"
    )
    geom_26910: str = Field(
        ..., description=f"Polygon geometry in {CRS_NATIVE} (WKT/binary)"
    )
    geom_wgs84: str = Field(
        ..., description=f"Polygon geometry in {CRS_WEB} (WKT/binary)"
    )


class LandmarkSchema(BaseModel):
    """Schema for the Landmark output table.

    Represents a landmark or point of interest for wayfinding.
    """
    landmark_id: str = Field(..., description="Unique landmark identifier")
    category: str = Field(..., description="Landmark category (e.g., 'entrance', 'elevator')")
    level_id: str = Field(..., description="Foreign key to Level")
    geom_26910: str = Field(..., description=f"Geometry in {CRS_NATIVE} (WKT or binary)")
    geom_wgs84: str = Field(..., description=f"Geometry in {CRS_WEB} (WKT or binary)")


class DetailSchema(BaseModel):
    """Schema for the Detail output table.

    Represents architectural details from the Details layer (excludes doors).
    """
    detail_id: str = Field(..., description="Unique detail identifier")
    use_type: str = Field(..., description="Detail USE_TYPE from source GDB")
    level_id: str = Field(..., description="Foreign key to Level")
    geom_26910: str = Field(..., description=f"Geometry in {CRS_NATIVE} (WKT or binary)")
    geom_wgs84: str = Field(..., description=f"Geometry in {CRS_WEB} (WKT or binary)")


class DoorSchema(BaseModel):
    """Schema for the Door output table.

    Represents door features (USE_TYPE='ADO') split from Details for instruction hints.
    """
    door_id: str = Field(..., description="Unique door identifier")
    use_type: str = Field(..., description="Door USE_TYPE from source GDB (always 'ADO')")
    level_id: str = Field(..., description="Foreign key to Level")
    geom_26910: str = Field(..., description=f"Geometry in {CRS_NATIVE} (WKT or binary)")
    geom_wgs84: str = Field(..., description=f"Geometry in {CRS_WEB} (WKT or binary)")


class PathwaySchema(BaseModel):
    """Schema for the Pathway output table.

    Represents a walkable path segment within a single level.
    """
    pathway_id: str = Field(..., description="Unique pathway identifier")
    length_3d: float = Field(..., description="3D length in meters")
    level_id: str = Field(..., description="Foreign key to Level")
    geom_26910: str = Field(..., description=f"Geometry in {CRS_NATIVE} (WKT or binary)")
    geom_wgs84: str = Field(..., description=f"Geometry in {CRS_WEB} (WKT or binary)")


class TransitionSchema(BaseModel):
    """Schema for the Transition output table.

    Represents a vertical connection (stairs, elevator, ramp) between levels.
    """
    transition_id: str = Field(..., description="Unique transition identifier")
    mode: str = Field(..., description="Transition mode (stairs, elevator, ramp)")
    length_3d: float = Field(..., description="3D length in meters")
    vertical_order_from: int = Field(..., description="Starting level vertical_order")
    vertical_order_to: int = Field(..., description="Ending level vertical_order")
    geom_26910: str = Field(..., description=f"Geometry in {CRS_NATIVE} (WKT or binary)")
    geom_wgs84: str = Field(..., description=f"Geometry in {CRS_WEB} (WKT or binary)")
