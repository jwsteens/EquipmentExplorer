-- Table for equipment
CREATE TABLE IF NOT EXISTS equipment (
    equipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL UNIQUE,
    description TEXT,
    room_tag TEXT,
    deck TEXT,
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_equipment_tag ON equipment(tag);
CREATE INDEX IF NOT EXISTS idx_equipment_room ON equipment(room_tag);
CREATE INDEX IF NOT EXISTS idx_equipment_deck ON equipment(deck);



-- Table for cables
CREATE TABLE IF NOT EXISTS cables (
    cable_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL UNIQUE,
    type TEXT,
    start_equipment_id INTEGER,
    dest_equipment_id INTEGER,
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (start_equipment_id) REFERENCES equipment(equipment_id) ON DELETE SET NULL,
    FOREIGN KEY (dest_equipment_id) REFERENCES equipment(equipment_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_cables_tag ON cables(tag);
CREATE INDEX IF NOT EXISTS idx_cables_start ON cables(start_equipment_id);
CREATE INDEX IF NOT EXISTS idx_cables_dest ON cables(dest_equipment_id);



-- Table for storing PDF documents
CREATE TABLE IF NOT EXISTS documents (
    pdf_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    document_description TEXT,
    supplier_code TEXT,
    supplier_name TEXT,
    supergrandparent TEXT,
    superparent TEXT,
    revision TEXT,
    status TEXT,
    file_size_bytes INTEGER,
    page_count INTEGER,
    content_hash TEXT,
    to_be_indexed BOOLEAN DEFAULT 0,
    date_indexed TIMESTAMP,
    date_modified TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_supplier ON documents(supplier_name);
CREATE INDEX IF NOT EXISTS idx_documents_supergrandparent ON documents(supergrandparent);
CREATE INDEX IF NOT EXISTS idx_documents_superparent ON documents(superparent);



-- Table for equipment occurrences in PDFs
CREATE TABLE IF NOT EXISTS equipment_occurrences (
    occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id INTEGER NOT NULL REFERENCES equipment(equipment_id) ON DELETE CASCADE,
    pdf_id INTEGER NOT NULL REFERENCES documents(pdf_id) ON DELETE CASCADE,
    page_number INTEGER,
    UNIQUE(equipment_id, pdf_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_equipment_occurrences_equipment ON equipment_occurrences(equipment_id);
CREATE INDEX IF NOT EXISTS idx_equipment_occurrences_pdf ON equipment_occurrences(pdf_id);



-- Table for cable occurrences in PDFs
CREATE TABLE IF NOT EXISTS cable_occurrences (
    occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cable_id INTEGER NOT NULL REFERENCES cables(cable_id) ON DELETE CASCADE,
    pdf_id INTEGER NOT NULL REFERENCES documents(pdf_id) ON DELETE CASCADE,
    page_number INTEGER,
    confidence REAL DEFAULT 1.0,
    UNIQUE(cable_id, pdf_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_cable_occurrences_cable ON cable_occurrences(cable_id);
CREATE INDEX IF NOT EXISTS idx_cable_occurrences_pdf ON cable_occurrences(pdf_id);



-- View for cable details with connected equipment
CREATE VIEW IF NOT EXISTS cable_connections_view AS
SELECT
    c.cable_id,
    c.tag AS cable_tag,
    c.type AS cable_type,
    s.tag AS start_equipment_tag,
    s.description AS start_equipment_description,
    s.room_tag AS start_room,
    s.deck AS start_deck,
    d.tag AS dest_equipment_tag,
    d.description AS dest_equipment_description,
    d.room_tag AS dest_room,
    d.deck AS dest_deck
FROM cables c
LEFT JOIN equipment s ON c.start_equipment_id = s.equipment_id
LEFT JOIN equipment d ON c.dest_equipment_id = d.equipment_id;



-- View for cable occurrences with document details
CREATE VIEW IF NOT EXISTS cable_documents_view AS
SELECT
    c.tag AS cable_tag,
    c.type AS cable_type,
    d.filename AS pdf_filename,
    d.relative_path AS pdf_path,
    d.document_description,
    d.supplier_name,
    o.page_number,
    o.confidence
FROM cable_occurrences o
JOIN cables c ON o.cable_id = c.cable_id
JOIN documents d ON o.pdf_id = d.pdf_id;



-- View for equipment occurrences with document details
CREATE VIEW IF NOT EXISTS equipment_documents_view AS
SELECT
    e.tag AS equipment_tag,
    e.description,
    e.room_tag,
    e.deck,
    d.filename AS pdf_filename,
    d.relative_path AS pdf_path,
    d.document_description,
    d.supplier_name,
    o.page_number
FROM equipment_occurrences o
JOIN equipment e ON o.equipment_id = e.equipment_id
JOIN documents d ON o.pdf_id = d.pdf_id;



-- View for document contents (all cables and equipment found in a document)
CREATE VIEW IF NOT EXISTS document_contents_view AS
SELECT
    d.filename AS pdf_filename,
    d.relative_path AS pdf_path,
    'cable' AS tag_type,
    c.tag AS tag,
    NULL AS description,
    o.page_number
FROM cable_occurrences o
JOIN documents d ON o.pdf_id = d.pdf_id
JOIN cables c ON o.cable_id = c.cable_id

UNION ALL

SELECT
    d.filename AS pdf_filename,
    d.relative_path AS pdf_path,
    'equipment' AS tag_type,
    e.tag AS tag,
    e.description,
    o.page_number
FROM equipment_occurrences o
JOIN documents d ON o.pdf_id = d.pdf_id
JOIN equipment e ON o.equipment_id = e.equipment_id

ORDER BY pdf_filename, tag_type, tag;
