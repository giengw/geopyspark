import json
import shapely.wkt

from geopyspark.geotrellis.constants import (RESAMPLE_METHODS,
                                             OPERATIONS,
                                             NEIGHBORHOODS,
                                             NEARESTNEIGHBOR,
                                             FLOAT,
                                             TILE,
                                             SPATIAL
                                            )

class RasterRDD(object):
    """Holds an RDD of GeoTrellis rasters"""

    __slots__ = ['geopysc', 'rdd_type', 'srdd']

    def __init__(self, geopysc, rdd_type, srdd):
        self.geopysc = geopysc
        self.rdd_type = rdd_type
        self.srdd = srdd

    @classmethod
    def from_numpy_rdd(cls, geopysc, rdd_type, numpy_rdd):
        key = geopysc.map_key_input(rdd_type, False)

        schema = geopysc.create_schema(key)
        ser = geopysc.create_tuple_serializer(schema, key_type=None, value_type=TILE)
        reserialized_rdd = numpy_rdd._reserialize(ser)

        if rdd_type == SPATIAL:
            srdd = \
                    geopysc._jvm.geopyspark.geotrellis.ProjectedRasterRDD.fromAvroEncodedRDD(
                        reserialized_rdd._jrdd, schema)
        else:
            srdd = \
                    geopysc._jvm.geopyspark.geotrellis.TemporalRasterRDD.fromAvroEncodedRDD(
                        reserialized_rdd._jrdd, schema)

        return cls(geopysc, rdd_type, srdd)

    def to_numpy_rdd(self):
        result = self.srdd.toAvroRDD()
        ser = self.geopysc.create_tuple_serializer(result._2(), value_type=TILE)
        return self.geopysc.create_python_rdd(result._1(), ser)

    def collect_metadata(self, extent=None, layout=None, crs=None, tile_size=256):
        """Iterate over RDD records and generate layer metadata desribing the contained rasters.

        Keyword arguments:
        crs -- Ignore CRS from records and use given
        extent -- Specify layout extent, must also specify layout
        layout -- Specify tile layout, must also specify layout
        tile_size -- Pixel dimensions of each tile, if not using layout
        """

        if not crs:
            crs = ""

        if extent and layout:
            json_metadata = self.srdd.collectMetadata(extent, layout, crs)
        elif not extent and not layout:
            json_metadata = self.srdd.collectMetadata(str(tile_size), crs)
        else:
            raise TypeError("Could not collect metadata with {} and {}".format(extent, layout))

        return json.loads(json_metadata)

    def reproject(self, target_crs, resample_method=NEARESTNEIGHBOR):
        """Reproject every individual raster to target_crs, does not sample past tile boundary"""
        assert(resample_method in RESAMPLE_METHODS)
        return RasterRDD(self.geopysc, self.rdd_type,
                         self.srdd.reproject(target_crs, resample_method))

    def cut_tiles(self, layer_metadata, resample_method=NEARESTNEIGHBOR):
        """Cut tiles to layout. May result in duplicate keys"""
        assert(resample_method in RESAMPLE_METHODS)
        srdd = self.srdd.cutTiles(json.dumps(layer_metadata), resample_method)
        return TiledRasterRDD(self.geopysc, self.rdd_type, srdd)

    def tile_to_layout(self, layer_metadata, resample_method=NEARESTNEIGHBOR):
        """Cut tiles to layout and merge overlapping tiles. This will produce unique keys"""
        assert(resample_method in RESAMPLE_METHODS)
        srdd = self.srdd.tileToLayout(json.dumps(layer_metadata), resample_method)
        return TiledRasterRDD(self.geopysc, self.rdd_type, srdd)


class TiledRasterRDD(object):
    """Holds an RDD of GeoTrellis tile layer"""

    __slots__ = ['geopysc', 'rdd_type', 'srdd']

    def __init__(self, geopysc, rdd_type, srdd):
        self.geopysc = geopysc
        self.rdd_type = rdd_type
        self.srdd = srdd

    @property
    def layer_metadata(self):
        """Layer metadata associated with this layer"""
        return json.loads(self.srdd.layerMetadata())

    @property
    def zoom_level(self):
        return self.srdd.getZoom()

    @classmethod
    def from_numpy_rdd(cls, geopysc, rdd_type, numpy_rdd, metadata):
        key = geopysc.map_key_input(rdd_type, True)

        schema = geopysc.create_schema(key)
        ser = geopysc.create_tuple_serializer(schema, key_type=None, value_type=TILE)
        reserialized_rdd = numpy_rdd._reserialize(ser)

        if rdd_type == SPATIAL:
            srdd = \
                    geopysc._jvm.geopyspark.geotrellis.SpatialTiledRasterRDD.fromAvroEncodedRDD(
                        reserialized_rdd._jrdd, schema, json.dumps(metadata))
        else:
            srdd = \
                    geopysc._jvm.geopyspark.geotrellis.TemporalTiledRasterRDD.fromAvroEncodedRDD(
                        reserialized_rdd._jrdd, schema, json.dumps(metadata))

        return cls(geopysc, key, srdd)

    def to_numpy_rdd(self):
        result = self.srdd.toAvroRDD()
        ser = self.geopysc.create_tuple_serializer(result._2(), value_type=TILE)
        return self.geopysc.create_python_rdd(result._1(), ser)

    def reproject(self, target_crs, extent=None, layout=None, scheme=FLOAT, tile_size=256,
                  resolution_threshold=0.1, resample_method=NEARESTNEIGHBOR):
        """Reproject RDD as tiled raster layer, samples surrounding tiles
        `extent` and `layout` may be specified if `scheme` is FLOAT
        """

        assert(resample_method in RESAMPLE_METHODS)

        if extent and layout:
            srdd = self.srdd.reproject(extent, layout, target_crs, resample_method)
        elif not extent and not layout:
            srdd = self.srdd.reproject(scheme, tile_size, resolution_threshold,
                                       target_crs, resample_method)
        else:
            raise TypeError("Could not collect reproject RDD with {} and {}".format(extent, layout))

        return TiledRasterRDD(self.geopysc, self.rdd_type, srdd)

    def tile_to_layout(self, layout, resample_method=NEARESTNEIGHBOR):
        assert(resample_method in RESAMPLE_METHODS)

        srdd = self.srdd.tileToLayout(layout, resample_method)

        return TiledRasterRDD(self.geopysc, self.rdd_type, srdd)

    def pyramid(self, start_zoom, end_zoom, resample_method=NEARESTNEIGHBOR):
        assert(resample_method in RESAMPLE_METHODS)

        size = self.layer_metadata['layoutDefinition']['tileLayout']['tileRows']

        if (size & (size - 1)) != 0:
            raise ValueError("Tiles must have a col and row count that is a power of 2")

        result = self.srdd.pyramid(start_zoom, end_zoom, resample_method)

        return [TiledRasterRDD(self.geopysc, self.rdd_type, srdd) for srdd in result]

    def focal(self, operation, neighborhood, param_1=None, param_2=None, param_3=None):
        assert(operation in OPERATIONS)
        assert(neighborhood in NEIGHBORHOODS)

        if param_1 is None:
            param_1 = 0.0
        if param_2 is None:
            param_2 = 0.0
        if param_3 is None:
            param_3 = 0.0

        srdd = self.srdd.focal(operation, neighborhood, param_1, param_2, param_3)

        return TiledRasterRDD(self.geopysc, self.rdd_type, srdd)

    def stitch(self):
        assert(self.rdd_type == SPATIAL,
               "Only TiledRasterRDDs with a rdd_type of SpatialKey can use stitch()")

        tup = self.srdd.stitch()
        ser = self.geopysc.create_value_serializer(tup._2(), TILE)
        return ser.loads(tup._1())[0]

    def cost_distance(self, geometries, max_distance):
        wkts = [shapely.wkt.dumps(g) for g in geometries]
        srdd = self.srdd.costDistance(self.geopysc.sc, wkts, max_distance)

        return TiledRasterRDD(self.geopysc, self.rdd_type, srdd)