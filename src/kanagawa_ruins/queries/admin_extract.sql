-- Both registered views must be EPSG:6677; bind an existing municipality code.
SELECT roads.* FROM roads
WHERE EXISTS (SELECT 1 FROM admin WHERE admin.muni_code = ?
              AND ST_Intersects(roads.geometry, admin.geometry));
