-- Register a normalized EPSG:6677 layer as "layer"; bind xmin,ymin,xmax,ymax in meters.
SELECT * FROM layer WHERE ST_Intersects(geometry, ST_MakeEnvelope(?, ?, ?, ?));
