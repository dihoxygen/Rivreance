-- Smoke test for the Rivreance schema, run by CI against a throwaway PostGIS database
-- after applying migrations/0001_init_rivreance.sql and seed.sql.
--
-- The Supabase Preview check that would otherwise exercise this schema is skipped
-- unless the repository is linked to a Supabase branch, so these assertions are the
-- only automated coverage the SQL has. Failures raise, which fails the CI step.

do $$
declare
    n_tables    int;
    n_policies  int;
    n_basins    int;
    unprotected text;
    collection  jsonb;
begin
    -- PostGIS puts spatial_ref_sys in public and owns it, so the schema's own tables are
    -- the ones with no extension dependency. It cannot carry RLS and holds only the
    -- public SRID catalogue, so it is excluded rather than asserted on.
    select count(*) into n_tables
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relkind = 'r'
      and not exists (
          select 1 from pg_depend d where d.objid = c.oid and d.deptype = 'e'
      );
    if n_tables <> 12 then
        raise exception 'expected 12 Rivreance tables in public, found %', n_tables;
    end if;

    -- One public-read policy per table, created by the loop at the end of the migration.
    select count(*) into n_policies from pg_policies where schemaname = 'public';
    if n_policies <> 12 then
        raise exception 'expected 12 public-read policies, found %', n_policies;
    end if;

    -- Without RLS actually enabled the policies above would be decorative, and the
    -- anon key would expose write access rather than the intended read-only view.
    select string_agg(c.relname, ', ') into unprotected
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relkind = 'r'
      and not c.relrowsecurity
      and not exists (
          select 1 from pg_depend d where d.objid = c.oid and d.deptype = 'e'
      );
    if unprotected is not null then
        raise exception 'row level security is disabled on: %', unprotected;
    end if;

    select count(*) into n_basins from public.basins;
    if n_basins <> 2 then
        raise exception 'expected the 2 seeded MVP basins, found %', n_basins;
    end if;

    -- The web and mobile maps both render whatever this RPC returns, so on an empty
    -- basin it has to produce an empty FeatureCollection rather than null.
    collection := public.get_basin_segment_conditions('03160112', 'kayaking', 1);
    if collection is null or collection->>'type' <> 'FeatureCollection' then
        raise exception 'get_basin_segment_conditions returned %', collection;
    end if;
    if jsonb_typeof(collection->'features') <> 'array' then
        raise exception 'get_basin_segment_conditions features was %',
            jsonb_typeof(collection->'features');
    end if;

    -- Argument order here is longitude then latitude, which is easy to transpose.
    perform (select count(*) from public.find_sites_near(-87.261, 33.4845, 50));

    perform (select count(*) from public.v_river_segments);
end
$$;
