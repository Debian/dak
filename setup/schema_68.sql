--
-- PostgreSQL database dump
--

SET statement_timeout = 0;
SET client_encoding = 'SQL_ASCII';
SET standard_conforming_strings = off;
SET check_function_bodies = false;
SET client_min_messages = warning;
SET escape_string_warning = off;

--
-- Name: audit; Type: SCHEMA; Schema: -; Owner: dak
--

CREATE SCHEMA audit;


ALTER SCHEMA audit OWNER TO dak;

SET search_path = public, pg_catalog;

--
-- Name: bin_associations_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION bin_associations_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM bin_associations$$;


ALTER FUNCTION public.bin_associations_id_max() OWNER TO dak;

--
-- Name: binaries_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION binaries_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM binaries$$;


ALTER FUNCTION public.binaries_id_max() OWNER TO dak;

--
-- Name: dsc_files_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION dsc_files_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM dsc_files$$;


ALTER FUNCTION public.dsc_files_id_max() OWNER TO dak;

--
-- Name: files_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION files_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM files$$;


ALTER FUNCTION public.files_id_max() OWNER TO dak;

--
-- Name: override_type_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION override_type_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM override_type$$;


ALTER FUNCTION public.override_type_id_max() OWNER TO dak;

--
-- Name: priority_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION priority_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM priority$$;


ALTER FUNCTION public.priority_id_max() OWNER TO dak;

--
-- Name: section_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION section_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM section$$;


ALTER FUNCTION public.section_id_max() OWNER TO dak;

--
-- Name: source_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION source_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM source$$;


ALTER FUNCTION public.source_id_max() OWNER TO dak;

--
-- Name: space_concat(text, text); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION space_concat(text, text) RETURNS text
    LANGUAGE sql
    AS $_$select case
WHEN $2 is null or $2 = '' THEN $1
WHEN $1 is null or $1 = '' THEN $2
ELSE $1 || ' ' || $2
END$_$;


ALTER FUNCTION public.space_concat(text, text) OWNER TO dak;

--
-- Name: src_associations_id_max(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION src_associations_id_max() RETURNS integer
    LANGUAGE sql
    AS $$SELECT max(id) FROM src_associations$$;


ALTER FUNCTION public.src_associations_id_max() OWNER TO dak;

--
-- Name: tfunc_set_modified(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION tfunc_set_modified() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN NEW.modified = now(); return NEW; END;
    $$;


ALTER FUNCTION public.tfunc_set_modified() OWNER TO dak;

--
-- Name: trigger_binsrc_assoc_update(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION trigger_binsrc_assoc_update() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO public, pg_temp
    AS $$
DECLARE
  v_data RECORD;

  v_package audit.package_changes.package%TYPE;
  v_version audit.package_changes.version%TYPE;
  v_architecture audit.package_changes.architecture%TYPE;
  v_suite audit.package_changes.suite%TYPE;
  v_event audit.package_changes.event%TYPE;
  v_priority audit.package_changes.priority%TYPE;
  v_component audit.package_changes.component%TYPE;
  v_section audit.package_changes.section%TYPE;
BEGIN
  CASE TG_OP
    WHEN 'INSERT' THEN v_event := 'I'; v_data := NEW;
    WHEN 'DELETE' THEN v_event := 'D'; v_data := OLD;
    ELSE RAISE EXCEPTION 'trigger called for invalid operation (%)', TG_OP;
  END CASE;

  SELECT suite_name INTO STRICT v_suite FROM suite WHERE id = v_data.suite;

  CASE TG_TABLE_NAME
    WHEN 'bin_associations' THEN
      SELECT package, version, arch_string
        INTO STRICT v_package, v_version, v_architecture
        FROM binaries LEFT JOIN architecture ON (architecture.id = binaries.architecture)
        WHERE binaries.id = v_data.bin;

      SELECT component.name, priority.priority, section.section
        INTO v_component, v_priority, v_section
        FROM override
             JOIN override_type ON (override.type = override_type.id)
             JOIN priority ON (priority.id = override.priority)
             JOIN section ON (section.id = override.section)
             JOIN component ON (override.component = component.id)
             JOIN suite ON (suite.id = override.suite)
        WHERE override_type.type != 'dsc'
              AND override.package = v_package AND suite.id = v_data.suite;

    WHEN 'src_associations' THEN
      SELECT source, version
        INTO STRICT v_package, v_version
        FROM source WHERE source.id = v_data.source;
      v_architecture := 'source';

      SELECT component.name, priority.priority, section.section
        INTO v_component, v_priority, v_section
        FROM override
             JOIN override_type ON (override.type = override_type.id)
             JOIN priority ON (priority.id = override.priority)
             JOIN section ON (section.id = override.section)
             JOIN component ON (override.component = component.id)
             JOIN suite ON (suite.id = override.suite)
        WHERE override_type.type = 'dsc'
              AND override.package = v_package AND suite.id = v_data.suite;

    ELSE RAISE EXCEPTION 'trigger called for invalid table (%)', TG_TABLE_NAME;
  END CASE;

  INSERT INTO audit.package_changes
    (package, version, architecture, suite, event, priority, component, section)
    VALUES (v_package, v_version, v_architecture, v_suite, v_event, v_priority, v_component, v_section);

  RETURN NEW;
END;
$$;


ALTER FUNCTION public.trigger_binsrc_assoc_update() OWNER TO dak;

--
-- Name: trigger_override_update(); Type: FUNCTION; Schema: public; Owner: dak
--

CREATE FUNCTION trigger_override_update() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO public, pg_temp
    AS $$
DECLARE
  v_src_override_id override_type.id%TYPE;

  v_priority audit.package_changes.priority%TYPE := NULL;
  v_component audit.package_changes.component%TYPE := NULL;
  v_section audit.package_changes.section%TYPE := NULL;
BEGIN

  IF TG_TABLE_NAME != 'override' THEN
    RAISE EXCEPTION 'trigger called for invalid table (%)', TG_TABLE_NAME;
  END IF;
  IF TG_OP != 'UPDATE' THEN
    RAISE EXCEPTION 'trigger called for invalid event (%)', TG_OP;
  END IF;

  IF OLD.package != NEW.package OR OLD.type != NEW.type OR OLD.suite != NEW.suite THEN
    RETURN NEW;
  END IF;

  IF OLD.priority != NEW.priority THEN
    SELECT priority INTO STRICT v_priority FROM priority WHERE id = NEW.priority;
  END IF;

  IF OLD.component != NEW.component THEN
    SELECT name INTO STRICT v_component FROM component WHERE id = NEW.component;
  END IF;

  IF OLD.section != NEW.section THEN
    SELECT section INTO STRICT v_section FROM section WHERE id = NEW.section;
  END IF;

  -- Find out if we're doing src or binary overrides
  SELECT id INTO STRICT v_src_override_id FROM override_type WHERE type = 'dsc';
  IF OLD.type = v_src_override_id THEN
    -- Doing a src_association link
    INSERT INTO audit.package_changes
      (package, version, architecture, suite, event, priority, component, section)
      SELECT NEW.package, source.version, 'source', suite.suite_name, 'U', v_priority, v_component, v_section
        FROM source
          JOIN src_associations ON (source.id = src_associations.source)
          JOIN suite ON (suite.id = src_associations.suite)
        WHERE source.source = NEW.package AND src_associations.suite = NEW.suite;
  ELSE
    -- Doing a bin_association link
    INSERT INTO audit.package_changes
      (package, version, architecture, suite, event, priority, component, section)
      SELECT NEW.package, binaries.version, architecture.arch_string, suite.suite_name, 'U', v_priority, v_component, v_section
        FROM binaries
          JOIN bin_associations ON (binaries.id = bin_associations.bin)
          JOIN architecture ON (architecture.id = binaries.architecture)
          JOIN suite ON (suite.id = bin_associations.suite)
        WHERE binaries.package = NEW.package AND bin_associations.suite = NEW.suite;
  END IF;

  RETURN NEW;
END;
$$;


ALTER FUNCTION public.trigger_override_update() OWNER TO dak;

SET search_path = audit, pg_catalog;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: package_changes; Type: TABLE; Schema: audit; Owner: dak; Tablespace: 
--

CREATE TABLE package_changes (
    changedate timestamp without time zone DEFAULT now() NOT NULL,
    package text NOT NULL,
    version public.debversion NOT NULL,
    architecture text NOT NULL,
    suite text NOT NULL,
    event text NOT NULL,
    priority text,
    component text,
    section text
);


ALTER TABLE audit.package_changes OWNER TO dak;

SET search_path = public, pg_catalog;

--
-- Name: bin_associations_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE bin_associations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.bin_associations_id_seq OWNER TO dak;

--
-- Name: bin_associations; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE bin_associations (
    id integer DEFAULT nextval('bin_associations_id_seq'::regclass) NOT NULL,
    suite integer NOT NULL,
    bin integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.bin_associations OWNER TO dak;

--
-- Name: binaries_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE binaries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.binaries_id_seq OWNER TO dak;

--
-- Name: binaries; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE binaries (
    id integer DEFAULT nextval('binaries_id_seq'::regclass) NOT NULL,
    package text NOT NULL,
    version debversion NOT NULL,
    maintainer integer NOT NULL,
    source integer NOT NULL,
    architecture integer NOT NULL,
    file integer NOT NULL,
    type text NOT NULL,
    sig_fpr integer,
    install_date timestamp with time zone DEFAULT now(),
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    stanza text
);


ALTER TABLE public.binaries OWNER TO dak;

--
-- Name: bin_associations_binaries; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW bin_associations_binaries AS
    SELECT bin_associations.id, bin_associations.bin, binaries.package, binaries.version, bin_associations.suite, binaries.architecture, binaries.source FROM (bin_associations JOIN binaries ON ((bin_associations.bin = binaries.id)));


ALTER TABLE public.bin_associations_binaries OWNER TO dak;

--
-- Name: source_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE source_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.source_id_seq OWNER TO dak;

--
-- Name: source; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE source (
    id integer DEFAULT nextval('source_id_seq'::regclass) NOT NULL,
    source text NOT NULL,
    version debversion NOT NULL,
    maintainer integer NOT NULL,
    file integer NOT NULL,
    sig_fpr integer,
    install_date timestamp with time zone NOT NULL,
    changedby integer NOT NULL,
    dm_upload_allowed boolean DEFAULT false NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    stanza text
);


ALTER TABLE public.source OWNER TO dak;

--
-- Name: src_associations_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE src_associations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.src_associations_id_seq OWNER TO dak;

--
-- Name: src_associations; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE src_associations (
    id integer DEFAULT nextval('src_associations_id_seq'::regclass) NOT NULL,
    suite integer NOT NULL,
    source integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.src_associations OWNER TO dak;

--
-- Name: src_associations_bin; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW src_associations_bin AS
    SELECT src_associations.id, src_associations.source, src_associations.suite, binaries.id AS bin, binaries.architecture FROM ((src_associations JOIN source ON ((src_associations.source = source.id))) JOIN binaries ON ((source.id = binaries.source)));


ALTER TABLE public.src_associations_bin OWNER TO dak;

--
-- Name: almost_obsolete_all_associations; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW almost_obsolete_all_associations AS
    SELECT bin_associations_binaries.id, bin_associations_binaries.bin, bin_associations_binaries.package, bin_associations_binaries.version, bin_associations_binaries.suite FROM (bin_associations_binaries LEFT JOIN src_associations_bin USING (bin, suite, architecture)) WHERE ((src_associations_bin.source IS NULL) AND (bin_associations_binaries.architecture = 2));


ALTER TABLE public.almost_obsolete_all_associations OWNER TO dak;

--
-- Name: any_associations_source; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW any_associations_source AS
    SELECT bin_associations.id, bin_associations.suite, binaries.id AS bin, binaries.package, binaries.version AS binver, binaries.architecture, source.id AS src, source.source, source.version AS srcver FROM ((bin_associations JOIN binaries ON (((bin_associations.bin = binaries.id) AND (binaries.architecture <> 2)))) JOIN source ON ((binaries.source = source.id)));


ALTER TABLE public.any_associations_source OWNER TO dak;

--
-- Name: src_associations_src; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW src_associations_src AS
    SELECT src_associations.id, src_associations.suite, source.id AS src, source.source, source.version FROM (src_associations JOIN source ON ((src_associations.source = source.id)));


ALTER TABLE public.src_associations_src OWNER TO dak;

--
-- Name: almost_obsolete_src_associations; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW almost_obsolete_src_associations AS
    SELECT src_associations_src.id, src_associations_src.src, src_associations_src.source, src_associations_src.version, src_associations_src.suite FROM (src_associations_src LEFT JOIN any_associations_source USING (src, suite)) WHERE (any_associations_source.bin IS NULL);


ALTER TABLE public.almost_obsolete_src_associations OWNER TO dak;

--
-- Name: architecture_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE architecture_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.architecture_id_seq OWNER TO dak;

--
-- Name: architecture; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE architecture (
    id integer DEFAULT nextval('architecture_id_seq'::regclass) NOT NULL,
    arch_string text NOT NULL,
    description text,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.architecture OWNER TO dak;

--
-- Name: archive_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE archive_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.archive_id_seq OWNER TO dak;

--
-- Name: archive; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE archive (
    id integer DEFAULT nextval('archive_id_seq'::regclass) NOT NULL,
    name text NOT NULL,
    origin_server text,
    description text,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    primary_mirror text
);


ALTER TABLE public.archive OWNER TO dak;

--
-- Name: bin_contents; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE bin_contents (
    file text NOT NULL,
    binary_id integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.bin_contents OWNER TO dak;

--
-- Name: binaries_metadata; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE binaries_metadata (
    bin_id integer NOT NULL,
    key_id integer NOT NULL,
    value text NOT NULL
);


ALTER TABLE public.binaries_metadata OWNER TO dak;

--
-- Name: suite_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE suite_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.suite_id_seq OWNER TO dak;

--
-- Name: suite; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE suite (
    id integer DEFAULT nextval('suite_id_seq'::regclass) NOT NULL,
    suite_name text NOT NULL,
    version text,
    origin text,
    label text,
    description text,
    untouchable boolean DEFAULT false NOT NULL,
    codename text,
    overridecodename text,
    validtime integer DEFAULT 604800 NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    notautomatic boolean DEFAULT false NOT NULL,
    copychanges text,
    overridesuite text,
    policy_queue_id integer,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    changelog text,
    butautomaticupgrades boolean DEFAULT false NOT NULL,
    signingkeys text[],
    announce text[],
    CONSTRAINT bau_needs_na_set CHECK (((NOT butautomaticupgrades) OR notautomatic))
);


ALTER TABLE public.suite OWNER TO dak;

--
-- Name: binaries_suite_arch; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW binaries_suite_arch AS
    SELECT bin_associations.id, binaries.id AS bin, binaries.package, binaries.version, binaries.source, bin_associations.suite, suite.suite_name, binaries.architecture, architecture.arch_string FROM (((binaries JOIN bin_associations ON ((binaries.id = bin_associations.bin))) JOIN suite ON ((suite.id = bin_associations.suite))) JOIN architecture ON ((binaries.architecture = architecture.id)));


ALTER TABLE public.binaries_suite_arch OWNER TO dak;

--
-- Name: binary_acl; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE binary_acl (
    id integer NOT NULL,
    access_level text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.binary_acl OWNER TO dak;

--
-- Name: binary_acl_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE binary_acl_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.binary_acl_id_seq OWNER TO dak;

--
-- Name: binary_acl_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE binary_acl_id_seq OWNED BY binary_acl.id;


--
-- Name: binary_acl_map; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE binary_acl_map (
    id integer NOT NULL,
    fingerprint_id integer NOT NULL,
    architecture_id integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.binary_acl_map OWNER TO dak;

--
-- Name: binary_acl_map_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE binary_acl_map_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.binary_acl_map_id_seq OWNER TO dak;

--
-- Name: binary_acl_map_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE binary_acl_map_id_seq OWNED BY binary_acl_map.id;


--
-- Name: files_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.files_id_seq OWNER TO dak;

--
-- Name: files; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE files (
    id integer DEFAULT nextval('files_id_seq'::regclass) NOT NULL,
    filename text NOT NULL,
    size bigint NOT NULL,
    md5sum text NOT NULL,
    location integer NOT NULL,
    last_used timestamp with time zone,
    sha1sum text,
    sha256sum text,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.files OWNER TO dak;

--
-- Name: location_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE location_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.location_id_seq OWNER TO dak;

--
-- Name: location; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE location (
    id integer DEFAULT nextval('location_id_seq'::regclass) NOT NULL,
    path text NOT NULL,
    component integer,
    archive integer,
    type text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.location OWNER TO dak;

--
-- Name: binfiles_suite_component_arch; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW binfiles_suite_component_arch AS
    SELECT files.filename, binaries.type, location.path, location.component, bin_associations.suite, binaries.architecture FROM (((binaries JOIN bin_associations ON ((binaries.id = bin_associations.bin))) JOIN files ON ((binaries.file = files.id))) JOIN location ON ((files.location = location.id)));


ALTER TABLE public.binfiles_suite_component_arch OWNER TO dak;

--
-- Name: build_queue; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE build_queue (
    id integer NOT NULL,
    queue_name text NOT NULL,
    path text NOT NULL,
    copy_files boolean DEFAULT false NOT NULL,
    generate_metadata boolean DEFAULT false NOT NULL,
    origin text,
    label text,
    releasedescription text,
    signingkey text,
    stay_of_execution integer DEFAULT 86400 NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    notautomatic boolean DEFAULT false NOT NULL,
    CONSTRAINT build_queue_meta_sanity_check CHECK (((generate_metadata IS FALSE) OR (((origin IS NOT NULL) AND (label IS NOT NULL)) AND (releasedescription IS NOT NULL)))),
    CONSTRAINT build_queue_stay_of_execution_check CHECK ((stay_of_execution >= 0))
);


ALTER TABLE public.build_queue OWNER TO dak;

--
-- Name: build_queue_files; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE build_queue_files (
    id integer NOT NULL,
    build_queue_id integer NOT NULL,
    insertdate timestamp without time zone DEFAULT now() NOT NULL,
    lastused timestamp without time zone,
    filename text NOT NULL,
    fileid integer,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.build_queue_files OWNER TO dak;

--
-- Name: build_queue_files_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE build_queue_files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.build_queue_files_id_seq OWNER TO dak;

--
-- Name: build_queue_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE build_queue_files_id_seq OWNED BY build_queue_files.id;


--
-- Name: build_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE build_queue_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.build_queue_id_seq OWNER TO dak;

--
-- Name: build_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE build_queue_id_seq OWNED BY build_queue.id;


--
-- Name: build_queue_policy_files; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE build_queue_policy_files (
    build_queue_id integer NOT NULL,
    file_id integer NOT NULL,
    filename text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    lastused timestamp without time zone
);


ALTER TABLE public.build_queue_policy_files OWNER TO dak;

--
-- Name: changelogs_text; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE changelogs_text (
    id integer NOT NULL,
    changelog text
);


ALTER TABLE public.changelogs_text OWNER TO dak;

--
-- Name: changes; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE changes (
    id integer NOT NULL,
    changesname text NOT NULL,
    seen timestamp with time zone DEFAULT now() NOT NULL,
    source text NOT NULL,
    binaries text NOT NULL,
    architecture text NOT NULL,
    version text NOT NULL,
    distribution text NOT NULL,
    urgency text NOT NULL,
    maintainer text NOT NULL,
    fingerprint text NOT NULL,
    changedby text NOT NULL,
    date text NOT NULL,
    in_queue integer,
    approved_for integer,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    changelog_id integer
);


ALTER TABLE public.changes OWNER TO dak;

--
-- Name: changelogs; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW changelogs AS
    SELECT cl.id, c.source, (c.version)::debversion AS version, c.architecture, cl.changelog, c.distribution FROM (changes c JOIN changelogs_text cl ON ((cl.id = c.changelog_id)));


ALTER TABLE public.changelogs OWNER TO dak;

--
-- Name: changelogs_text_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE changelogs_text_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.changelogs_text_id_seq OWNER TO dak;

--
-- Name: changelogs_text_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE changelogs_text_id_seq OWNED BY changelogs_text.id;


--
-- Name: changes_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE changes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.changes_id_seq OWNER TO dak;

--
-- Name: changes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE changes_id_seq OWNED BY changes.id;


--
-- Name: changes_pending_binaries; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE changes_pending_binaries (
    id integer NOT NULL,
    change_id integer NOT NULL,
    package text NOT NULL,
    version debversion NOT NULL,
    architecture_id integer NOT NULL,
    source_id integer,
    pending_source_id integer,
    pending_file_id integer,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT changes_pending_binaries_check CHECK (((source_id IS NOT NULL) OR (pending_source_id IS NOT NULL)))
);


ALTER TABLE public.changes_pending_binaries OWNER TO dak;

--
-- Name: changes_pending_binaries_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE changes_pending_binaries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.changes_pending_binaries_id_seq OWNER TO dak;

--
-- Name: changes_pending_binaries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE changes_pending_binaries_id_seq OWNED BY changes_pending_binaries.id;


--
-- Name: changes_pending_files; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE changes_pending_files (
    id integer NOT NULL,
    filename text NOT NULL,
    size bigint NOT NULL,
    md5sum text NOT NULL,
    sha1sum text NOT NULL,
    sha256sum text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    processed boolean DEFAULT false
);


ALTER TABLE public.changes_pending_files OWNER TO dak;

--
-- Name: changes_pending_files_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE changes_pending_files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.changes_pending_files_id_seq OWNER TO dak;

--
-- Name: changes_pending_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE changes_pending_files_id_seq OWNED BY changes_pending_files.id;


--
-- Name: changes_pending_files_map; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE changes_pending_files_map (
    file_id integer NOT NULL,
    change_id integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.changes_pending_files_map OWNER TO dak;

--
-- Name: changes_pending_source; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE changes_pending_source (
    id integer NOT NULL,
    change_id integer NOT NULL,
    source text NOT NULL,
    version debversion NOT NULL,
    maintainer_id integer NOT NULL,
    changedby_id integer NOT NULL,
    sig_fpr integer NOT NULL,
    dm_upload_allowed boolean DEFAULT false NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.changes_pending_source OWNER TO dak;

--
-- Name: changes_pending_source_files; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE changes_pending_source_files (
    pending_source_id integer NOT NULL,
    pending_file_id integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.changes_pending_source_files OWNER TO dak;

--
-- Name: changes_pending_source_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE changes_pending_source_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.changes_pending_source_id_seq OWNER TO dak;

--
-- Name: changes_pending_source_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE changes_pending_source_id_seq OWNED BY changes_pending_source.id;


--
-- Name: changes_pool_files; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE changes_pool_files (
    changeid integer NOT NULL,
    fileid integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.changes_pool_files OWNER TO dak;

--
-- Name: component_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE component_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.component_id_seq OWNER TO dak;

--
-- Name: component; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE component (
    id integer DEFAULT nextval('component_id_seq'::regclass) NOT NULL,
    name text NOT NULL,
    description text,
    meets_dfsg boolean,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.component OWNER TO dak;

--
-- Name: config; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE config (
    id integer NOT NULL,
    name text NOT NULL,
    value text,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.config OWNER TO dak;

--
-- Name: config_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE config_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.config_id_seq OWNER TO dak;

--
-- Name: config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE config_id_seq OWNED BY config.id;


--
-- Name: dsc_files_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE dsc_files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.dsc_files_id_seq OWNER TO dak;

--
-- Name: dsc_files; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE dsc_files (
    id integer DEFAULT nextval('dsc_files_id_seq'::regclass) NOT NULL,
    source integer NOT NULL,
    file integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.dsc_files OWNER TO dak;

--
-- Name: external_overrides; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE external_overrides (
    package text NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    suite integer NOT NULL,
    component integer NOT NULL
);


ALTER TABLE public.external_overrides OWNER TO dak;

--
-- Name: extra_src_references; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE extra_src_references (
    bin_id integer NOT NULL,
    src_id integer NOT NULL
);


ALTER TABLE public.extra_src_references OWNER TO dak;

--
-- Name: file_arch_suite; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW file_arch_suite AS
    SELECT f.id AS file, f.size, b.architecture, s.id AS suite FROM files f, binaries b, bin_associations ba, suite s WHERE (((f.id = b.file) AND (b.id = ba.bin)) AND (ba.suite = s.id));


ALTER TABLE public.file_arch_suite OWNER TO dak;

--
-- Name: fingerprint_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE fingerprint_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.fingerprint_id_seq OWNER TO dak;

--
-- Name: fingerprint; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE fingerprint (
    id integer DEFAULT nextval('fingerprint_id_seq'::regclass) NOT NULL,
    fingerprint text NOT NULL,
    uid integer,
    keyring integer,
    source_acl_id integer,
    binary_acl_id integer,
    binary_reject boolean DEFAULT true NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.fingerprint OWNER TO dak;

--
-- Name: keyring_acl_map; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE keyring_acl_map (
    id integer NOT NULL,
    keyring_id integer NOT NULL,
    architecture_id integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.keyring_acl_map OWNER TO dak;

--
-- Name: keyring_acl_map_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE keyring_acl_map_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.keyring_acl_map_id_seq OWNER TO dak;

--
-- Name: keyring_acl_map_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE keyring_acl_map_id_seq OWNED BY keyring_acl_map.id;


--
-- Name: keyrings; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE keyrings (
    id integer NOT NULL,
    name text NOT NULL,
    default_source_acl_id integer,
    default_binary_acl_id integer,
    default_binary_reject boolean DEFAULT true NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    active boolean DEFAULT true
);


ALTER TABLE public.keyrings OWNER TO dak;

--
-- Name: keyrings_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE keyrings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.keyrings_id_seq OWNER TO dak;

--
-- Name: keyrings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE keyrings_id_seq OWNED BY keyrings.id;


--
-- Name: maintainer_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE maintainer_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.maintainer_id_seq OWNER TO dak;

--
-- Name: maintainer; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE maintainer (
    id integer DEFAULT nextval('maintainer_id_seq'::regclass) NOT NULL,
    name text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.maintainer OWNER TO dak;

--
-- Name: metadata_keys; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE metadata_keys (
    key_id integer NOT NULL,
    key text NOT NULL,
    ordering integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.metadata_keys OWNER TO dak;

--
-- Name: metadata_keys_key_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE metadata_keys_key_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.metadata_keys_key_id_seq OWNER TO dak;

--
-- Name: metadata_keys_key_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE metadata_keys_key_id_seq OWNED BY metadata_keys.key_id;


--
-- Name: new_comments; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE new_comments (
    id integer NOT NULL,
    package text NOT NULL,
    version text NOT NULL,
    comment text NOT NULL,
    author text NOT NULL,
    notedate timestamp with time zone DEFAULT now() NOT NULL,
    trainee boolean DEFAULT false NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.new_comments OWNER TO dak;

--
-- Name: new_comments_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE new_comments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.new_comments_id_seq OWNER TO dak;

--
-- Name: new_comments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE new_comments_id_seq OWNED BY new_comments.id;


--
-- Name: newest_all_associations; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW newest_all_associations AS
    SELECT binaries_suite_arch.package, max(binaries_suite_arch.version) AS version, binaries_suite_arch.suite, binaries_suite_arch.architecture FROM binaries_suite_arch WHERE (binaries_suite_arch.architecture = 2) GROUP BY binaries_suite_arch.package, binaries_suite_arch.suite, binaries_suite_arch.architecture;


ALTER TABLE public.newest_all_associations OWNER TO dak;

--
-- Name: newest_any_associations; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW newest_any_associations AS
    SELECT binaries_suite_arch.package, max(binaries_suite_arch.version) AS version, binaries_suite_arch.suite, binaries_suite_arch.architecture FROM binaries_suite_arch WHERE (binaries_suite_arch.architecture > 2) GROUP BY binaries_suite_arch.package, binaries_suite_arch.suite, binaries_suite_arch.architecture;


ALTER TABLE public.newest_any_associations OWNER TO dak;

--
-- Name: source_suite; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW source_suite AS
    SELECT src_associations.id, source.id AS src, source.source, source.version, src_associations.suite, suite.suite_name, source.install_date FROM ((source JOIN src_associations ON ((source.id = src_associations.source))) JOIN suite ON ((suite.id = src_associations.suite)));


ALTER TABLE public.source_suite OWNER TO dak;

--
-- Name: newest_source; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW newest_source AS
    SELECT source_suite.source, max(source_suite.version) AS version, source_suite.suite FROM source_suite GROUP BY source_suite.source, source_suite.suite;


ALTER TABLE public.newest_source OWNER TO dak;

--
-- Name: newest_src_association; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW newest_src_association AS
    SELECT source_suite.id, source_suite.src, source_suite.source, source_suite.version, source_suite.suite FROM (source_suite JOIN newest_source USING (source, version, suite));


ALTER TABLE public.newest_src_association OWNER TO dak;

--
-- Name: obsolete_all_associations; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW obsolete_all_associations AS
    SELECT almost.id, almost.bin, almost.package, almost.version, almost.suite FROM (almost_obsolete_all_associations almost JOIN newest_all_associations newest ON ((((almost.package = newest.package) AND (almost.version < newest.version)) AND (almost.suite = newest.suite))));


ALTER TABLE public.obsolete_all_associations OWNER TO dak;

--
-- Name: obsolete_any_associations; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW obsolete_any_associations AS
    SELECT binaries_suite_arch.id, binaries_suite_arch.architecture, binaries_suite_arch.version, binaries_suite_arch.package, binaries_suite_arch.suite FROM (binaries_suite_arch JOIN newest_any_associations ON (((((binaries_suite_arch.architecture = newest_any_associations.architecture) AND (binaries_suite_arch.package = newest_any_associations.package)) AND (binaries_suite_arch.suite = newest_any_associations.suite)) AND (binaries_suite_arch.version <> newest_any_associations.version))));


ALTER TABLE public.obsolete_any_associations OWNER TO dak;

--
-- Name: obsolete_any_by_all_associations; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW obsolete_any_by_all_associations AS
    SELECT binaries_suite_arch.id, binaries_suite_arch.package, binaries_suite_arch.version, binaries_suite_arch.suite, binaries_suite_arch.architecture FROM (binaries_suite_arch JOIN newest_all_associations ON (((((binaries_suite_arch.package = newest_all_associations.package) AND (binaries_suite_arch.version < newest_all_associations.version)) AND (binaries_suite_arch.suite = newest_all_associations.suite)) AND (binaries_suite_arch.architecture > 2))));


ALTER TABLE public.obsolete_any_by_all_associations OWNER TO dak;

--
-- Name: obsolete_src_associations; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW obsolete_src_associations AS
    SELECT almost.id, almost.src, almost.source, almost.version, almost.suite FROM (almost_obsolete_src_associations almost JOIN newest_src_association newest ON ((((almost.source = newest.source) AND (almost.version < newest.version)) AND (almost.suite = newest.suite))));


ALTER TABLE public.obsolete_src_associations OWNER TO dak;

--
-- Name: override; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE override (
    package text NOT NULL,
    suite integer NOT NULL,
    component integer NOT NULL,
    priority integer,
    section integer NOT NULL,
    type integer NOT NULL,
    maintainer text,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.override OWNER TO dak;

--
-- Name: override_type_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE override_type_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.override_type_id_seq OWNER TO dak;

--
-- Name: override_type; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE override_type (
    id integer DEFAULT nextval('override_type_id_seq'::regclass) NOT NULL,
    type text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.override_type OWNER TO dak;

--
-- Name: policy_queue; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE policy_queue (
    id integer NOT NULL,
    queue_name text NOT NULL,
    path text NOT NULL,
    perms character(4) DEFAULT '0660'::bpchar NOT NULL,
    change_perms character(4) DEFAULT '0660'::bpchar NOT NULL,
    generate_metadata boolean DEFAULT false NOT NULL,
    origin text,
    label text,
    releasedescription text,
    signingkey text,
    stay_of_execution integer DEFAULT 86400 NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    send_to_build_queues boolean DEFAULT false NOT NULL,
    CONSTRAINT policy_queue_change_perms_check CHECK ((change_perms ~ similar_escape('[0-7][0-7][0-7][0-7]'::text, NULL::text))),
    CONSTRAINT policy_queue_meta_sanity_check CHECK (((generate_metadata IS FALSE) OR (((origin IS NOT NULL) AND (label IS NOT NULL)) AND (releasedescription IS NOT NULL)))),
    CONSTRAINT policy_queue_perms_check CHECK ((perms ~ similar_escape('[0-7][0-7][0-7][0-7]'::text, NULL::text))),
    CONSTRAINT policy_queue_stay_of_execution_check CHECK ((stay_of_execution >= 0))
);


ALTER TABLE public.policy_queue OWNER TO dak;

--
-- Name: policy_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE policy_queue_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.policy_queue_id_seq OWNER TO dak;

--
-- Name: policy_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE policy_queue_id_seq OWNED BY policy_queue.id;


--
-- Name: priority_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE priority_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.priority_id_seq OWNER TO dak;

--
-- Name: priority; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE priority (
    id integer DEFAULT nextval('priority_id_seq'::regclass) NOT NULL,
    priority text NOT NULL,
    level integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.priority OWNER TO dak;

--
-- Name: section_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE section_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.section_id_seq OWNER TO dak;

--
-- Name: section; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE section (
    id integer DEFAULT nextval('section_id_seq'::regclass) NOT NULL,
    section text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.section OWNER TO dak;

--
-- Name: source_acl; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE source_acl (
    id integer NOT NULL,
    access_level text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.source_acl OWNER TO dak;

--
-- Name: source_acl_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE source_acl_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.source_acl_id_seq OWNER TO dak;

--
-- Name: source_acl_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE source_acl_id_seq OWNED BY source_acl.id;


--
-- Name: source_metadata; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE source_metadata (
    src_id integer NOT NULL,
    key_id integer NOT NULL,
    value text NOT NULL
);


ALTER TABLE public.source_metadata OWNER TO dak;

--
-- Name: src_contents; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE src_contents (
    file text NOT NULL,
    source_id integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.src_contents OWNER TO dak;

--
-- Name: src_format; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE src_format (
    id integer NOT NULL,
    format_name text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.src_format OWNER TO dak;

--
-- Name: src_format_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE src_format_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.src_format_id_seq OWNER TO dak;

--
-- Name: src_format_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE src_format_id_seq OWNED BY src_format.id;


--
-- Name: src_uploaders; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE src_uploaders (
    id integer NOT NULL,
    source integer NOT NULL,
    maintainer integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.src_uploaders OWNER TO dak;

--
-- Name: src_uploaders_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE src_uploaders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.src_uploaders_id_seq OWNER TO dak;

--
-- Name: src_uploaders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE src_uploaders_id_seq OWNED BY src_uploaders.id;


--
-- Name: suite_architectures; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE suite_architectures (
    suite integer NOT NULL,
    architecture integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.suite_architectures OWNER TO dak;

--
-- Name: suite_arch_by_name; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW suite_arch_by_name AS
    SELECT suite.suite_name AS suite, a.arch_string AS arch FROM ((suite_architectures sa JOIN architecture a ON ((sa.architecture = a.id))) JOIN suite ON ((sa.suite = suite.id))) WHERE (a.arch_string <> ALL (ARRAY['all'::text, 'source'::text]));


ALTER TABLE public.suite_arch_by_name OWNER TO dak;

--
-- Name: suite_build_queue_copy; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE suite_build_queue_copy (
    suite integer NOT NULL,
    build_queue_id integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.suite_build_queue_copy OWNER TO dak;

--
-- Name: suite_src_formats; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE suite_src_formats (
    suite integer NOT NULL,
    src_format integer NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.suite_src_formats OWNER TO dak;

--
-- Name: uid_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE uid_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.uid_id_seq OWNER TO dak;

--
-- Name: uid; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE uid (
    id integer DEFAULT nextval('uid_id_seq'::regclass) NOT NULL,
    uid text NOT NULL,
    name text,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.uid OWNER TO dak;

--
-- Name: upload_blocks; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE upload_blocks (
    id integer NOT NULL,
    source text NOT NULL,
    version debversion,
    fingerprint_id integer,
    uid_id integer,
    reason text NOT NULL,
    created timestamp with time zone DEFAULT now() NOT NULL,
    modified timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT upload_blocks_check CHECK (((fingerprint_id IS NOT NULL) OR (uid_id IS NOT NULL)))
);


ALTER TABLE public.upload_blocks OWNER TO dak;

--
-- Name: upload_blocks_id_seq; Type: SEQUENCE; Schema: public; Owner: dak
--

CREATE SEQUENCE upload_blocks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.upload_blocks_id_seq OWNER TO dak;

--
-- Name: upload_blocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dak
--

ALTER SEQUENCE upload_blocks_id_seq OWNED BY upload_blocks.id;


--
-- Name: version_check; Type: TABLE; Schema: public; Owner: dak; Tablespace: 
--

CREATE TABLE version_check (
    suite integer NOT NULL,
    "check" text NOT NULL,
    reference integer NOT NULL,
    CONSTRAINT version_check_check_check CHECK (("check" = ANY (ARRAY['Enhances'::text, 'MustBeNewerThan'::text, 'MustBeOlderThan'::text])))
);


ALTER TABLE public.version_check OWNER TO dak;

--
-- Name: version_checks; Type: VIEW; Schema: public; Owner: dak
--

CREATE VIEW version_checks AS
    SELECT s.suite_name AS source_suite, v."check" AS condition, t.suite_name AS target_suite FROM ((suite s JOIN version_check v ON ((s.id = v.suite))) JOIN suite t ON ((v.reference = t.id))) ORDER BY s.suite_name, v."check", t.suite_name;


ALTER TABLE public.version_checks OWNER TO dak;

--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE binary_acl ALTER COLUMN id SET DEFAULT nextval('binary_acl_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE binary_acl_map ALTER COLUMN id SET DEFAULT nextval('binary_acl_map_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE build_queue ALTER COLUMN id SET DEFAULT nextval('build_queue_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE build_queue_files ALTER COLUMN id SET DEFAULT nextval('build_queue_files_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE changelogs_text ALTER COLUMN id SET DEFAULT nextval('changelogs_text_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE changes ALTER COLUMN id SET DEFAULT nextval('changes_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE changes_pending_binaries ALTER COLUMN id SET DEFAULT nextval('changes_pending_binaries_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE changes_pending_files ALTER COLUMN id SET DEFAULT nextval('changes_pending_files_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE changes_pending_source ALTER COLUMN id SET DEFAULT nextval('changes_pending_source_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE config ALTER COLUMN id SET DEFAULT nextval('config_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE keyring_acl_map ALTER COLUMN id SET DEFAULT nextval('keyring_acl_map_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE keyrings ALTER COLUMN id SET DEFAULT nextval('keyrings_id_seq'::regclass);


--
-- Name: key_id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE metadata_keys ALTER COLUMN key_id SET DEFAULT nextval('metadata_keys_key_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE new_comments ALTER COLUMN id SET DEFAULT nextval('new_comments_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE policy_queue ALTER COLUMN id SET DEFAULT nextval('policy_queue_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE source_acl ALTER COLUMN id SET DEFAULT nextval('source_acl_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE src_format ALTER COLUMN id SET DEFAULT nextval('src_format_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE src_uploaders ALTER COLUMN id SET DEFAULT nextval('src_uploaders_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: dak
--

ALTER TABLE upload_blocks ALTER COLUMN id SET DEFAULT nextval('upload_blocks_id_seq'::regclass);


--
-- Name: architecture_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY architecture
    ADD CONSTRAINT architecture_pkey PRIMARY KEY (id);


--
-- Name: archive_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY archive
    ADD CONSTRAINT archive_pkey PRIMARY KEY (id);


--
-- Name: bin_associations_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY bin_associations
    ADD CONSTRAINT bin_associations_pkey PRIMARY KEY (id);


--
-- Name: bin_contents_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY bin_contents
    ADD CONSTRAINT bin_contents_pkey PRIMARY KEY (file, binary_id);


--
-- Name: binaries_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY binaries_metadata
    ADD CONSTRAINT binaries_metadata_pkey PRIMARY KEY (bin_id, key_id);


--
-- Name: binaries_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY binaries
    ADD CONSTRAINT binaries_pkey PRIMARY KEY (id);


--
-- Name: binary_acl_access_level_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY binary_acl
    ADD CONSTRAINT binary_acl_access_level_key UNIQUE (access_level);


--
-- Name: binary_acl_map_fingerprint_id_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY binary_acl_map
    ADD CONSTRAINT binary_acl_map_fingerprint_id_key UNIQUE (fingerprint_id, architecture_id);


--
-- Name: binary_acl_map_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY binary_acl_map
    ADD CONSTRAINT binary_acl_map_pkey PRIMARY KEY (id);


--
-- Name: binary_acl_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY binary_acl
    ADD CONSTRAINT binary_acl_pkey PRIMARY KEY (id);


--
-- Name: build_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY build_queue
    ADD CONSTRAINT build_queue_pkey PRIMARY KEY (id);


--
-- Name: build_queue_policy_files_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY build_queue_policy_files
    ADD CONSTRAINT build_queue_policy_files_pkey PRIMARY KEY (build_queue_id, file_id);


--
-- Name: build_queue_queue_name_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY build_queue
    ADD CONSTRAINT build_queue_queue_name_key UNIQUE (queue_name);


--
-- Name: changelogs_text_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changelogs_text
    ADD CONSTRAINT changelogs_text_pkey PRIMARY KEY (id);


--
-- Name: changes_pending_binaries_package_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes_pending_binaries
    ADD CONSTRAINT changes_pending_binaries_package_key UNIQUE (package, version, architecture_id);


--
-- Name: changes_pending_binaries_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes_pending_binaries
    ADD CONSTRAINT changes_pending_binaries_pkey PRIMARY KEY (id);


--
-- Name: changes_pending_files_filename_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes_pending_files
    ADD CONSTRAINT changes_pending_files_filename_key UNIQUE (filename);


--
-- Name: changes_pending_files_map_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes_pending_files_map
    ADD CONSTRAINT changes_pending_files_map_pkey PRIMARY KEY (file_id, change_id);


--
-- Name: changes_pending_files_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes_pending_files
    ADD CONSTRAINT changes_pending_files_pkey PRIMARY KEY (id);


--
-- Name: changes_pending_source_files_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes_pending_source_files
    ADD CONSTRAINT changes_pending_source_files_pkey PRIMARY KEY (pending_source_id, pending_file_id);


--
-- Name: changes_pending_source_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes_pending_source
    ADD CONSTRAINT changes_pending_source_pkey PRIMARY KEY (id);


--
-- Name: changes_pool_files_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes_pool_files
    ADD CONSTRAINT changes_pool_files_pkey PRIMARY KEY (changeid, fileid);


--
-- Name: component_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY component
    ADD CONSTRAINT component_pkey PRIMARY KEY (id);


--
-- Name: config_name_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY config
    ADD CONSTRAINT config_name_key UNIQUE (name);


--
-- Name: config_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY config
    ADD CONSTRAINT config_pkey PRIMARY KEY (id);


--
-- Name: dsc_files_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY dsc_files
    ADD CONSTRAINT dsc_files_pkey PRIMARY KEY (id);


--
-- Name: external_overrides_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY external_overrides
    ADD CONSTRAINT external_overrides_pkey PRIMARY KEY (suite, component, package, key);


--
-- Name: extra_src_references_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY extra_src_references
    ADD CONSTRAINT extra_src_references_pkey PRIMARY KEY (bin_id, src_id);


--
-- Name: files_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY files
    ADD CONSTRAINT files_pkey PRIMARY KEY (id);


--
-- Name: fingerprint_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY fingerprint
    ADD CONSTRAINT fingerprint_pkey PRIMARY KEY (id);


--
-- Name: keyring_acl_map_keyring_id_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY keyring_acl_map
    ADD CONSTRAINT keyring_acl_map_keyring_id_key UNIQUE (keyring_id, architecture_id);


--
-- Name: keyring_acl_map_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY keyring_acl_map
    ADD CONSTRAINT keyring_acl_map_pkey PRIMARY KEY (id);


--
-- Name: keyrings_name_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY keyrings
    ADD CONSTRAINT keyrings_name_key UNIQUE (name);


--
-- Name: keyrings_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY keyrings
    ADD CONSTRAINT keyrings_pkey PRIMARY KEY (id);


--
-- Name: known_changes_changesname_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes
    ADD CONSTRAINT known_changes_changesname_key UNIQUE (changesname);


--
-- Name: known_changes_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY changes
    ADD CONSTRAINT known_changes_pkey PRIMARY KEY (id);


--
-- Name: location_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY location
    ADD CONSTRAINT location_pkey PRIMARY KEY (id);


--
-- Name: maintainer_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY maintainer
    ADD CONSTRAINT maintainer_pkey PRIMARY KEY (id);


--
-- Name: metadata_keys_key_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY metadata_keys
    ADD CONSTRAINT metadata_keys_key_key UNIQUE (key);


--
-- Name: metadata_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY metadata_keys
    ADD CONSTRAINT metadata_keys_pkey PRIMARY KEY (key_id);


--
-- Name: new_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY new_comments
    ADD CONSTRAINT new_comments_pkey PRIMARY KEY (id);


--
-- Name: override_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY override
    ADD CONSTRAINT override_pkey PRIMARY KEY (suite, component, package, type);


--
-- Name: override_type_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY override_type
    ADD CONSTRAINT override_type_pkey PRIMARY KEY (id);


--
-- Name: policy_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY policy_queue
    ADD CONSTRAINT policy_queue_pkey PRIMARY KEY (id);


--
-- Name: policy_queue_queue_name_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY policy_queue
    ADD CONSTRAINT policy_queue_queue_name_key UNIQUE (queue_name);


--
-- Name: priority_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY priority
    ADD CONSTRAINT priority_pkey PRIMARY KEY (id);


--
-- Name: queue_files_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY build_queue_files
    ADD CONSTRAINT queue_files_pkey PRIMARY KEY (id);


--
-- Name: section_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY section
    ADD CONSTRAINT section_pkey PRIMARY KEY (id);


--
-- Name: source_acl_access_level_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY source_acl
    ADD CONSTRAINT source_acl_access_level_key UNIQUE (access_level);


--
-- Name: source_acl_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY source_acl
    ADD CONSTRAINT source_acl_pkey PRIMARY KEY (id);


--
-- Name: source_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY source_metadata
    ADD CONSTRAINT source_metadata_pkey PRIMARY KEY (src_id, key_id);


--
-- Name: source_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY source
    ADD CONSTRAINT source_pkey PRIMARY KEY (id);


--
-- Name: src_associations_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY src_associations
    ADD CONSTRAINT src_associations_pkey PRIMARY KEY (id);


--
-- Name: src_contents_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY src_contents
    ADD CONSTRAINT src_contents_pkey PRIMARY KEY (file, source_id);


--
-- Name: src_format_format_name_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY src_format
    ADD CONSTRAINT src_format_format_name_key UNIQUE (format_name);


--
-- Name: src_format_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY src_format
    ADD CONSTRAINT src_format_pkey PRIMARY KEY (id);


--
-- Name: src_uploaders_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY src_uploaders
    ADD CONSTRAINT src_uploaders_pkey PRIMARY KEY (id);


--
-- Name: src_uploaders_source_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY src_uploaders
    ADD CONSTRAINT src_uploaders_source_key UNIQUE (source, maintainer);


--
-- Name: suite_architectures_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY suite_architectures
    ADD CONSTRAINT suite_architectures_pkey PRIMARY KEY (suite, architecture);


--
-- Name: suite_name_unique; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY suite
    ADD CONSTRAINT suite_name_unique UNIQUE (suite_name);


--
-- Name: suite_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY suite
    ADD CONSTRAINT suite_pkey PRIMARY KEY (id);


--
-- Name: suite_queue_copy_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY suite_build_queue_copy
    ADD CONSTRAINT suite_queue_copy_pkey PRIMARY KEY (suite, build_queue_id);


--
-- Name: suite_src_formats_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY suite_src_formats
    ADD CONSTRAINT suite_src_formats_pkey PRIMARY KEY (suite, src_format);


--
-- Name: suite_src_formats_suite_key; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY suite_src_formats
    ADD CONSTRAINT suite_src_formats_suite_key UNIQUE (suite, src_format);


--
-- Name: uid_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY uid
    ADD CONSTRAINT uid_pkey PRIMARY KEY (id);


--
-- Name: upload_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY upload_blocks
    ADD CONSTRAINT upload_blocks_pkey PRIMARY KEY (id);


--
-- Name: version_check_pkey; Type: CONSTRAINT; Schema: public; Owner: dak; Tablespace: 
--

ALTER TABLE ONLY version_check
    ADD CONSTRAINT version_check_pkey PRIMARY KEY (suite, "check", reference);


--
-- Name: architecture_arch_string_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX architecture_arch_string_key ON architecture USING btree (arch_string);


--
-- Name: archive_name_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX archive_name_key ON archive USING btree (name);


--
-- Name: bin_associations_bin; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX bin_associations_bin ON bin_associations USING btree (bin);


--
-- Name: bin_associations_suite_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX bin_associations_suite_key ON bin_associations USING btree (suite, bin);


--
-- Name: binaries_architecture_idx; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX binaries_architecture_idx ON binaries USING btree (architecture);


--
-- Name: binaries_by_package; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX binaries_by_package ON binaries USING btree (id, package);


--
-- Name: binaries_file_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX binaries_file_key ON binaries USING btree (file);


--
-- Name: binaries_files; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX binaries_files ON binaries USING btree (file);


--
-- Name: binaries_fingerprint; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX binaries_fingerprint ON binaries USING btree (sig_fpr);


--
-- Name: binaries_id; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX binaries_id ON binaries USING btree (id);


--
-- Name: binaries_maintainer; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX binaries_maintainer ON binaries USING btree (maintainer);


--
-- Name: binaries_metadata_depends; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX binaries_metadata_depends ON binaries_metadata USING btree (bin_id) WHERE (key_id = 44);


--
-- Name: binaries_metadata_provides; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX binaries_metadata_provides ON binaries_metadata USING btree (bin_id) WHERE (key_id = 51);


--
-- Name: binaries_package_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX binaries_package_key ON binaries USING btree (package, version, architecture);


--
-- Name: changesapproved_for; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX changesapproved_for ON changes USING btree (approved_for);


--
-- Name: changesdistribution_ind; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX changesdistribution_ind ON changes USING btree (distribution);


--
-- Name: changesin_queue; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX changesin_queue ON changes USING btree (in_queue);


--
-- Name: changesin_queue_approved_for; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX changesin_queue_approved_for ON changes USING btree (in_queue, approved_for);


--
-- Name: changesname_ind; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX changesname_ind ON changes USING btree (changesname);


--
-- Name: changessource_ind; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX changessource_ind ON changes USING btree (source);


--
-- Name: changestimestamp_ind; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX changestimestamp_ind ON changes USING btree (seen);


--
-- Name: changesurgency_ind; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX changesurgency_ind ON changes USING btree (urgency);


--
-- Name: component_name_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX component_name_key ON component USING btree (name);


--
-- Name: dsc_files_file; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX dsc_files_file ON dsc_files USING btree (file);


--
-- Name: dsc_files_source_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX dsc_files_source_key ON dsc_files USING btree (source, file);


--
-- Name: files_filename_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX files_filename_key ON files USING btree (filename, location);


--
-- Name: files_last_used; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX files_last_used ON files USING btree (last_used);


--
-- Name: fingerprint_fingerprint_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX fingerprint_fingerprint_key ON fingerprint USING btree (fingerprint);


--
-- Name: ind_bin_contents_binary; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX ind_bin_contents_binary ON bin_contents USING btree (binary_id);


--
-- Name: jjt; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX jjt ON files USING btree (id);


--
-- Name: jjt2; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX jjt2 ON files USING btree (location);


--
-- Name: jjt3; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX jjt3 ON files USING btree (id, location);


--
-- Name: jjt4; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX jjt4 ON binaries USING btree (source);


--
-- Name: jjt5; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX jjt5 ON binaries USING btree (id, source);


--
-- Name: jjt_override_type_idx; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX jjt_override_type_idx ON override USING btree (type);


--
-- Name: maintainer_name_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX maintainer_name_key ON maintainer USING btree (name);


--
-- Name: override_by_package; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX override_by_package ON override USING btree (package);


--
-- Name: override_suite_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX override_suite_key ON override USING btree (suite, component, package, type);


--
-- Name: override_type_type_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX override_type_type_key ON override_type USING btree (type);


--
-- Name: priority_level_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX priority_level_key ON priority USING btree (level);


--
-- Name: priority_priority_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX priority_priority_key ON priority USING btree (priority);


--
-- Name: section_section_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX section_section_key ON section USING btree (section);


--
-- Name: source_file_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX source_file_key ON source USING btree (file);


--
-- Name: source_fingerprint; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX source_fingerprint ON source USING btree (sig_fpr);


--
-- Name: source_maintainer; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX source_maintainer ON source USING btree (maintainer);


--
-- Name: source_source_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX source_source_key ON source USING btree (source, version);


--
-- Name: src_associations_source; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX src_associations_source ON src_associations USING btree (source);


--
-- Name: src_associations_suite_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX src_associations_suite_key ON src_associations USING btree (suite, source);


--
-- Name: src_contents_source_id_idx; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX src_contents_source_id_idx ON src_contents USING btree (source_id);


--
-- Name: suite_architectures_suite_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX suite_architectures_suite_key ON suite_architectures USING btree (suite, architecture);


--
-- Name: suite_hash; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE INDEX suite_hash ON suite USING hash (suite_name);


--
-- Name: uid_uid_key; Type: INDEX; Schema: public; Owner: dak; Tablespace: 
--

CREATE UNIQUE INDEX uid_uid_key ON uid USING btree (uid);


--
-- Name: modified_architecture; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_architecture BEFORE UPDATE ON architecture FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_archive; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_archive BEFORE UPDATE ON archive FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_bin_associations; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_bin_associations BEFORE UPDATE ON bin_associations FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_bin_contents; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_bin_contents BEFORE UPDATE ON bin_contents FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_binaries; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_binaries BEFORE UPDATE ON binaries FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_binary_acl; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_binary_acl BEFORE UPDATE ON binary_acl FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_binary_acl_map; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_binary_acl_map BEFORE UPDATE ON binary_acl_map FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_build_queue; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_build_queue BEFORE UPDATE ON build_queue FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_build_queue_files; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_build_queue_files BEFORE UPDATE ON build_queue_files FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_changes; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_changes BEFORE UPDATE ON changes FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_changes_pending_binaries; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_changes_pending_binaries BEFORE UPDATE ON changes_pending_binaries FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_changes_pending_files; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_changes_pending_files BEFORE UPDATE ON changes_pending_files FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_changes_pending_files_map; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_changes_pending_files_map BEFORE UPDATE ON changes_pending_files_map FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_changes_pending_source; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_changes_pending_source BEFORE UPDATE ON changes_pending_source FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_changes_pending_source_files; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_changes_pending_source_files BEFORE UPDATE ON changes_pending_source_files FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_changes_pool_files; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_changes_pool_files BEFORE UPDATE ON changes_pool_files FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_component; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_component BEFORE UPDATE ON component FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_config; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_config BEFORE UPDATE ON config FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_dsc_files; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_dsc_files BEFORE UPDATE ON dsc_files FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_files; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_files BEFORE UPDATE ON files FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_fingerprint; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_fingerprint BEFORE UPDATE ON fingerprint FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_keyring_acl_map; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_keyring_acl_map BEFORE UPDATE ON keyring_acl_map FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_keyrings; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_keyrings BEFORE UPDATE ON keyrings FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_location; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_location BEFORE UPDATE ON location FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_maintainer; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_maintainer BEFORE UPDATE ON maintainer FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_new_comments; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_new_comments BEFORE UPDATE ON new_comments FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_override; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_override BEFORE UPDATE ON override FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_override_type; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_override_type BEFORE UPDATE ON override_type FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_policy_queue; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_policy_queue BEFORE UPDATE ON policy_queue FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_priority; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_priority BEFORE UPDATE ON priority FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_section; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_section BEFORE UPDATE ON section FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_source; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_source BEFORE UPDATE ON source FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_source_acl; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_source_acl BEFORE UPDATE ON source_acl FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_src_associations; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_src_associations BEFORE UPDATE ON src_associations FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_src_contents; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_src_contents BEFORE UPDATE ON src_contents FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_src_format; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_src_format BEFORE UPDATE ON src_format FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_src_uploaders; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_src_uploaders BEFORE UPDATE ON src_uploaders FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_suite; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_suite BEFORE UPDATE ON suite FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_suite_architectures; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_suite_architectures BEFORE UPDATE ON suite_architectures FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_suite_build_queue_copy; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_suite_build_queue_copy BEFORE UPDATE ON suite_build_queue_copy FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_suite_src_formats; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_suite_src_formats BEFORE UPDATE ON suite_src_formats FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_uid; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_uid BEFORE UPDATE ON uid FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: modified_upload_blocks; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER modified_upload_blocks BEFORE UPDATE ON upload_blocks FOR EACH ROW EXECUTE PROCEDURE tfunc_set_modified();


--
-- Name: trigger_bin_associations_audit; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER trigger_bin_associations_audit AFTER INSERT OR DELETE ON bin_associations FOR EACH ROW EXECUTE PROCEDURE trigger_binsrc_assoc_update();


--
-- Name: trigger_override_audit; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER trigger_override_audit AFTER UPDATE ON override FOR EACH ROW EXECUTE PROCEDURE trigger_override_update();


--
-- Name: trigger_src_associations_audit; Type: TRIGGER; Schema: public; Owner: dak
--

CREATE TRIGGER trigger_src_associations_audit AFTER INSERT OR DELETE ON src_associations FOR EACH ROW EXECUTE PROCEDURE trigger_binsrc_assoc_update();


--
-- Name: $1; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY fingerprint
    ADD CONSTRAINT "$1" FOREIGN KEY (keyring) REFERENCES keyrings(id);


--
-- Name: bin_associations_bin; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY bin_associations
    ADD CONSTRAINT bin_associations_bin FOREIGN KEY (bin) REFERENCES binaries(id) MATCH FULL;


--
-- Name: bin_associations_suite; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY bin_associations
    ADD CONSTRAINT bin_associations_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;


--
-- Name: bin_contents_bin_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY bin_contents
    ADD CONSTRAINT bin_contents_bin_fkey FOREIGN KEY (binary_id) REFERENCES binaries(id) ON DELETE CASCADE;


--
-- Name: binaries_architecture; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binaries
    ADD CONSTRAINT binaries_architecture FOREIGN KEY (architecture) REFERENCES architecture(id) MATCH FULL;


--
-- Name: binaries_file; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binaries
    ADD CONSTRAINT binaries_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;


--
-- Name: binaries_maintainer; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binaries
    ADD CONSTRAINT binaries_maintainer FOREIGN KEY (maintainer) REFERENCES maintainer(id) MATCH FULL;


--
-- Name: binaries_metadata_bin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binaries_metadata
    ADD CONSTRAINT binaries_metadata_bin_id_fkey FOREIGN KEY (bin_id) REFERENCES binaries(id) ON DELETE CASCADE;


--
-- Name: binaries_metadata_key_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binaries_metadata
    ADD CONSTRAINT binaries_metadata_key_id_fkey FOREIGN KEY (key_id) REFERENCES metadata_keys(key_id);


--
-- Name: binaries_sig_fpr; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binaries
    ADD CONSTRAINT binaries_sig_fpr FOREIGN KEY (sig_fpr) REFERENCES fingerprint(id) MATCH FULL;


--
-- Name: binaries_source; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binaries
    ADD CONSTRAINT binaries_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;


--
-- Name: binary_acl_map_architecture_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binary_acl_map
    ADD CONSTRAINT binary_acl_map_architecture_id_fkey FOREIGN KEY (architecture_id) REFERENCES architecture(id);


--
-- Name: binary_acl_map_fingerprint_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY binary_acl_map
    ADD CONSTRAINT binary_acl_map_fingerprint_id_fkey FOREIGN KEY (fingerprint_id) REFERENCES fingerprint(id);


--
-- Name: build_queue_files_build_queue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY build_queue_files
    ADD CONSTRAINT build_queue_files_build_queue_id_fkey FOREIGN KEY (build_queue_id) REFERENCES build_queue(id) ON DELETE CASCADE;


--
-- Name: build_queue_policy_files_build_queue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY build_queue_policy_files
    ADD CONSTRAINT build_queue_policy_files_build_queue_id_fkey FOREIGN KEY (build_queue_id) REFERENCES build_queue(id) ON DELETE CASCADE;


--
-- Name: build_queue_policy_files_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY build_queue_policy_files
    ADD CONSTRAINT build_queue_policy_files_file_id_fkey FOREIGN KEY (file_id) REFERENCES changes_pending_files(id) ON DELETE CASCADE;


--
-- Name: changes_pending_binaries_architecture_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_binaries
    ADD CONSTRAINT changes_pending_binaries_architecture_id_fkey FOREIGN KEY (architecture_id) REFERENCES architecture(id);


--
-- Name: changes_pending_binaries_change_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_binaries
    ADD CONSTRAINT changes_pending_binaries_change_id_fkey FOREIGN KEY (change_id) REFERENCES changes(id);


--
-- Name: changes_pending_binaries_pending_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_binaries
    ADD CONSTRAINT changes_pending_binaries_pending_file_id_fkey FOREIGN KEY (pending_file_id) REFERENCES changes_pending_files(id);


--
-- Name: changes_pending_binaries_pending_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_binaries
    ADD CONSTRAINT changes_pending_binaries_pending_source_id_fkey FOREIGN KEY (pending_source_id) REFERENCES changes_pending_source(id);


--
-- Name: changes_pending_binaries_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_binaries
    ADD CONSTRAINT changes_pending_binaries_source_id_fkey FOREIGN KEY (source_id) REFERENCES source(id);


--
-- Name: changes_pending_files_map_change_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_files_map
    ADD CONSTRAINT changes_pending_files_map_change_id_fkey FOREIGN KEY (change_id) REFERENCES changes(id);


--
-- Name: changes_pending_files_map_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_files_map
    ADD CONSTRAINT changes_pending_files_map_file_id_fkey FOREIGN KEY (file_id) REFERENCES changes_pending_files(id);


--
-- Name: changes_pending_source_change_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_source
    ADD CONSTRAINT changes_pending_source_change_id_fkey FOREIGN KEY (change_id) REFERENCES changes(id);


--
-- Name: changes_pending_source_changedby_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_source
    ADD CONSTRAINT changes_pending_source_changedby_id_fkey FOREIGN KEY (changedby_id) REFERENCES maintainer(id);


--
-- Name: changes_pending_source_files_pending_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_source_files
    ADD CONSTRAINT changes_pending_source_files_pending_file_id_fkey FOREIGN KEY (pending_file_id) REFERENCES changes_pending_files(id);


--
-- Name: changes_pending_source_files_pending_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_source_files
    ADD CONSTRAINT changes_pending_source_files_pending_source_id_fkey FOREIGN KEY (pending_source_id) REFERENCES changes_pending_source(id);


--
-- Name: changes_pending_source_maintainer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_source
    ADD CONSTRAINT changes_pending_source_maintainer_id_fkey FOREIGN KEY (maintainer_id) REFERENCES maintainer(id);


--
-- Name: changes_pending_source_sig_fpr_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pending_source
    ADD CONSTRAINT changes_pending_source_sig_fpr_fkey FOREIGN KEY (sig_fpr) REFERENCES fingerprint(id);


--
-- Name: changes_pool_files_changeid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pool_files
    ADD CONSTRAINT changes_pool_files_changeid_fkey FOREIGN KEY (changeid) REFERENCES changes(id) ON DELETE CASCADE;


--
-- Name: changes_pool_files_fileid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes_pool_files
    ADD CONSTRAINT changes_pool_files_fileid_fkey FOREIGN KEY (fileid) REFERENCES files(id) ON DELETE RESTRICT;


--
-- Name: dsc_files_file; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY dsc_files
    ADD CONSTRAINT dsc_files_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;


--
-- Name: dsc_files_source; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY dsc_files
    ADD CONSTRAINT dsc_files_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;


--
-- Name: external_overrides_component_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY external_overrides
    ADD CONSTRAINT external_overrides_component_fkey FOREIGN KEY (component) REFERENCES component(id);


--
-- Name: external_overrides_suite_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY external_overrides
    ADD CONSTRAINT external_overrides_suite_fkey FOREIGN KEY (suite) REFERENCES suite(id);


--
-- Name: extra_src_references_bin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY extra_src_references
    ADD CONSTRAINT extra_src_references_bin_id_fkey FOREIGN KEY (bin_id) REFERENCES binaries(id) ON DELETE CASCADE;


--
-- Name: extra_src_references_src_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY extra_src_references
    ADD CONSTRAINT extra_src_references_src_id_fkey FOREIGN KEY (src_id) REFERENCES source(id) ON DELETE RESTRICT;


--
-- Name: files_location; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY files
    ADD CONSTRAINT files_location FOREIGN KEY (location) REFERENCES location(id) MATCH FULL;


--
-- Name: fingerprint_binary_acl_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY fingerprint
    ADD CONSTRAINT fingerprint_binary_acl_id_fkey FOREIGN KEY (binary_acl_id) REFERENCES binary_acl(id);


--
-- Name: fingerprint_source_acl_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY fingerprint
    ADD CONSTRAINT fingerprint_source_acl_id_fkey FOREIGN KEY (source_acl_id) REFERENCES source_acl(id);


--
-- Name: fingerprint_uid; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY fingerprint
    ADD CONSTRAINT fingerprint_uid FOREIGN KEY (uid) REFERENCES uid(id) MATCH FULL;


--
-- Name: keyring_acl_map_architecture_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY keyring_acl_map
    ADD CONSTRAINT keyring_acl_map_architecture_id_fkey FOREIGN KEY (architecture_id) REFERENCES architecture(id);


--
-- Name: keyring_acl_map_keyring_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY keyring_acl_map
    ADD CONSTRAINT keyring_acl_map_keyring_id_fkey FOREIGN KEY (keyring_id) REFERENCES keyrings(id);


--
-- Name: keyrings_default_binary_acl_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY keyrings
    ADD CONSTRAINT keyrings_default_binary_acl_id_fkey FOREIGN KEY (default_binary_acl_id) REFERENCES binary_acl(id);


--
-- Name: keyrings_default_source_acl_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY keyrings
    ADD CONSTRAINT keyrings_default_source_acl_id_fkey FOREIGN KEY (default_source_acl_id) REFERENCES source_acl(id);


--
-- Name: known_changes_approved_for_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes
    ADD CONSTRAINT known_changes_approved_for_fkey FOREIGN KEY (in_queue) REFERENCES policy_queue(id) ON DELETE RESTRICT;


--
-- Name: known_changes_in_queue_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY changes
    ADD CONSTRAINT known_changes_in_queue_fkey FOREIGN KEY (in_queue) REFERENCES policy_queue(id) ON DELETE RESTRICT;


--
-- Name: location_archive_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY location
    ADD CONSTRAINT location_archive_fkey FOREIGN KEY (archive) REFERENCES archive(id);


--
-- Name: location_component_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY location
    ADD CONSTRAINT location_component_fkey FOREIGN KEY (component) REFERENCES component(id);


--
-- Name: override_component; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY override
    ADD CONSTRAINT override_component FOREIGN KEY (component) REFERENCES component(id) MATCH FULL;


--
-- Name: override_priority; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY override
    ADD CONSTRAINT override_priority FOREIGN KEY (priority) REFERENCES priority(id) MATCH FULL;


--
-- Name: override_section; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY override
    ADD CONSTRAINT override_section FOREIGN KEY (section) REFERENCES section(id) MATCH FULL;


--
-- Name: override_suite; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY override
    ADD CONSTRAINT override_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;


--
-- Name: override_type; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY override
    ADD CONSTRAINT override_type FOREIGN KEY (type) REFERENCES override_type(id) MATCH FULL;


--
-- Name: queue_files_fileid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY build_queue_files
    ADD CONSTRAINT queue_files_fileid_fkey FOREIGN KEY (fileid) REFERENCES files(id) ON DELETE CASCADE;


--
-- Name: source_changedby; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY source
    ADD CONSTRAINT source_changedby FOREIGN KEY (changedby) REFERENCES maintainer(id) MATCH FULL;


--
-- Name: source_file; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY source
    ADD CONSTRAINT source_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;


--
-- Name: source_maintainer; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY source
    ADD CONSTRAINT source_maintainer FOREIGN KEY (maintainer) REFERENCES maintainer(id) MATCH FULL;


--
-- Name: source_metadata_key_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY source_metadata
    ADD CONSTRAINT source_metadata_key_id_fkey FOREIGN KEY (key_id) REFERENCES metadata_keys(key_id);


--
-- Name: source_metadata_src_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY source_metadata
    ADD CONSTRAINT source_metadata_src_id_fkey FOREIGN KEY (src_id) REFERENCES source(id) ON DELETE CASCADE;


--
-- Name: source_sig_fpr; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY source
    ADD CONSTRAINT source_sig_fpr FOREIGN KEY (sig_fpr) REFERENCES fingerprint(id) MATCH FULL;


--
-- Name: src_associations_source; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY src_associations
    ADD CONSTRAINT src_associations_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;


--
-- Name: src_associations_suite; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY src_associations
    ADD CONSTRAINT src_associations_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;


--
-- Name: src_contents_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY src_contents
    ADD CONSTRAINT src_contents_source_id_fkey FOREIGN KEY (source_id) REFERENCES source(id) ON DELETE CASCADE;


--
-- Name: src_format_key; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY suite_src_formats
    ADD CONSTRAINT src_format_key FOREIGN KEY (src_format) REFERENCES src_format(id);


--
-- Name: src_uploaders_maintainer; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY src_uploaders
    ADD CONSTRAINT src_uploaders_maintainer FOREIGN KEY (maintainer) REFERENCES maintainer(id) ON DELETE CASCADE;


--
-- Name: src_uploaders_source; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY src_uploaders
    ADD CONSTRAINT src_uploaders_source FOREIGN KEY (source) REFERENCES source(id) ON DELETE CASCADE;


--
-- Name: suite_architectures_architectur; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY suite_architectures
    ADD CONSTRAINT suite_architectures_architectur FOREIGN KEY (architecture) REFERENCES architecture(id) MATCH FULL;


--
-- Name: suite_architectures_suite; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY suite_architectures
    ADD CONSTRAINT suite_architectures_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;


--
-- Name: suite_build_queue_copy_build_queue_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY suite_build_queue_copy
    ADD CONSTRAINT suite_build_queue_copy_build_queue_id_fkey FOREIGN KEY (build_queue_id) REFERENCES build_queue(id) ON DELETE RESTRICT;


--
-- Name: suite_key; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY suite_src_formats
    ADD CONSTRAINT suite_key FOREIGN KEY (suite) REFERENCES suite(id);


--
-- Name: suite_policy_queue_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY suite
    ADD CONSTRAINT suite_policy_queue_fkey FOREIGN KEY (policy_queue_id) REFERENCES policy_queue(id) ON DELETE RESTRICT;


--
-- Name: suite_queue_copy_suite_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY suite_build_queue_copy
    ADD CONSTRAINT suite_queue_copy_suite_fkey FOREIGN KEY (suite) REFERENCES suite(id);


--
-- Name: upload_blocks_fingerprint_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY upload_blocks
    ADD CONSTRAINT upload_blocks_fingerprint_id_fkey FOREIGN KEY (fingerprint_id) REFERENCES fingerprint(id);


--
-- Name: upload_blocks_uid_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY upload_blocks
    ADD CONSTRAINT upload_blocks_uid_id_fkey FOREIGN KEY (uid_id) REFERENCES uid(id);


--
-- Name: version_check_reference_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY version_check
    ADD CONSTRAINT version_check_reference_fkey FOREIGN KEY (reference) REFERENCES suite(id);


--
-- Name: version_check_suite_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dak
--

ALTER TABLE ONLY version_check
    ADD CONSTRAINT version_check_suite_fkey FOREIGN KEY (suite) REFERENCES suite(id);


--
-- Name: audit; Type: ACL; Schema: -; Owner: dak
--

REVOKE ALL ON SCHEMA audit FROM PUBLIC;
REVOKE ALL ON SCHEMA audit FROM dak;
GRANT ALL ON SCHEMA audit TO dak;
GRANT USAGE ON SCHEMA audit TO PUBLIC;
GRANT USAGE ON SCHEMA audit TO ftpteam;
GRANT USAGE ON SCHEMA audit TO ftpmaster;


--
-- Name: public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM postgres;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO PUBLIC;


SET search_path = audit, pg_catalog;

--
-- Name: package_changes; Type: ACL; Schema: audit; Owner: dak
--

REVOKE ALL ON TABLE package_changes FROM PUBLIC;
REVOKE ALL ON TABLE package_changes FROM dak;
GRANT ALL ON TABLE package_changes TO dak;
GRANT SELECT ON TABLE package_changes TO PUBLIC;


SET search_path = public, pg_catalog;

--
-- Name: bin_associations_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE bin_associations_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE bin_associations_id_seq FROM dak;
GRANT ALL ON SEQUENCE bin_associations_id_seq TO dak;
GRANT SELECT ON SEQUENCE bin_associations_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE bin_associations_id_seq TO ftpmaster;


--
-- Name: bin_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE bin_associations FROM PUBLIC;
REVOKE ALL ON TABLE bin_associations FROM dak;
GRANT ALL ON TABLE bin_associations TO dak;
GRANT SELECT ON TABLE bin_associations TO PUBLIC;
GRANT ALL ON TABLE bin_associations TO ftpmaster;
GRANT DELETE ON TABLE bin_associations TO ftpteam;


--
-- Name: binaries_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE binaries_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE binaries_id_seq FROM dak;
GRANT ALL ON SEQUENCE binaries_id_seq TO dak;
GRANT SELECT ON SEQUENCE binaries_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE binaries_id_seq TO ftpmaster;


--
-- Name: binaries; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE binaries FROM PUBLIC;
REVOKE ALL ON TABLE binaries FROM dak;
GRANT ALL ON TABLE binaries TO dak;
GRANT SELECT ON TABLE binaries TO PUBLIC;
GRANT ALL ON TABLE binaries TO ftpmaster;


--
-- Name: bin_associations_binaries; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE bin_associations_binaries FROM PUBLIC;
REVOKE ALL ON TABLE bin_associations_binaries FROM dak;
GRANT ALL ON TABLE bin_associations_binaries TO dak;
GRANT SELECT ON TABLE bin_associations_binaries TO ftpmaster;
GRANT SELECT ON TABLE bin_associations_binaries TO PUBLIC;


--
-- Name: source_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE source_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE source_id_seq FROM dak;
GRANT ALL ON SEQUENCE source_id_seq TO dak;
GRANT SELECT ON SEQUENCE source_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE source_id_seq TO ftpmaster;


--
-- Name: source; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE source FROM PUBLIC;
REVOKE ALL ON TABLE source FROM dak;
GRANT ALL ON TABLE source TO dak;
GRANT SELECT ON TABLE source TO PUBLIC;
GRANT ALL ON TABLE source TO ftpmaster;


--
-- Name: src_associations_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE src_associations_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE src_associations_id_seq FROM dak;
GRANT ALL ON SEQUENCE src_associations_id_seq TO dak;
GRANT SELECT ON SEQUENCE src_associations_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE src_associations_id_seq TO ftpmaster;


--
-- Name: src_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE src_associations FROM PUBLIC;
REVOKE ALL ON TABLE src_associations FROM dak;
GRANT ALL ON TABLE src_associations TO dak;
GRANT SELECT ON TABLE src_associations TO PUBLIC;
GRANT ALL ON TABLE src_associations TO ftpmaster;
GRANT DELETE ON TABLE src_associations TO ftpteam;


--
-- Name: src_associations_bin; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE src_associations_bin FROM PUBLIC;
REVOKE ALL ON TABLE src_associations_bin FROM dak;
GRANT ALL ON TABLE src_associations_bin TO dak;
GRANT SELECT ON TABLE src_associations_bin TO ftpmaster;
GRANT SELECT ON TABLE src_associations_bin TO PUBLIC;


--
-- Name: almost_obsolete_all_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE almost_obsolete_all_associations FROM PUBLIC;
REVOKE ALL ON TABLE almost_obsolete_all_associations FROM dak;
GRANT ALL ON TABLE almost_obsolete_all_associations TO dak;
GRANT SELECT ON TABLE almost_obsolete_all_associations TO ftpmaster;
GRANT SELECT ON TABLE almost_obsolete_all_associations TO PUBLIC;


--
-- Name: any_associations_source; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE any_associations_source FROM PUBLIC;
REVOKE ALL ON TABLE any_associations_source FROM dak;
GRANT ALL ON TABLE any_associations_source TO dak;
GRANT SELECT ON TABLE any_associations_source TO ftpmaster;
GRANT SELECT ON TABLE any_associations_source TO PUBLIC;


--
-- Name: src_associations_src; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE src_associations_src FROM PUBLIC;
REVOKE ALL ON TABLE src_associations_src FROM dak;
GRANT ALL ON TABLE src_associations_src TO dak;
GRANT SELECT ON TABLE src_associations_src TO ftpmaster;
GRANT SELECT ON TABLE src_associations_src TO PUBLIC;


--
-- Name: almost_obsolete_src_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE almost_obsolete_src_associations FROM PUBLIC;
REVOKE ALL ON TABLE almost_obsolete_src_associations FROM dak;
GRANT ALL ON TABLE almost_obsolete_src_associations TO dak;
GRANT SELECT ON TABLE almost_obsolete_src_associations TO ftpmaster;
GRANT SELECT ON TABLE almost_obsolete_src_associations TO PUBLIC;


--
-- Name: architecture_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE architecture_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE architecture_id_seq FROM dak;
GRANT ALL ON SEQUENCE architecture_id_seq TO dak;
GRANT SELECT ON SEQUENCE architecture_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE architecture_id_seq TO ftpmaster;


--
-- Name: architecture; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE architecture FROM PUBLIC;
REVOKE ALL ON TABLE architecture FROM dak;
GRANT ALL ON TABLE architecture TO dak;
GRANT SELECT ON TABLE architecture TO PUBLIC;
GRANT ALL ON TABLE architecture TO ftpmaster;


--
-- Name: archive_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE archive_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE archive_id_seq FROM dak;
GRANT ALL ON SEQUENCE archive_id_seq TO dak;
GRANT SELECT ON SEQUENCE archive_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE archive_id_seq TO ftpmaster;


--
-- Name: archive; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE archive FROM PUBLIC;
REVOKE ALL ON TABLE archive FROM dak;
GRANT ALL ON TABLE archive TO dak;
GRANT SELECT ON TABLE archive TO PUBLIC;
GRANT ALL ON TABLE archive TO ftpmaster;


--
-- Name: bin_contents; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE bin_contents FROM PUBLIC;
REVOKE ALL ON TABLE bin_contents FROM dak;
GRANT ALL ON TABLE bin_contents TO dak;
GRANT SELECT ON TABLE bin_contents TO PUBLIC;
GRANT ALL ON TABLE bin_contents TO ftpmaster;


--
-- Name: binaries_metadata; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE binaries_metadata FROM PUBLIC;
REVOKE ALL ON TABLE binaries_metadata FROM dak;
GRANT ALL ON TABLE binaries_metadata TO dak;
GRANT SELECT,INSERT,UPDATE ON TABLE binaries_metadata TO ftpmaster;
GRANT SELECT ON TABLE binaries_metadata TO PUBLIC;


--
-- Name: suite_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE suite_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE suite_id_seq FROM dak;
GRANT ALL ON SEQUENCE suite_id_seq TO dak;
GRANT SELECT ON SEQUENCE suite_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE suite_id_seq TO ftpmaster;


--
-- Name: suite; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE suite FROM PUBLIC;
REVOKE ALL ON TABLE suite FROM dak;
GRANT ALL ON TABLE suite TO dak;
GRANT SELECT ON TABLE suite TO PUBLIC;
GRANT ALL ON TABLE suite TO ftpmaster;


--
-- Name: binaries_suite_arch; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE binaries_suite_arch FROM PUBLIC;
REVOKE ALL ON TABLE binaries_suite_arch FROM dak;
GRANT ALL ON TABLE binaries_suite_arch TO dak;
GRANT SELECT ON TABLE binaries_suite_arch TO ftpmaster;
GRANT SELECT ON TABLE binaries_suite_arch TO PUBLIC;


--
-- Name: binary_acl; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE binary_acl FROM PUBLIC;
REVOKE ALL ON TABLE binary_acl FROM dak;
GRANT ALL ON TABLE binary_acl TO dak;
GRANT SELECT ON TABLE binary_acl TO PUBLIC;
GRANT ALL ON TABLE binary_acl TO ftpmaster;


--
-- Name: binary_acl_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE binary_acl_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE binary_acl_id_seq FROM dak;
GRANT ALL ON SEQUENCE binary_acl_id_seq TO dak;
GRANT ALL ON SEQUENCE binary_acl_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE binary_acl_id_seq TO PUBLIC;


--
-- Name: binary_acl_map; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE binary_acl_map FROM PUBLIC;
REVOKE ALL ON TABLE binary_acl_map FROM dak;
GRANT ALL ON TABLE binary_acl_map TO dak;
GRANT SELECT ON TABLE binary_acl_map TO PUBLIC;
GRANT ALL ON TABLE binary_acl_map TO ftpmaster;


--
-- Name: binary_acl_map_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE binary_acl_map_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE binary_acl_map_id_seq FROM dak;
GRANT ALL ON SEQUENCE binary_acl_map_id_seq TO dak;
GRANT ALL ON SEQUENCE binary_acl_map_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE binary_acl_map_id_seq TO PUBLIC;


--
-- Name: files_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE files_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE files_id_seq FROM dak;
GRANT ALL ON SEQUENCE files_id_seq TO dak;
GRANT SELECT ON SEQUENCE files_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE files_id_seq TO ftpmaster;


--
-- Name: files; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE files FROM PUBLIC;
REVOKE ALL ON TABLE files FROM dak;
GRANT ALL ON TABLE files TO dak;
GRANT SELECT ON TABLE files TO PUBLIC;
GRANT ALL ON TABLE files TO ftpmaster;


--
-- Name: location_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE location_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE location_id_seq FROM dak;
GRANT ALL ON SEQUENCE location_id_seq TO dak;
GRANT SELECT ON SEQUENCE location_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE location_id_seq TO ftpmaster;


--
-- Name: location; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE location FROM PUBLIC;
REVOKE ALL ON TABLE location FROM dak;
GRANT ALL ON TABLE location TO dak;
GRANT SELECT ON TABLE location TO PUBLIC;
GRANT ALL ON TABLE location TO ftpmaster;


--
-- Name: binfiles_suite_component_arch; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE binfiles_suite_component_arch FROM PUBLIC;
REVOKE ALL ON TABLE binfiles_suite_component_arch FROM dak;
GRANT ALL ON TABLE binfiles_suite_component_arch TO dak;
GRANT SELECT ON TABLE binfiles_suite_component_arch TO ftpmaster;
GRANT SELECT ON TABLE binfiles_suite_component_arch TO PUBLIC;


--
-- Name: build_queue; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE build_queue FROM PUBLIC;
REVOKE ALL ON TABLE build_queue FROM dak;
GRANT ALL ON TABLE build_queue TO dak;
GRANT SELECT ON TABLE build_queue TO PUBLIC;
GRANT ALL ON TABLE build_queue TO ftpmaster;


--
-- Name: build_queue_files; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE build_queue_files FROM PUBLIC;
REVOKE ALL ON TABLE build_queue_files FROM dak;
GRANT ALL ON TABLE build_queue_files TO dak;
GRANT SELECT ON TABLE build_queue_files TO PUBLIC;
GRANT ALL ON TABLE build_queue_files TO ftpmaster;


--
-- Name: build_queue_files_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE build_queue_files_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE build_queue_files_id_seq FROM dak;
GRANT ALL ON SEQUENCE build_queue_files_id_seq TO dak;
GRANT ALL ON SEQUENCE build_queue_files_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE build_queue_files_id_seq TO PUBLIC;


--
-- Name: build_queue_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE build_queue_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE build_queue_id_seq FROM dak;
GRANT ALL ON SEQUENCE build_queue_id_seq TO dak;
GRANT ALL ON SEQUENCE build_queue_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE build_queue_id_seq TO PUBLIC;


--
-- Name: build_queue_policy_files; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE build_queue_policy_files FROM PUBLIC;
REVOKE ALL ON TABLE build_queue_policy_files FROM dak;
GRANT ALL ON TABLE build_queue_policy_files TO dak;
GRANT SELECT,INSERT,UPDATE ON TABLE build_queue_policy_files TO ftpmaster;
GRANT SELECT ON TABLE build_queue_policy_files TO PUBLIC;


--
-- Name: changelogs_text; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changelogs_text FROM PUBLIC;
REVOKE ALL ON TABLE changelogs_text FROM dak;
GRANT ALL ON TABLE changelogs_text TO dak;
GRANT SELECT ON TABLE changelogs_text TO PUBLIC;
GRANT ALL ON TABLE changelogs_text TO ftpmaster;


--
-- Name: changes; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changes FROM PUBLIC;
REVOKE ALL ON TABLE changes FROM dak;
GRANT ALL ON TABLE changes TO dak;
GRANT ALL ON TABLE changes TO ftpmaster;
GRANT SELECT ON TABLE changes TO PUBLIC;
GRANT DELETE,UPDATE ON TABLE changes TO ftpteam;


--
-- Name: changelogs; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changelogs FROM PUBLIC;
REVOKE ALL ON TABLE changelogs FROM dak;
GRANT ALL ON TABLE changelogs TO dak;
GRANT SELECT ON TABLE changelogs TO PUBLIC;
GRANT ALL ON TABLE changelogs TO ftpmaster;


--
-- Name: changelogs_text_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE changelogs_text_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE changelogs_text_id_seq FROM dak;
GRANT ALL ON SEQUENCE changelogs_text_id_seq TO dak;
GRANT ALL ON SEQUENCE changelogs_text_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE changelogs_text_id_seq TO PUBLIC;


--
-- Name: changes_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE changes_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE changes_id_seq FROM dak;
GRANT ALL ON SEQUENCE changes_id_seq TO dak;
GRANT ALL ON SEQUENCE changes_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE changes_id_seq TO PUBLIC;


--
-- Name: changes_pending_binaries; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changes_pending_binaries FROM PUBLIC;
REVOKE ALL ON TABLE changes_pending_binaries FROM dak;
GRANT ALL ON TABLE changes_pending_binaries TO dak;
GRANT SELECT ON TABLE changes_pending_binaries TO PUBLIC;
GRANT ALL ON TABLE changes_pending_binaries TO ftpmaster;


--
-- Name: changes_pending_binaries_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE changes_pending_binaries_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE changes_pending_binaries_id_seq FROM dak;
GRANT ALL ON SEQUENCE changes_pending_binaries_id_seq TO dak;
GRANT ALL ON SEQUENCE changes_pending_binaries_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE changes_pending_binaries_id_seq TO PUBLIC;


--
-- Name: changes_pending_files; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changes_pending_files FROM PUBLIC;
REVOKE ALL ON TABLE changes_pending_files FROM dak;
GRANT ALL ON TABLE changes_pending_files TO dak;
GRANT SELECT ON TABLE changes_pending_files TO PUBLIC;
GRANT ALL ON TABLE changes_pending_files TO ftpmaster;
GRANT DELETE ON TABLE changes_pending_files TO ftpteam;


--
-- Name: changes_pending_files_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE changes_pending_files_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE changes_pending_files_id_seq FROM dak;
GRANT ALL ON SEQUENCE changes_pending_files_id_seq TO dak;
GRANT ALL ON SEQUENCE changes_pending_files_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE changes_pending_files_id_seq TO PUBLIC;
GRANT USAGE ON SEQUENCE changes_pending_files_id_seq TO ftpteam;


--
-- Name: changes_pending_files_map; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changes_pending_files_map FROM PUBLIC;
REVOKE ALL ON TABLE changes_pending_files_map FROM dak;
GRANT ALL ON TABLE changes_pending_files_map TO dak;
GRANT SELECT,INSERT,DELETE ON TABLE changes_pending_files_map TO ftpteam;
GRANT SELECT ON TABLE changes_pending_files_map TO PUBLIC;


--
-- Name: changes_pending_source; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changes_pending_source FROM PUBLIC;
REVOKE ALL ON TABLE changes_pending_source FROM dak;
GRANT ALL ON TABLE changes_pending_source TO dak;
GRANT SELECT ON TABLE changes_pending_source TO PUBLIC;
GRANT ALL ON TABLE changes_pending_source TO ftpmaster;


--
-- Name: changes_pending_source_files; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changes_pending_source_files FROM PUBLIC;
REVOKE ALL ON TABLE changes_pending_source_files FROM dak;
GRANT ALL ON TABLE changes_pending_source_files TO dak;
GRANT SELECT ON TABLE changes_pending_source_files TO PUBLIC;
GRANT ALL ON TABLE changes_pending_source_files TO ftpmaster;


--
-- Name: changes_pending_source_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE changes_pending_source_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE changes_pending_source_id_seq FROM dak;
GRANT ALL ON SEQUENCE changes_pending_source_id_seq TO dak;
GRANT ALL ON SEQUENCE changes_pending_source_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE changes_pending_source_id_seq TO PUBLIC;


--
-- Name: changes_pool_files; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE changes_pool_files FROM PUBLIC;
REVOKE ALL ON TABLE changes_pool_files FROM dak;
GRANT ALL ON TABLE changes_pool_files TO dak;
GRANT SELECT ON TABLE changes_pool_files TO PUBLIC;
GRANT ALL ON TABLE changes_pool_files TO ftpmaster;
GRANT DELETE ON TABLE changes_pool_files TO ftpteam;


--
-- Name: component_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE component_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE component_id_seq FROM dak;
GRANT ALL ON SEQUENCE component_id_seq TO dak;
GRANT SELECT ON SEQUENCE component_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE component_id_seq TO ftpmaster;


--
-- Name: component; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE component FROM PUBLIC;
REVOKE ALL ON TABLE component FROM dak;
GRANT ALL ON TABLE component TO dak;
GRANT SELECT ON TABLE component TO PUBLIC;
GRANT ALL ON TABLE component TO ftpmaster;


--
-- Name: config; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE config FROM PUBLIC;
REVOKE ALL ON TABLE config FROM dak;
GRANT ALL ON TABLE config TO dak;
GRANT ALL ON TABLE config TO ftpmaster;
GRANT SELECT ON TABLE config TO ftpteam;
GRANT SELECT ON TABLE config TO PUBLIC;


--
-- Name: config_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE config_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE config_id_seq FROM dak;
GRANT ALL ON SEQUENCE config_id_seq TO dak;
GRANT ALL ON SEQUENCE config_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE config_id_seq TO PUBLIC;


--
-- Name: dsc_files_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE dsc_files_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE dsc_files_id_seq FROM dak;
GRANT ALL ON SEQUENCE dsc_files_id_seq TO dak;
GRANT SELECT ON SEQUENCE dsc_files_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE dsc_files_id_seq TO ftpmaster;


--
-- Name: dsc_files; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE dsc_files FROM PUBLIC;
REVOKE ALL ON TABLE dsc_files FROM dak;
GRANT ALL ON TABLE dsc_files TO dak;
GRANT SELECT ON TABLE dsc_files TO PUBLIC;
GRANT ALL ON TABLE dsc_files TO ftpmaster;


--
-- Name: external_overrides; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE external_overrides FROM PUBLIC;
REVOKE ALL ON TABLE external_overrides FROM dak;
GRANT ALL ON TABLE external_overrides TO dak;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE external_overrides TO ftpmaster;
GRANT SELECT ON TABLE external_overrides TO PUBLIC;


--
-- Name: extra_src_references; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE extra_src_references FROM PUBLIC;
REVOKE ALL ON TABLE extra_src_references FROM dak;
GRANT ALL ON TABLE extra_src_references TO dak;
GRANT SELECT,INSERT,UPDATE ON TABLE extra_src_references TO ftpmaster;
GRANT SELECT ON TABLE extra_src_references TO PUBLIC;


--
-- Name: file_arch_suite; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE file_arch_suite FROM PUBLIC;
REVOKE ALL ON TABLE file_arch_suite FROM dak;
GRANT ALL ON TABLE file_arch_suite TO dak;
GRANT ALL ON TABLE file_arch_suite TO ftpmaster;
GRANT SELECT ON TABLE file_arch_suite TO PUBLIC;


--
-- Name: fingerprint_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE fingerprint_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE fingerprint_id_seq FROM dak;
GRANT ALL ON SEQUENCE fingerprint_id_seq TO dak;
GRANT SELECT ON SEQUENCE fingerprint_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE fingerprint_id_seq TO ftpmaster;


--
-- Name: fingerprint; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE fingerprint FROM PUBLIC;
REVOKE ALL ON TABLE fingerprint FROM dak;
GRANT ALL ON TABLE fingerprint TO dak;
GRANT SELECT ON TABLE fingerprint TO PUBLIC;
GRANT ALL ON TABLE fingerprint TO ftpmaster;


--
-- Name: keyring_acl_map; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE keyring_acl_map FROM PUBLIC;
REVOKE ALL ON TABLE keyring_acl_map FROM dak;
GRANT ALL ON TABLE keyring_acl_map TO dak;
GRANT SELECT ON TABLE keyring_acl_map TO PUBLIC;
GRANT ALL ON TABLE keyring_acl_map TO ftpmaster;


--
-- Name: keyring_acl_map_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE keyring_acl_map_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE keyring_acl_map_id_seq FROM dak;
GRANT ALL ON SEQUENCE keyring_acl_map_id_seq TO dak;
GRANT ALL ON SEQUENCE keyring_acl_map_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE keyring_acl_map_id_seq TO PUBLIC;


--
-- Name: keyrings; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE keyrings FROM PUBLIC;
REVOKE ALL ON TABLE keyrings FROM dak;
GRANT ALL ON TABLE keyrings TO dak;
GRANT SELECT ON TABLE keyrings TO PUBLIC;
GRANT ALL ON TABLE keyrings TO ftpmaster;


--
-- Name: keyrings_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE keyrings_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE keyrings_id_seq FROM dak;
GRANT ALL ON SEQUENCE keyrings_id_seq TO dak;
GRANT SELECT ON SEQUENCE keyrings_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE keyrings_id_seq TO ftpmaster;


--
-- Name: maintainer_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE maintainer_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE maintainer_id_seq FROM dak;
GRANT ALL ON SEQUENCE maintainer_id_seq TO dak;
GRANT SELECT ON SEQUENCE maintainer_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE maintainer_id_seq TO ftpmaster;


--
-- Name: maintainer; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE maintainer FROM PUBLIC;
REVOKE ALL ON TABLE maintainer FROM dak;
GRANT ALL ON TABLE maintainer TO dak;
GRANT SELECT ON TABLE maintainer TO PUBLIC;
GRANT ALL ON TABLE maintainer TO ftpmaster;


--
-- Name: metadata_keys; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE metadata_keys FROM PUBLIC;
REVOKE ALL ON TABLE metadata_keys FROM dak;
GRANT ALL ON TABLE metadata_keys TO dak;
GRANT SELECT,INSERT,UPDATE ON TABLE metadata_keys TO ftpmaster;
GRANT SELECT ON TABLE metadata_keys TO PUBLIC;


--
-- Name: metadata_keys_key_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE metadata_keys_key_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE metadata_keys_key_id_seq FROM dak;
GRANT ALL ON SEQUENCE metadata_keys_key_id_seq TO dak;
GRANT ALL ON SEQUENCE metadata_keys_key_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE metadata_keys_key_id_seq TO PUBLIC;


--
-- Name: new_comments; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE new_comments FROM PUBLIC;
REVOKE ALL ON TABLE new_comments FROM dak;
GRANT ALL ON TABLE new_comments TO dak;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE new_comments TO ftptrainee;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE new_comments TO ftpteam;
GRANT ALL ON TABLE new_comments TO ftpmaster;


--
-- Name: new_comments_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE new_comments_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE new_comments_id_seq FROM dak;
GRANT ALL ON SEQUENCE new_comments_id_seq TO dak;
GRANT SELECT,UPDATE ON SEQUENCE new_comments_id_seq TO ftptrainee;
GRANT SELECT,UPDATE ON SEQUENCE new_comments_id_seq TO ftpteam;
GRANT ALL ON SEQUENCE new_comments_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE new_comments_id_seq TO PUBLIC;


--
-- Name: newest_all_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE newest_all_associations FROM PUBLIC;
REVOKE ALL ON TABLE newest_all_associations FROM dak;
GRANT ALL ON TABLE newest_all_associations TO dak;
GRANT SELECT ON TABLE newest_all_associations TO ftpmaster;
GRANT SELECT ON TABLE newest_all_associations TO PUBLIC;


--
-- Name: newest_any_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE newest_any_associations FROM PUBLIC;
REVOKE ALL ON TABLE newest_any_associations FROM dak;
GRANT ALL ON TABLE newest_any_associations TO dak;
GRANT SELECT ON TABLE newest_any_associations TO ftpmaster;
GRANT SELECT ON TABLE newest_any_associations TO PUBLIC;


--
-- Name: source_suite; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE source_suite FROM PUBLIC;
REVOKE ALL ON TABLE source_suite FROM dak;
GRANT ALL ON TABLE source_suite TO dak;
GRANT SELECT ON TABLE source_suite TO ftpmaster;
GRANT SELECT ON TABLE source_suite TO PUBLIC;


--
-- Name: newest_source; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE newest_source FROM PUBLIC;
REVOKE ALL ON TABLE newest_source FROM dak;
GRANT ALL ON TABLE newest_source TO dak;
GRANT SELECT ON TABLE newest_source TO ftpmaster;
GRANT SELECT ON TABLE newest_source TO PUBLIC;


--
-- Name: newest_src_association; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE newest_src_association FROM PUBLIC;
REVOKE ALL ON TABLE newest_src_association FROM dak;
GRANT ALL ON TABLE newest_src_association TO dak;
GRANT SELECT ON TABLE newest_src_association TO ftpmaster;
GRANT SELECT ON TABLE newest_src_association TO PUBLIC;


--
-- Name: obsolete_all_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE obsolete_all_associations FROM PUBLIC;
REVOKE ALL ON TABLE obsolete_all_associations FROM dak;
GRANT ALL ON TABLE obsolete_all_associations TO dak;
GRANT SELECT ON TABLE obsolete_all_associations TO ftpmaster;
GRANT SELECT ON TABLE obsolete_all_associations TO PUBLIC;


--
-- Name: obsolete_any_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE obsolete_any_associations FROM PUBLIC;
REVOKE ALL ON TABLE obsolete_any_associations FROM dak;
GRANT ALL ON TABLE obsolete_any_associations TO dak;
GRANT SELECT ON TABLE obsolete_any_associations TO ftpmaster;
GRANT SELECT ON TABLE obsolete_any_associations TO PUBLIC;


--
-- Name: obsolete_any_by_all_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE obsolete_any_by_all_associations FROM PUBLIC;
REVOKE ALL ON TABLE obsolete_any_by_all_associations FROM dak;
GRANT ALL ON TABLE obsolete_any_by_all_associations TO dak;
GRANT SELECT ON TABLE obsolete_any_by_all_associations TO ftpmaster;
GRANT SELECT ON TABLE obsolete_any_by_all_associations TO PUBLIC;


--
-- Name: obsolete_src_associations; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE obsolete_src_associations FROM PUBLIC;
REVOKE ALL ON TABLE obsolete_src_associations FROM dak;
GRANT ALL ON TABLE obsolete_src_associations TO dak;
GRANT SELECT ON TABLE obsolete_src_associations TO ftpmaster;
GRANT SELECT ON TABLE obsolete_src_associations TO PUBLIC;


--
-- Name: override; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE override FROM PUBLIC;
REVOKE ALL ON TABLE override FROM dak;
GRANT ALL ON TABLE override TO dak;
GRANT SELECT ON TABLE override TO PUBLIC;
GRANT ALL ON TABLE override TO ftpmaster;
GRANT INSERT,DELETE,UPDATE ON TABLE override TO ftpteam;


--
-- Name: override_type_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE override_type_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE override_type_id_seq FROM dak;
GRANT ALL ON SEQUENCE override_type_id_seq TO dak;
GRANT SELECT ON SEQUENCE override_type_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE override_type_id_seq TO ftpmaster;


--
-- Name: override_type; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE override_type FROM PUBLIC;
REVOKE ALL ON TABLE override_type FROM dak;
GRANT ALL ON TABLE override_type TO dak;
GRANT SELECT ON TABLE override_type TO PUBLIC;
GRANT ALL ON TABLE override_type TO ftpmaster;


--
-- Name: policy_queue; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE policy_queue FROM PUBLIC;
REVOKE ALL ON TABLE policy_queue FROM dak;
GRANT ALL ON TABLE policy_queue TO dak;
GRANT SELECT ON TABLE policy_queue TO PUBLIC;
GRANT ALL ON TABLE policy_queue TO ftpmaster;


--
-- Name: policy_queue_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE policy_queue_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE policy_queue_id_seq FROM dak;
GRANT ALL ON SEQUENCE policy_queue_id_seq TO dak;
GRANT ALL ON SEQUENCE policy_queue_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE policy_queue_id_seq TO PUBLIC;


--
-- Name: priority_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE priority_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE priority_id_seq FROM dak;
GRANT ALL ON SEQUENCE priority_id_seq TO dak;
GRANT SELECT ON SEQUENCE priority_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE priority_id_seq TO ftpmaster;


--
-- Name: priority; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE priority FROM PUBLIC;
REVOKE ALL ON TABLE priority FROM dak;
GRANT ALL ON TABLE priority TO dak;
GRANT SELECT ON TABLE priority TO PUBLIC;
GRANT ALL ON TABLE priority TO ftpmaster;


--
-- Name: section_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE section_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE section_id_seq FROM dak;
GRANT ALL ON SEQUENCE section_id_seq TO dak;
GRANT SELECT ON SEQUENCE section_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE section_id_seq TO ftpmaster;


--
-- Name: section; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE section FROM PUBLIC;
REVOKE ALL ON TABLE section FROM dak;
GRANT ALL ON TABLE section TO dak;
GRANT SELECT ON TABLE section TO PUBLIC;
GRANT ALL ON TABLE section TO ftpmaster;


--
-- Name: source_acl; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE source_acl FROM PUBLIC;
REVOKE ALL ON TABLE source_acl FROM dak;
GRANT ALL ON TABLE source_acl TO dak;
GRANT SELECT ON TABLE source_acl TO PUBLIC;
GRANT ALL ON TABLE source_acl TO ftpmaster;


--
-- Name: source_acl_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE source_acl_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE source_acl_id_seq FROM dak;
GRANT ALL ON SEQUENCE source_acl_id_seq TO dak;
GRANT ALL ON SEQUENCE source_acl_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE source_acl_id_seq TO PUBLIC;


--
-- Name: source_metadata; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE source_metadata FROM PUBLIC;
REVOKE ALL ON TABLE source_metadata FROM dak;
GRANT ALL ON TABLE source_metadata TO dak;
GRANT SELECT,INSERT,UPDATE ON TABLE source_metadata TO ftpmaster;
GRANT SELECT ON TABLE source_metadata TO PUBLIC;


--
-- Name: src_contents; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE src_contents FROM PUBLIC;
REVOKE ALL ON TABLE src_contents FROM dak;
GRANT ALL ON TABLE src_contents TO dak;
GRANT SELECT,INSERT,UPDATE ON TABLE src_contents TO ftpmaster;
GRANT SELECT ON TABLE src_contents TO PUBLIC;


--
-- Name: src_format; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE src_format FROM PUBLIC;
REVOKE ALL ON TABLE src_format FROM dak;
GRANT ALL ON TABLE src_format TO dak;
GRANT SELECT ON TABLE src_format TO PUBLIC;
GRANT ALL ON TABLE src_format TO ftpmaster;


--
-- Name: src_format_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE src_format_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE src_format_id_seq FROM dak;
GRANT ALL ON SEQUENCE src_format_id_seq TO dak;
GRANT ALL ON SEQUENCE src_format_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE src_format_id_seq TO PUBLIC;


--
-- Name: src_uploaders; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE src_uploaders FROM PUBLIC;
REVOKE ALL ON TABLE src_uploaders FROM dak;
GRANT ALL ON TABLE src_uploaders TO dak;
GRANT SELECT ON TABLE src_uploaders TO PUBLIC;
GRANT ALL ON TABLE src_uploaders TO ftpmaster;


--
-- Name: src_uploaders_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE src_uploaders_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE src_uploaders_id_seq FROM dak;
GRANT ALL ON SEQUENCE src_uploaders_id_seq TO dak;
GRANT SELECT ON SEQUENCE src_uploaders_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE src_uploaders_id_seq TO ftpmaster;


--
-- Name: suite_architectures; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE suite_architectures FROM PUBLIC;
REVOKE ALL ON TABLE suite_architectures FROM dak;
GRANT ALL ON TABLE suite_architectures TO dak;
GRANT SELECT ON TABLE suite_architectures TO PUBLIC;
GRANT ALL ON TABLE suite_architectures TO ftpmaster;


--
-- Name: suite_arch_by_name; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE suite_arch_by_name FROM PUBLIC;
REVOKE ALL ON TABLE suite_arch_by_name FROM dak;
GRANT ALL ON TABLE suite_arch_by_name TO dak;
GRANT SELECT ON TABLE suite_arch_by_name TO PUBLIC;
GRANT SELECT ON TABLE suite_arch_by_name TO ftpmaster;


--
-- Name: suite_build_queue_copy; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE suite_build_queue_copy FROM PUBLIC;
REVOKE ALL ON TABLE suite_build_queue_copy FROM dak;
GRANT ALL ON TABLE suite_build_queue_copy TO dak;
GRANT SELECT ON TABLE suite_build_queue_copy TO PUBLIC;
GRANT ALL ON TABLE suite_build_queue_copy TO ftpmaster;


--
-- Name: suite_src_formats; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE suite_src_formats FROM PUBLIC;
REVOKE ALL ON TABLE suite_src_formats FROM dak;
GRANT ALL ON TABLE suite_src_formats TO dak;
GRANT SELECT ON TABLE suite_src_formats TO PUBLIC;
GRANT ALL ON TABLE suite_src_formats TO ftpmaster;


--
-- Name: uid_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE uid_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE uid_id_seq FROM dak;
GRANT ALL ON SEQUENCE uid_id_seq TO dak;
GRANT SELECT ON SEQUENCE uid_id_seq TO PUBLIC;
GRANT ALL ON SEQUENCE uid_id_seq TO ftpmaster;


--
-- Name: uid; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE uid FROM PUBLIC;
REVOKE ALL ON TABLE uid FROM dak;
GRANT ALL ON TABLE uid TO dak;
GRANT SELECT ON TABLE uid TO PUBLIC;
GRANT ALL ON TABLE uid TO ftpmaster;


--
-- Name: upload_blocks; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE upload_blocks FROM PUBLIC;
REVOKE ALL ON TABLE upload_blocks FROM dak;
GRANT ALL ON TABLE upload_blocks TO dak;
GRANT SELECT ON TABLE upload_blocks TO PUBLIC;
GRANT ALL ON TABLE upload_blocks TO ftpmaster;


--
-- Name: upload_blocks_id_seq; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON SEQUENCE upload_blocks_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE upload_blocks_id_seq FROM dak;
GRANT ALL ON SEQUENCE upload_blocks_id_seq TO dak;
GRANT ALL ON SEQUENCE upload_blocks_id_seq TO ftpmaster;
GRANT SELECT ON SEQUENCE upload_blocks_id_seq TO PUBLIC;


--
-- Name: version_check; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE version_check FROM PUBLIC;
REVOKE ALL ON TABLE version_check FROM dak;
GRANT ALL ON TABLE version_check TO dak;
GRANT SELECT,INSERT,UPDATE ON TABLE version_check TO ftpmaster;
GRANT SELECT ON TABLE version_check TO PUBLIC;


--
-- Name: version_checks; Type: ACL; Schema: public; Owner: dak
--

REVOKE ALL ON TABLE version_checks FROM PUBLIC;
REVOKE ALL ON TABLE version_checks FROM dak;
GRANT ALL ON TABLE version_checks TO dak;
GRANT SELECT ON TABLE version_checks TO PUBLIC;


--
-- PostgreSQL database dump complete
--

-- Set schema version
INSERT INTO config (name, value) VALUES ('db_revision', 68);

