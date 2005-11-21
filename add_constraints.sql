-- Fix up after population of the database...

-- First of all readd the constraints (takes ~1:30 on auric)

ALTER TABLE files ADD CONSTRAINT files_location FOREIGN KEY (location) REFERENCES location(id) MATCH FULL;

ALTER TABLE source ADD CONSTRAINT source_maintainer FOREIGN KEY (maintainer) REFERENCES maintainer(id) MATCH FULL;
ALTER TABLE source ADD CONSTRAINT source_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;
ALTER TABLE source ADD CONSTRAINT source_sig_fpr FOREIGN KEY (sig_fpr) REFERENCES fingerprint(id) MATCH FULL;

ALTER TABLE dsc_files ADD CONSTRAINT dsc_files_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;
ALTER TABLE dsc_files ADD CONSTRAINT dsc_files_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;

ALTER TABLE binaries ADD CONSTRAINT binaries_maintainer FOREIGN KEY (maintainer) REFERENCES maintainer(id) MATCH FULL;
ALTER TABLE binaries ADD CONSTRAINT binaries_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;
ALTER TABLE binaries ADD CONSTRAINT binaries_architecture FOREIGN KEY (architecture) REFERENCES architecture(id) MATCH FULL;
ALTER TABLE binaries ADD CONSTRAINT binaries_file FOREIGN KEY (file) REFERENCES files(id) MATCH FULL;
ALTER TABLE binaries ADD CONSTRAINT binaries_sig_fpr FOREIGN KEY (sig_fpr) REFERENCES fingerprint(id) MATCH FULL;

ALTER TABLE suite_architectures ADD CONSTRAINT suite_architectures_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;
ALTER TABLE suite_architectures ADD CONSTRAINT suite_architectures_architecture FOREIGN KEY (architecture) REFERENCES architecture(id) MATCH FULL;

ALTER TABLE bin_associations ADD CONSTRAINT bin_associations_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;
ALTER TABLE bin_associations ADD CONSTRAINT bin_associations_bin FOREIGN KEY (bin) REFERENCES binaries(id) MATCH FULL;

ALTER TABLE src_associations ADD CONSTRAINT src_associations_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;
ALTER TABLE src_associations ADD CONSTRAINT src_associations_source FOREIGN KEY (source) REFERENCES source(id) MATCH FULL;

ALTER TABLE override ADD CONSTRAINT override_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;
ALTER TABLE override ADD CONSTRAINT override_component FOREIGN KEY (component) REFERENCES component(id) MATCH FULL;
ALTER TABLE override ADD CONSTRAINT override_priority FOREIGN KEY (priority) REFERENCES priority(id) MATCH FULL;
ALTER TABLE override ADD CONSTRAINT override_section FOREIGN KEY (section) REFERENCES section(id) MATCH FULL;
ALTER TABLE override ADD CONSTRAINT override_type FOREIGN KEY (type) REFERENCES override_type(id) MATCH FULL;

ALTER TABLE accepted_autobuild ADD CONSTRAINT accepted_autobuild_suite FOREIGN KEY (suite) REFERENCES suite(id) MATCH FULL;

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
CREATE FUNCTION section_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM section'
    LANGUAGE 'sql';
CREATE FUNCTION priority_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM priority'
    LANGUAGE 'sql';
CREATE FUNCTION override_type_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM override_type'
    LANGUAGE 'sql';
CREATE FUNCTION maintainer_id_max() RETURNS INT4
    AS 'SELECT max(id) FROM maintainer'
    LANGUAGE 'sql';

SELECT setval('files_id_seq', files_id_max());
SELECT setval('source_id_seq', source_id_max());
SELECT setval('src_associations_id_seq', src_associations_id_max());
SELECT setval('dsc_files_id_seq', dsc_files_id_max());
SELECT setval('binaries_id_seq', binaries_id_max());
SELECT setval('bin_associations_id_seq', bin_associations_id_max());
SELECT setval('section_id_seq', section_id_max());
SELECT setval('priority_id_seq', priority_id_max());
SELECT setval('override_type_id_seq', override_type_id_max());
SELECT setval('maintainer_id_seq', maintainer_id_max());

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
VACUUM section;
VACUUM priority;
VACUUM override_type;
VACUUM override;

-- FIXME: has to be a better way to do this
GRANT ALL ON architecture, architecture_id_seq, archive,
  archive_id_seq, bin_associations, bin_associations_id_seq, binaries,
  binaries_id_seq, component, component_id_seq, dsc_files,
  dsc_files_id_seq, files, files_id_seq, fingerprint,
  fingerprint_id_seq, location, location_id_seq, maintainer,
  maintainer_id_seq, override, override_type, override_type_id_seq,
  priority, priority_id_seq, section, section_id_seq, source,
  source_id_seq, src_associations, src_associations_id_seq, suite,
  suite_architectures, suite_id_seq, accepted_autobuild, uid,
  uid_id_seq TO GROUP ftpmaster;

-- Read only access to user 'nobody'
GRANT SELECT ON architecture, architecture_id_seq, archive,
  archive_id_seq, bin_associations, bin_associations_id_seq, binaries,
  binaries_id_seq, component, component_id_seq, dsc_files,
  dsc_files_id_seq, files, files_id_seq, fingerprint,
  fingerprint_id_seq, location, location_id_seq, maintainer,
  maintainer_id_seq, override, override_type, override_type_id_seq,
  priority, priority_id_seq, section, section_id_seq, source,
  source_id_seq, src_associations, src_associations_id_seq, suite,
  suite_architectures, suite_id_seq, accepted_autobuild, uid,
  uid_id_seq TO PUBLIC;
