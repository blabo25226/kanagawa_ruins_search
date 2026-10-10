-- Unknown/non-year vintages remain NULL rather than fabricating a year.
SELECT CASE WHEN regexp_matches(source_vintage, '^[0-9]{4}($|[_-])')
            THEN left(source_vintage, 4) ELSE NULL END AS source_year,
       count(*) AS feature_count
FROM layer GROUP BY ALL ORDER BY ALL;
