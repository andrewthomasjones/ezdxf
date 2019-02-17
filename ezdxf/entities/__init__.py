# Copyright (c) 2019 Manfred Moitzi
# License: MIT License
# Created 2019-02-13
# New entity system with unified DXF attribute system for DXF R12 and DXF R2000+

# Goals:
# ------
#
# 1. No more wrapped ExtendedTags()
# 2. Store entities as DXFEntity () or inherited instances in the drawing database
# 3. remove separation of legacy and modern tag structures
#    - uses owner tag of DXF R2000+ also for DXF R12
#    - same layout structures (BLOCK_RECORDS, LAYOUT, OBJECTS section)
#    - just don't export DXF R2000+ structures to DXF R12 files
# 4. still store unknown entities (Map3d...) as bunch of tag, but inside of an special DXFEntity (UnknownEntity)
# 5. preserve actual DXFEntity interface, DXFEntity.dxf seem still a good idea - other methods deprecate slowly
# 6. DXFTag and ExtendedTags are no more the main data types - store dxf attributes as object attributes in
#    inherited classes of DXFAttrib() as DXFEntity.dxf attribute
# 7. use individual DXF export functions for each entity, but provide a useful boiler plate
from .dxfentity import DXFEntity, UnknownEntity
from .dxfgfx import DXFGraphic
from .dxfclass import DXFClass
from .line import Line
from .insert import Insert
from .polyline import Polyline
from .lwpolyline import LWPolyline