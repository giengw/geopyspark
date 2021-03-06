import os
import unittest
import numpy as np

import pytest

from shapely.geometry import Polygon, MultiPolygon
from geopyspark.tests.base_test_class import BaseTestClass
from geopyspark.geotrellis.rdd import TiledRasterRDD
from geopyspark.geotrellis.constants import SPATIAL


class CostDistanceTest(BaseTestClass):
    data = np.array([[
        [1.0, 1.0, 1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0, 1.0, 0.0]]])

    layer = [({'row': 0, 'col': 0}, {'no_data_value': -1.0, 'data': data}),
             ({'row': 1, 'col': 0}, {'no_data_value': -1.0, 'data': data}),
             ({'row': 0, 'col': 1}, {'no_data_value': -1.0, 'data': data}),
             ({'row': 1, 'col': 1}, {'no_data_value': -1.0, 'data': data})]
    rdd = BaseTestClass.geopysc.pysc.parallelize(layer)

    extent = {'xmin': 0.0, 'ymin': 0.0, 'xmax': 33.0, 'ymax': 33.0}
    layout = {'layoutCols': 2, 'layoutRows': 2, 'tileCols': 5, 'tileRows': 5}
    metadata = {'cellType': 'float32ud-1.0',
                'extent': extent,
                'crs': '+proj=longlat +datum=WGS84 +no_defs ',
                'bounds': {
                    'minKey': {'col': 0, 'row': 0},
                    'maxKey': {'col': 1, 'row': 1}},
                'layoutDefinition': {
                    'extent': extent,
                    'tileLayout': {'tileCols': 5, 'tileRows': 5, 'layoutCols': 2, 'layoutRows': 2}}}

    tiled_rdd = TiledRasterRDD.from_numpy_rdd(BaseTestClass.geopysc, SPATIAL, rdd, metadata)

    @pytest.fixture(autouse=True)
    def tearDown(self):
        yield
        BaseTestClass.geopysc.pysc._gateway.close()

    def test_polygonal_min(self):
        polygon = Polygon([(0.0, 0.0), (0.0, 33.0), (33.0, 33.0), (33.0, 0.0), (0.0, 0.0)])
        result = self.tiled_rdd.polygonal_min(polygon, float)

        self.assertEqual(result, 0.0)

    def test_polygonal_max(self):
        polygon = Polygon([(1.0, 1.0), (1.0, 10.0), (10.0, 10.0), (10.0, 1.0)])
        result = self.tiled_rdd.polygonal_max(polygon, float)

        self.assertEqual(result, 1.0)

    def test_polygonal_sum(self):
        polygon = Polygon([(0.0, 0.0), (0.0, 33.0), (33.0, 33.0), (33.0, 0.0), (0.0, 0.0)])
        result = self.tiled_rdd.polygonal_sum(polygon, float)

        self.assertEqual(result, 96.0)

    def test_polygonal_mean(self):
        polygon = Polygon([(1.0, 1.0), (1.0, 10.0), (10.0, 10.0), (10.0, 1.0)])
        result = self.tiled_rdd.polygonal_mean(polygon)

        self.assertEqual(result, 1.0)


if __name__ == "__main__":
    unittest.main()
