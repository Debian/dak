DROP DATABASE projectb;
CREATE DATABASE projectb WITH ENCODING = 'SQL_ASCII';

\c projectb

CREATE TABLE archive (
       id SERIAL PRIMARY KEY,
       name TEXT UNIQUE NOT NULL,
       origin_server TEXT,
       description TEXT
);

CREATE TABLE component (
       id SERIAL PRIMARY KEY,
       name TEXT UNIQUE NOT NULL,
       description TEXT,
       meets_dfsg BOOLEAN
);

CREATE TABLE architecture (
       id SERIAL PRIMARY KEY,
       arch_string TEXT UNIQUE NOT NULL,
       description TEXT
);

CREATE TABLE maintainer (
       id SERIAL PRIMARY KEY,
       name TEXT UNIQUE NOT NULL
);

CREATE TABLE uid (
       id SERIAL PRIMARY KEY,
       uid TEXT UNIQUE NOT NULL,
       name TEXT
);

CREATE TABLE keyrings (
       id SERIAL PRIMARY KEY,
       name TEXT
);


CREATE TABLE fingerprint (
       id SERIAL PRIMARY KEY,
       fingerprint TEXT UNIQUE NOT NULL,
       uid INT4 REFERENCES uid,
       keyring INT4 REFERENCES keyrings
);

CREATE TABLE location (
       id SERIAL PRIMARY KEY,
       path TEXT NOT NULL,
       component INT4 REFERENCES component,
       archive INT4 REFERENCES archive,
       type TEXT NOT NULL
);

-- No references below here to allow sane population; added post-population

CREATE TABLE files (
       id SERIAL PRIMARY KEY,
       filename TEXT NOT NULL,
       size INT8 NOT NULL,
       md5sum TEXT NOT NULL,
       location INT4 NOT NULL, -- REFERENCES location
       last_used TIMESTAMP,
       unique (filename, location)
);

CREATE TABLE source (
        id SERIAL PRIMARY KEY,
        source TEXT NOT NULL,
        version TEXT NOT NULL,
        maintainer INT4 NOT NULL, -- REFERENCES maintainer
        changedby INT4 NOT NULL, -- REFERENCES maintainer
        file INT4 UNIQUE NOT NULL, -- REFERENCES files
	install_date TIMESTAMP NOT NULL,
	sig_fpr INT4 NOT NULL, -- REFERENCES fingerprint
	unique (source, version)
);

CREATE TABLE src_uploaders (
       id SERIAL PRIMARY KEY,
       source INT4 NOT NULL REFERENCES source,
       maintainer INT4 NOT NULL REFERENCES maintainer
);

CREATE TABLE dsc_files (
       id SERIAL PRIMARY KEY,
       source INT4 NOT NULL, -- REFERENCES source,
       file INT4 NOT NULL, -- RERENCES files
       unique (source, file)
);

CREATE TABLE binaries (
       id SERIAL PRIMARY KEY,
       package TEXT NOT NULL,
       version TEXT NOT NULL,
       maintainer INT4 NOT NULL, -- REFERENCES maintainer
       source INT4, -- REFERENCES source,
       architecture INT4 NOT NULL, -- REFERENCES architecture
       file INT4 UNIQUE NOT NULL, -- REFERENCES files,
       type TEXT NOT NULL,
-- joeyh@ doesn't want .udebs and .debs with the same name, which is why the unique () doesn't mention type
       sig_fpr INT4 NOT NULL, -- REFERENCES fingerprint
       unique (package, version, architecture)
);

CREATE TABLE suite (
       id SERIAL PRIMARY KEY,
       suite_name TEXT NOT NULL,
       version TEXT,
       origin TEXT,
       label TEXT,
       policy_engine TEXT,
       description TEXT
);

CREATE TABLE queue (
       id SERIAL PRIMARY KEY,
       queue_name TEXT NOT NULL
);

CREATE TABLE suite_architectures (
       suite INT4 NOT NULL, -- REFERENCES suite
       architecture INT4 NOT NULL, -- REFERENCES architecture
       unique (suite, architecture)
);

CREATE TABLE bin_associations (
       id SERIAL PRIMARY KEY,
       suite INT4 NOT NULL, -- REFERENCES suite
       bin INT4 NOT NULL, -- REFERENCES binaries
       unique (suite, bin)
);

CREATE TABLE src_associations (
       id SERIAL PRIMARY KEY,
       suite INT4 NOT NULL, -- REFERENCES suite
       source INT4 NOT NULL, -- REFERENCES source
       unique (suite, source)
);

CREATE TABLE section (
       id SERIAL PRIMARY KEY,
       section TEXT UNIQUE NOT NULL
);

CREATE TABLE priority (
       id SERIAL PRIMARY KEY,
       priority TEXT UNIQUE NOT NULL,
       level INT4 UNIQUE NOT NULL
);

CREATE TABLE override_type (
       id SERIAL PRIMARY KEY,
       type TEXT UNIQUE NOT NULL
);

CREATE TABLE override (
       package TEXT NOT NULL,
       suite INT4 NOT NULL, -- references suite
       component INT4 NOT NULL, -- references component
       priority INT4, -- references priority
       section INT4 NOT NULL, -- references section
       type INT4 NOT NULL, -- references override_type
       maintainer TEXT,
       unique (suite, component, package, type)
);

CREATE TABLE queue_build (
       suite INT4 NOT NULL, -- references suite
       queue INT4 NOT NULL, -- references queue
       filename TEXT NOT NULL,
       in_queue BOOLEAN NOT NULL,
       last_used TIMESTAMP
);

-- Critical indexes

CREATE INDEX bin_associations_bin ON bin_associations (bin);
CREATE INDEX src_associations_source ON src_associations (source);
CREATE INDEX source_maintainer ON source (maintainer);
CREATE INDEX binaries_maintainer ON binaries (maintainer);
CREATE INDEX binaries_fingerprint on binaries (sig_fpr);
CREATE INDEX source_fingerprint on source (sig_fpr);
CREATE INDEX dsc_files_file ON dsc_files (file);

-- Own function
CREATE FUNCTION space_concat(text, text) RETURNS text
    AS $_$select case
WHEN $2 is null or $2 = '' THEN $1
WHEN $1 is null or $1 = '' THEN $2
ELSE $1 || ' ' || $2
END$_$
    LANGUAGE sql;

CREATE AGGREGATE space_separated_list (
    BASETYPE = text,
    SFUNC = space_concat,
    STYPE = text,
    INITCOND = ''
);
