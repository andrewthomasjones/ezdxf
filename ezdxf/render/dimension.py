# Created: 28.12.2018
# Copyright (C) 2018-2019, Manfred Moitzi
# License: MIT License
from typing import TYPE_CHECKING, Tuple, Iterable, List, Sequence
import math
from ezdxf.algebra import Vector, ConstructionRay, xround, ConstructionLine
from ezdxf.algebra import UCS, PassTroughUCS
from ezdxf.lldxf import const
from ezdxf.options import options
from ezdxf.lldxf.const import DXFValueError, DXFUndefinedBlockError
from ezdxf.tools import suppress_zeros, raise_decimals
from ezdxf.render.arrows import ARROWS, connection_point

if TYPE_CHECKING:
    from ezdxf.eztypes import Dimension, BlockLayout, Vertex, DimStyleOverride, Style


class DimensionBase:
    def __init__(self, dimension: 'Dimension', block: 'BlockLayout', ucs: 'UCS' = None,
                 override: 'DimStyleOverride' = None):
        self.drawing = dimension.drawing
        self.dimension = dimension
        self.dxfversion = self.drawing.dxfversion
        self.supports_dxf_r2000 = self.dxfversion >= 'AC1015'
        self.block = block
        if override:
            self.dim_style = override
        else:
            self.dim_style = self.dimension.dimstyle_override()
        self.ucs = ucs or PassTroughUCS()
        self.requires_extrusion = self.ucs.uz != (0, 0, 1)
        if self.requires_extrusion:  # set extrusion vector of DIMENSION entity
            self.dimension.dxf.extrusion = self.ucs.uz

        self.user_location_override = self.dimension.get_flag_state(self.dimension.USER_LOCATION_OVERRIDE,
                                                                    name='dimtype')
        self.default_color = self.dimension.dxf.color
        get = self.dim_style.get
        self.dim_scale = get('dimscale', 1)  # ignored by ezdxf
        self.dim_measurement_factor = get('dimlfac', 1)

        # text properties
        self.text_style_name = get('dimtxsty', options.default_dimension_text_style)
        self.text_style = self.drawing.styles.get(self.text_style_name)
        self.text_height = self.char_height
        self.text_width_factor = self.text_style.get_dxf_attrib('width', 1.)
        self.text_gap = get('dimgap', 0.625)
        self.text_rotation = self.dimension.get_dxf_attrib('text_rotation', None)
        self.text_color = get('dimclrt', self.default_color)

        # text_halign = 0: center; 1: left; 2: right; 3: above ext1; 4: above ext2
        self.text_halign = get('dimjust', 0)

        # text_valign = 0: center; 1: above; 2: farthest away?; 3: JIS?; 4: below (2, 3 ignored by ezdxf)
        self.text_valign = get('dimtad', 0)

        self.text_movement_rule = get('dimtmove', 0)
        self.text_inside_horizontal = get('dimtih', 0)  # ignored by ezdxf
        self.text_outside_horizontal = get('dimtoh', 0)  # ignored by ezdxf
        self.force_text_inside = bool(get('dimtix', 0))

        # arrow properties
        self.tick_size = get('dimtsz')
        if self.tick_size > 0:
            self.arrow1_name, self.arrow2_name = None, None
        else:
            # arrow name or block name if user defined arrow
            self.arrow1_name, self.arrow2_name = self.dim_style.get_arrow_names()
        self.arrow_size = get('dimasz')

        # dimension line properties
        self.dim_line_color = get('dimclrd', self.default_color)
        self.dim_line_extension = bool(get('dimdle', 0.))
        self.dim_linetype = get('dimltype', None)
        self.dim_lineweight = get('dimlwd', const.LINEWEIGHT_BYBLOCK)
        self.suppress_dim1_line = bool(get('dimsd1', 0))
        self.suppress_dim2_line = bool(get('dimsd2', 0))

        # extension line properties
        self.ext_line_color = get('dimclre', self.default_color)
        self.ext1_linetype_name = get('dimltex1', None)
        self.ext2_linetype_name = get('dimltex2', None)
        self.ext_lineweight = get('dimlwe', const.LINEWEIGHT_BYBLOCK)
        self.suppress_ext1_line = bool(get('dimse1', False))
        self.suppress_ext2_line = bool(get('dimse2', False))
        self.ext_line_extension = get('dimexe', 0.)
        self.ext_line_offset = get('dimexo', 0.)
        self.ext_line_fixed = bool(get('dimexfix', False))
        self.ext_line_length = bool(get('dimexlen', self.ext_line_extension))

    @property
    def char_height(self) -> float:
        height = self.text_style.get_dxf_attrib('height', 0)
        if height == 0:  # variable text height (not fixed)
            height = self.dim_style.get('dimtxt', 1.)
        return height

    def text_width(self, text: str) -> float:
        char_width = self.text_height * self.text_width_factor
        return len(text) * char_width

    def default_attributes(self) -> dict:
        return {
            'layer': self.dimension.dxf.layer,
            'color': self.dimension.dxf.color,
        }

    def wcs(self, point: 'Vertex') -> Vector:
        return self.ucs.to_wcs(point)

    def ocs(self, point: 'Vertex') -> Vector:
        return self.ucs.to_ocs(point)

    def text_override(self, measurement: float) -> str:
        text = self.dimension.dxf.text
        if text == ' ':  # suppress text
            return ''
        elif text == '' or text == '<>':  # measured distance
            return self.format_text(measurement)
        else:  # user override
            return text

    def format_text(self, value: float) -> str:
        dimrnd = self.dim_style.get('dimrnd', None)
        dimdec = self.dim_style.get('dimdec', None)
        dimzin = self.dim_style.get('dimzin', 0)
        dimdsep = self.dim_style.get('dimdsep', '.')
        dimpost = self.dim_style.get('dimpost', '<>')
        return format_text(value, dimrnd, dimdec, dimzin, dimdsep, dimpost)

    def add_line(self, start: 'Vertex', end: 'Vertex', dxfattribs: dict = None) -> None:
        attribs = self.default_attributes()
        if dxfattribs:
            attribs.update(dxfattribs)
        self.block.add_line(self.wcs(start), self.wcs(end), dxfattribs=attribs)

    def add_blockref(self, name: str, insert: 'Vertex', rotation: float = 0,
                     scale: float = 1., dxfattribs: dict = None) -> Vector:
        if name in ARROWS:  # generates automatically BLOCK definitions for arrows if needed
            self.block.add_arrow_blockref(name, insert=insert, size=scale, rotation=rotation, dxfattribs=dxfattribs)
        else:
            if name not in self.drawing.blocks:
                raise DXFUndefinedBlockError('Undefined block: "{}"'.format(name))

            attribs = self.default_attributes()
            attribs['rotation'] = rotation
            if scale != 1.:
                attribs['xscale'] = scale
                attribs['yscale'] = scale
            if self.requires_extrusion:
                attribs['extrusion'] = self.ucs.uz
            if dxfattribs:
                attribs.update(dxfattribs)
            self.block.add_blockref(name, insert=self.ocs(insert), dxfattribs=attribs)
            return insert

    def add_text(self, text: str, pos: 'Vertex', rotation: float, align='MIDDLE_CENTER',
                 dxfattribs: dict = None) -> None:
        # todo: ucs to ocs
        attribs = self.default_attributes()
        attribs['rotation'] = rotation
        attribs['style'] = self.text_style_name

        if self.dxfversion > 'AC1009':
            attribs['char_height'] = self.char_height
            attribs['insert'] = pos
            attribs['attachment_point'] = self.dimension.get_dxf_attrib('align', const.MTEXT_ALIGN_FLAGS.get(align, 5))
            if dxfattribs:
                attribs.update(dxfattribs)
            self.block.add_mtext(text, dxfattribs=attribs)
        else:
            attribs['height'] = self.char_height
            if dxfattribs:
                attribs.update(dxfattribs)
            dxftext = self.block.add_text(text, dxfattribs=attribs)
            dxftext.set_pos(self.ocs(pos), align=align)

    def add_defpoints(self, points: Iterable['Vertex']) -> None:
        attribs = {
            'layer': 'DEFPOINTS',
        }
        for point in points:
            self.block.add_point(self.wcs(point), dxfattribs=attribs)

    def add_leader(self, p1: Vector, p2: Vector, p3: Vector, dxfattribs: dict = None) -> None:
        self.add_line(p1, p2, dxfattribs)
        self.add_line(p2, p3, dxfattribs)


class LinearDimension(DimensionBase):
    def __init__(self, dimension: 'Dimension', block: 'BlockLayout', ucs: 'UCS' = None,
                 override: 'DimStyleOverride' = None):
        super().__init__(dimension, block, ucs, override)

        self.dim_line_angle = self.dimension.get_dxf_attrib('angle', 0)
        self.dim_line_angle_rad = math.radians(self.dim_line_angle)
        self.ext_line_angle = self.dim_line_angle + 90  # todo: oblique angle
        self.ext_line_angle_rad = math.radians(self.ext_line_angle)

        if self.text_rotation is None:
            # text_inside_horizontal: not supported by ezdxf, use text_rotation attribute
            # text_outside_horizontal: not supported by ezdxf, use text_rotation attribute
            # text is aligned to dimension line
            self.text_rotation = self.dim_line_angle
            if self.text_halign in (3, 4):  # text above extension line, rotated about 90 degrees
                self.text_rotation += 90

        self.ext1_line_start = self.dimension.dxf.defpoint2
        self.ext2_line_start = self.dimension.dxf.defpoint3

        ext1_ray = ConstructionRay(self.ext1_line_start, angle=self.ext_line_angle_rad)
        ext2_ray = ConstructionRay(self.ext2_line_start, angle=self.ext_line_angle_rad)

        # text_movement_rule: 0 = Moves the dimension line with dimension text
        if self.user_location_override and self.text_movement_rule == 0:
            dim_line_ray = ConstructionRay(self.dimension.dxf.text_midpoint, angle=self.dim_line_angle_rad)
        else:
            dim_line_ray = ConstructionRay(self.dimension.dxf.defpoint, angle=self.dim_line_angle_rad)

        self.dim_line_start = dim_line_ray.intersect(ext1_ray)
        self.dim_line_end = dim_line_ray.intersect(ext2_ray)
        self.dimension.dxf.defpoint = self.dim_line_start  # set defpoint to expected location
        self.measurement = (self.dim_line_end - self.dim_line_start).magnitude
        self.text = self.text_override(self.measurement * self.dim_measurement_factor)
        self.text_location = None
        self.text_box = None
        self.text_outside = False
        self.required_text_space = None
        if self.text:
            self.dim_text_width = self.text_width(self.text)
            self.required_text_space = self.dim_text_width + 2 * (self.arrow_size + self.text_gap)
            if not self.force_text_inside:
                self.text_outside = self.required_text_space > self.measurement
            self.text_location = self.get_text_location(self.dim_text_width, self.text_outside)
            self.text_box = TextBox(
                center=self.text_location,
                width=self.dim_text_width,
                height=self.text_height,
                angle=self.text_rotation,
                # shrink gap slightly, to avoid congruent borders of text box and dimension line for standard
                # text locations above and below dimension line
                gap=self.text_gap * .99
            )

        self.required_arrows_space = 2 * self.arrow_size + self.text_gap
        self.arrows_outside = self.required_arrows_space > self.measurement

    def render(self):
        # add measurement text
        if self.text:
            self.add_measurement_text(self.text, self.text_location, self.text_rotation)
            # add leader
            if self.user_location_override and self.text_movement_rule == 1:
                target_point = self.dim_line_start.lerp(self.dim_line_end)
                corners = self.text_box.corners
                self.add_leader(target_point, corners[0], corners[1])

        # add extension line 1
        if not self.suppress_ext1_line:
            start, end = self.extension_line_points(self.ext1_line_start, self.dim_line_start)
            self.add_extension_line(start, end, linetype=self.ext1_linetype_name)

        # add extension line 2
        if not self.suppress_ext2_line:
            start, end = self.extension_line_points(self.ext2_line_start, self.dim_line_end)
            self.add_extension_line(start, end, linetype=self.ext2_linetype_name)

        # add arrow symbols (block references), also adjust dimension line start and end point
        dim_line_start, dim_line_end = self.add_arrows(
            self.dim_line_start,
            self.dim_line_end,
            self.arrows_outside,
        )

        # add dimension line
        self.add_dimension_line(dim_line_start, dim_line_end)

        # add POINT entities at definition points
        self.add_defpoints([self.dim_line_start, self.ext1_line_start, self.ext2_line_start])

        # transform ucs coordinates into WCS and OCS
        self.defpoints_to_wcs()

    def defpoints_to_wcs(self) -> None:
        def from_ucs(attr, func):
            point = self.dimension.get_dxf_attrib(attr)
            self.dimension.set_dxf_attrib(attr, func(point))

        from_ucs('defpoint', self.wcs)
        from_ucs('defpoint2', self.wcs)
        from_ucs('defpoint3', self.wcs)
        from_ucs('text_midpoint', self.ocs)

    def add_measurement_text(self, dim_text: str, pos: Vector, rotation: float) -> None:
        attribs = {
            'color': self.text_color,
        }
        self.add_text(dim_text, pos=pos, rotation=rotation, dxfattribs=attribs)

    def add_dimension_line(self, start: 'Vertex', end: 'Vertex') -> None:
        def order(a: Vector, b: Vector) -> Tuple[Vector, Vector]:
            if (start - a).magnitude < (start - b).magnitude:
                return a, b
            else:
                return b, a

        direction = (end - start).normalize()
        extension = direction * self.dim_line_extension
        if self.arrow1_name is None or ARROWS.has_extension_line(self.arrow1_name):
            start = start - extension
        if self.arrow2_name is None or ARROWS.has_extension_line(self.arrow2_name):
            end = end + extension

        attribs = {
            'color': self.dim_line_color
        }
        if self.dim_linetype is not None:
            attribs['linetype'] = self.dim_linetype

        # lineweight requires DXF R2000 or later
        if self.supports_dxf_r2000:
            attribs['lineweight'] = self.dim_lineweight

        if self.text_box:  # is dimension line crossing text
            intersection_points = self.text_box.intersect(ConstructionLine(start, end))
        else:
            intersection_points = []
        if len(intersection_points) == 2:
            # sort all points, line[0-1] - gap - line[2-3]
            intersection_points.extend([start, end])
            p1, p2 = order(intersection_points[0], intersection_points[1])

            if not self.suppress_dim1_line:
                self.add_line(start, p1, dxfattribs=attribs)
            if not self.suppress_dim2_line:
                self.add_line(p2, end, dxfattribs=attribs)

        else:  # no intersection
            self.add_line(start, end, dxfattribs=attribs)

    def extension_line_points(self, start: 'Vertex', end: 'Vertex') -> Tuple[Vector, Vector]:
        """
        Adjust start and end point of extension line by dimension variables DIMEXE, DIMEXO, DIMEXFIX, DIMEXLEN.

        Args:
            start: start point of extension line (measurement point)
            end: end point at dimension line

        Returns: adjusted start and end point

        """
        direction = (end - start).normalize()
        if self.ext_line_fixed:
            start = end - (direction * self.ext_line_length)
        else:
            start = start + direction * self.ext_line_offset
        end = end + direction * self.ext_line_extension
        return start, end

    def add_extension_line(self, start: 'Vertex', end: 'Vertex', linetype: str = None) -> None:
        attribs = {
            'color': self.ext_line_color
        }
        if linetype is not None:
            attribs['linetype'] = linetype

        # lineweight requires DXF R2000 or later
        if self.supports_dxf_r2000:
            attribs['lineweight'] = self.ext_lineweight

        self.add_line(start, end, dxfattribs=attribs)

    def add_arrows(self, start: 'Vertex', end: 'Vertex', outside: bool = False) -> Tuple[Vector, Vector]:
        attribs = {
            'color': self.dim_line_color,
        }

        if self.tick_size > 0.:  # oblique stroke, but double the size
            self.block.add_arrow(
                ARROWS.oblique,
                insert=start,
                rotation=self.dim_line_angle,
                size=self.tick_size * 2,
                dxfattribs=attribs,
            )
            self.block.add_arrow(
                ARROWS.oblique,
                insert=end,
                rotation=self.dim_line_angle,
                size=self.tick_size * 2,
                dxfattribs=attribs,
            )
        else:
            scale = self.arrow_size
            start_angle = self.dim_line_angle + 180.
            end_angle = self.dim_line_angle
            if outside:
                start_angle, end_angle = end_angle, start_angle
            self.add_blockref(self.arrow1_name, insert=start, scale=scale, rotation=start_angle,
                              dxfattribs=attribs)  # reverse
            self.add_blockref(self.arrow2_name, insert=end, scale=scale, rotation=end_angle, dxfattribs=attribs)
            if not outside:
                start = connection_point(self.arrow1_name, start, scale, start_angle)
                end = connection_point(self.arrow2_name, end, scale, end_angle)

        if outside:  # add extension lines to arrows if outside
            def has_arrow_extension(name: str) -> bool:
                return (name is not None) and (name in ARROWS) and (name not in ARROWS.ORIGIN_ZERO)

            arrow_vector = (end - start).normalize(self.arrow_size)
            # extension line for first arrow
            if has_arrow_extension(self.arrow1_name):  # just for arrows
                start_ = start - arrow_vector
                end_ = start_ - arrow_vector
                self.block.add_line(start_, end_, dxfattribs=attribs)
            # extension line for second arrow
            if has_arrow_extension(self.arrow2_name):  # just for arrows
                start_ = end + arrow_vector
                end_ = start_ + arrow_vector
                self.block.add_line(start_, end_, dxfattribs=attribs)

        return start, end

    @property
    def vertical_factor(self) -> float:
        """text_valign as factor: returns 1 for above, 0 for center and -1 for below dimension line"""
        if self.text_valign == 0:
            return 0
        elif self.text_valign == 4:
            return -1
        else:
            return 1

    def text_vertical_distance(self) -> float:
        """
        Returns the vertical distance for dimension line to text midpoint. Positive values are above the line, negative
        values are below the line.
        """
        return (self.text_height / 2. + self.text_gap) * self.vertical_factor

    def get_text_location(self, text_width: float, text_outside: bool = False) -> Vector:
        """
        Calculate text midpoint in drawing units.

        Args:
            text_width: text with in drawing units
            text_outside: place text outside of extension lines, applies only for dimjust = 0, 1 or 2

        """
        start = self.dim_line_start
        end = self.dim_line_end
        # todo: text location outside
        if self.user_location_override:
            text_location = self.dimension.get_dxf_attrib('text_midpoint')
            if self.text_movement_rule == 0:
                # text_location defines the text location along the dimension line
                # vertical distance from dimension line to text midpoint, normal to the dimension line
                vdist = self.text_vertical_distance()
            else:  # move text freely by text_midpoint
                return text_location
        else:
            # default location: above the dimension line and centered between extension lines
            text_location = start.lerp(end)
            offset = self.text_gap + self.arrow_size + text_width / 2
            if self.text_halign == 1:  # positions the text next to the first extension line
                text_location = start + (end - start).normalize(offset)
            elif self.text_halign == 2:  # positions the text next to the second extension line
                text_location = end + (start - end).normalize(offset)
            elif self.text_halign in (
                    3, 4):  # positions the text above and aligned with the first/second extension line
                dist = self.text_gap + self.text_height / 2.
                _offset = (start - end).normalize(dist) * self.vertical_factor
                if self.text_halign == 3:
                    text_location = start + _offset
                else:
                    text_location = end + _offset

            self.dimension.set_dxf_attrib('text_midpoint', text_location)
            if self.text_halign in (0, 1, 2):
                vdist = self.text_vertical_distance()
            else:
                vdist = offset

        # lift text location
        ortho = (end - start).orthogonal().normalize(vdist)
        return text_location + ortho


class DimensionRenderer:
    def dispatch(self, dimension: 'Dimension', ucs: 'UCS', override: 'DimStyleOverride' = None) -> None:
        dwg = dimension.drawing
        block = dwg.blocks.new_anonymous_block(type_char='D')
        dimension.dxf.geometry = block.name
        dim_type = dimension.dim_type

        if dim_type in (0, 1):
            self.linear(dimension, block, ucs, override)
        elif dim_type == 2:
            self.angular(dimension, block, ucs, override)
        elif dim_type == 3:
            self.diameter(dimension, block, ucs, override)
        elif dim_type == 4:
            self.radius(dimension, block, ucs, override)
        elif dim_type == 5:
            self.angular3p(dimension, block, ucs, override)
        elif dim_type == 6:
            self.ordinate(dimension, block, ucs, override)
        else:
            raise DXFValueError("Unknown DIMENSION type: {}".format(dim_type))

    def linear(self, dimension: 'Dimension', block: 'BlockLayout', ucs: 'UCS', override: 'DimStyleOverride' = None):
        """
        Call renderer for linear dimension lines: horizontal, vertical and rotated
        """
        render = LinearDimension(dimension, block, ucs, override)
        render.render()

    def angular(self, dimension: 'Dimension', block: 'BlockLayout', ucs: 'UCS', override: 'DimStyleOverride' = None):
        raise NotImplemented

    def diameter(self, dimension: 'Dimension', block: 'BlockLayout', ucs: 'UCS', override: 'DimStyleOverride' = None):
        raise NotImplemented

    def radius(self, dimension: 'Dimension', block: 'BlockLayout', ucs: 'UCS', override: 'DimStyleOverride' = None):
        raise NotImplemented

    def angular3p(self, dimension: 'Dimension', block: 'BlockLayout', ucs: 'UCS', override: 'DimStyleOverride' = None):
        raise NotImplemented

    def ordinate(self, dimension: 'Dimension', block: 'BlockLayout', ucs: 'UCS', override: 'DimStyleOverride' = None):
        raise NotImplemented


def format_text(value: float, dimrnd: float = None, dimdec: int = None, dimzin: int = 0, dimdsep: str = '.',
                dimpost: str = '<>', raisedec=False) -> str:
    if dimrnd is not None:
        value = xround(value, dimrnd)

    if dimdec is None:
        fmt = "{:f}"
        dimzin = dimzin | 8  # remove pending zeros for undefined decimal places, '{:f}'.format(0) -> '0.000000'
    else:
        fmt = "{:." + str(dimdec) + "f}"
    text = fmt.format(value)

    leading = bool(dimzin & 4)
    pending = bool(dimzin & 8)
    text = suppress_zeros(text, leading, pending)
    if raisedec:
        text = raise_decimals(text)
    if dimdsep != '.':
        text = text.replace('.', dimdsep)
    if dimpost:
        if '<>' in dimpost:
            fmt = dimpost.replace('<>', '{}', 1)
            text = fmt.format(text)
        else:
            raise DXFValueError('Invalid dimpost string: "{}"'.format(dimpost))
    return text


class TextBox:
    def __init__(self, center: 'Vertex', width: float, height: float, angle: float, gap: float = 0.):
        self.center = Vector(center)
        w2 = Vector.from_deg_angle(angle, width / 2 + gap)
        h2 = Vector.from_deg_angle(angle + 90, height / 2 + gap)
        self.corners = (
            self.center - w2 - h2,  # lower left
            self.center + w2 - h2,  # lower right
            self.center + w2 + h2,  # upper right
            self.center - w2 + h2,  # upper left
        )

    def __str__(self):
        vstr = ', '.join(str(c) for c in self.corners)
        return "TextBox({})".format(vstr)

    def border_lines(self) -> Sequence[ConstructionLine]:
        p1, p2, p3, p4 = self.corners
        return (
            ConstructionLine(p1, p2),
            ConstructionLine(p2, p3),
            ConstructionLine(p3, p4),
            ConstructionLine(p4, p1),
        )

    def intersect(self, line: ConstructionLine) -> List[Vector]:
        """
        Returns 0, 1 or 2 intersection points between `line` and `TextBox` border lines.

        Args:
            line: line to intersect with border lines

        Returns: list of intersection points

        """
        result = set()
        for border_line in self.border_lines():
            p = line.intersect(border_line)
            if p is not None:
                result.add(p)
        return sorted(result)
