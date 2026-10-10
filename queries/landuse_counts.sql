-- L03-b source_vintage includes the mesh partition; its first 4 characters are the verified year.
SELECT left(source_vintage, 4) AS source_year, landuse_code, landuse_label,
       count(*) AS feature_count
FROM landuse GROUP BY ALL ORDER BY ALL;
