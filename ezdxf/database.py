# Purpose: database module
# Created: 11.03.2011
# Copyright (c) 2011-2018, Manfred Moitzi
# License: MIT License
from typing import Optional, Iterable, Tuple
from ezdxf.tools.handle import HandleGenerator
from ezdxf.lldxf.const import DXFValueError
from ezdxf.lldxf.tags import DXFTag
from ezdxf.lldxf.extendedtags import ExtendedTags
from ezdxf.dxfentity import DXFEntity

# todo: delete database model - when new entity system works


class EntityDB:
    """ A simple key/value database a.k.a. dict(), but can be replaced by other classes that implements all of the
    methods of `EntityDB`. The entities have no order.

    The old Data Model

    Every entity/object, except tables and sections, are represented as tag-list (see ExtendedTags Class), this lists
    are stored in the drawing-associated database, database-key is the 'handle' tag (code == 5 or 105).

    For the entity/object manipulation this tag-list will be wrapped into separated classes, which are generated by
    the dxffactory-object. The dxffactory-object generates DXF-Version specific wrapper classes.

    """

    def __init__(self, dxffactory=None):
        self._database = {}
        self.handles = HandleGenerator()
        self.dxffactory = dxffactory

    def __delitem__(self, handle: str) -> None:
        del self._database[handle]

    def __getitem__(self, handle: str) -> ExtendedTags:
        return self._database[handle]

    def get(self, handle: str) -> Optional[ExtendedTags]:
        try:
            return self.__getitem__(handle)
        except KeyError:  # internal exception
            return None

    def __setitem__(self, handle: str, tags: ExtendedTags) -> None:
        self._database[handle] = tags

    def __contains__(self, handle: str) -> bool:
        """ Database contains handle? """
        return handle in self._database

    def __len__(self) -> int:
        """ Count of database items. """
        return len(self._database)

    def __iter__(self) -> Iterable[str]:
        """ Iterate over all handles. """
        return iter(self._database.keys())

    def keys(self) -> Iterable[str]:
        """ Iterate over all handles. """
        return self._database.keys()

    def values(self) -> Iterable[ExtendedTags]:
        """ Iterate over all entities. """
        return self._database.values()

    def items(self) -> Iterable[Tuple[str, ExtendedTags]]:
        """ Iterate over all (handle, entities) pairs. """
        return self._database.items()

    def add_tags(self, tags: ExtendedTags) -> str:
        try:
            handle = tags.get_handle()
        except DXFValueError:  # create new handle
            handle = self.get_unique_handle()
            handle_code = 105 if tags.dxftype() == 'DIMSTYLE' else 5  # legacy shit!!!
            tags.noclass.insert(1, DXFTag(handle_code, handle))  # handle should be the 2. tag

        self.__setitem__(handle, tags)
        return handle

    def delete_entity(self, entity: DXFEntity) -> None:
        entity.destroy()
        self.delete_handle(entity.dxf.handle)

    def delete_handle(self, handle: str) -> None:
        del self._database[handle]

    def get_unique_handle(self) -> str:
        while True:
            handle = self.handles.next()
            if handle not in self._database:  # you can not trust $HANDSEED value
                return handle

    def duplicate_tags(self, tags: ExtendedTags) -> ExtendedTags:
        """
        Deep copy of tags with new handle and duplicated linked entities (VERTEX, ATTRIB, SEQEND) with also new handles.
        An existing owner tag is not changed because this is not the domain of the EntityDB() class.
        The new entity tags are added to the drawing database.

        This is not a deep copy in the meaning of Python, because handle and link is changed.
        
        """
        new_tags = tags.clone()
        new_tags.noclass.replace_handle(self.get_unique_handle())  # set new handle
        self.add_tags(new_tags)  # add new tags to database
        source_link = tags.link  # follow link structure of original entity
        parent_copy = new_tags
        while source_link is not None:  # duplicate linked entities (VERTEX, ATTRIB, SEQEND)
            source_linked_entity = self.get(source_link)  # extended tags
            linked_entity_copy = source_linked_entity.clone()
            new_handle = self.get_unique_handle()
            linked_entity_copy.noclass.replace_handle(new_handle)  # set new handle
            self.add_tags(linked_entity_copy)  # add new tags to database
            parent_copy.link = new_handle
            source_link = source_linked_entity.link  # follow link structure of original entity
            parent_copy = linked_entity_copy
        return new_tags
