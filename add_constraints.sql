-- Fix up after population off the database...

-- First of all readd the constraints (takes ~1:30 on auric)

ALTER TABLE files ADD CONSTRAINT files_location FOREIGN KEY (location) REFERENCES location(id) MATCH FULL;

ALTER TABLE source ADD CONSTRAINT source_maintainer FOREIGN KEY (maintainer) REFERENCES maintainer(id) MATCH FULL;
ALTER TABLE source ADD CONSTRAINT source_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;

ALTER TABLE dsc_files ADD CONSTRAINT dsc_files_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;
ALTER TABLE dsc_files ADD CONSTRAINT dsc_files_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;

ALTER TABLE binaries ADD CONSTRAINT binaries_maintainer FOREIGN KEY (maintainer) REFERENCES maintainer(id) MATCH FULL;
ALTER TABLE binaries ADD CONSTRAINT binaries_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;
ALTER TABLE binaries ADD CONSTRAINT binaries_architecture FOREIGN KEY (architecture) REFERENCES architecture(id) MATCH FULL;
ALTER TABLE binaries ADD CONSTRAINT binaries_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;

ALTER TABLE suite_architectures ADD CONSTRAINT suite_architectures_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;
ALTER TABLE suite_architectures ADD CONSTRAINT suite_architectures_architecture FOREIGN KEY (architecture) REFERENCES architecture(id) MATCH FULL;

ALTER TABLE bin_associations ADD CONSTRAINT bin_associations_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;
ALTER TABLE bin_associations ADD CONSTRAINT bin_associations_bin FOREIGN KEY (bin) REFERENCES binaries(id) MATCH FULL;
  
ALTER TABLE src_associations ADD CONSTRAINT src_associations_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;
ALTER TABLE src_associations ADD CONSTRAINT src_associations_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;

-- Then correct all the id SERIAL PRIMARY KEY columns...

CREATE FUNCTION files_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM files' 
    LANGUAGE 'sql';
CREATE FUNCTION source_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM source' 
    LANGUAGE 'sql';
CREATE FUNCTION src_associations_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM src_associations' 
    LANGUAGE 'sql';
CREATE FUNCTION dsc_files_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM dsc_files' 
    LANGUAGE 'sql';
CREATE FUNCTION binaries_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM binaries' 
    LANGUAGE 'sql';
CREATE FUNCTION bin_associations_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM bin_associations' 
    LANGUAGE 'sql';

SELECT setval('files_id_seq', files_id_max());
SELECT setval('source_id_seq', source_id_max());
SELECT setval('src_associations_id_seq', src_associations_id_max());
SELECT setval('dsc_files_id_seq', dsc_files_id_max());
SELECT setval('binaries_id_seq', binaries_id_max());
SELECT setval('bin_associations_id_seq', bin_associations_id_max());

-- Vacuum the tables for efficency

VACUUM archive;
VACUUM component;
VACUUM architecture;
VACUUM maintainer;
VACUUM location;
VACUUM files;
VACUUM source;
VACUUM dsc_files;
VACUUM binaries;
VACUUM suite;
VACUUM suite_architectures;
VACUUM bin_associations;
VACUUM src_associations;

-- FIXME: has to be a better way to do this
GRANT ALL ON 
  architecture, architecture_id_seq, archive, archive_id_seq,
  bin_associations, bin_associations_id_seq, binaries,
  binaries_id_seq, component, component_id_seq, dsc_files,
  dsc_files_id_seq, files, files_id_seq, location, location_id_seq,
  maintainer, maintainer_id_seq, source, source_id_seq,
  src_associations, src_associations_id_seq, suite,
  suite_architectures, suite_id_seq
     TO troup;

-- Give write privileges to the associations tables for AJ for the purposes of `testing'
GRANT ALL ON 
  binaries, binaries_id_seq, 
  bin_associations, bin_associations_id_seq,
  source, source_id_seq, 
  src_associations, src_associations_id_seq,
  suite, suite_id_seq 
     TO ajt;

-- RO access to AJ for all other tables
GRANT SELECT ON 
  architecture, archive, binaries, component,
  dsc_files, files, location, maintainer, source, suite, suite_architectures
     TO ajt;

-- Read only access to user 'nobody'
GRANT SELECT ON 
  architecture, architecture_id_seq, archive, archive_id_seq,
  bin_associations, bin_associations_id_seq, binaries,
  binaries_id_seq, component, component_id_seq, dsc_files,
  dsc_files_id_seq, files, files_id_seq, location, location_id_seq,
  maintainer, maintainer_id_seq, source, source_id_seq,
  src_associations, src_associations_id_seq, suite,
  suite_architectures, suite_id_seq
     TO PUBLIC;
