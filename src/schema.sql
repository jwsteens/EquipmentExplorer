-- Ship Cable and Equipment PDF Indexing Database Schema
-- Normalized design for efficient bidirectional lookups

-- Table for storing PDF documents
CREATE TABLE IF NOT EXISTS pdfs (
    pdf_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    document_description TEXT,
    drawing_number TEXT,
    supplier_code TEXT,
    supplier_name TEXT,
    file_size_bytes INTEGER,
    page_count INTEGER,
    is_searchable BOOLEAN DEFAULT 0,
    ocr_processed BOOLEAN DEFAULT 0,
    date_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_modified TIMESTAMP
);

-- Index for looking up PDFs by drawing number
CREATE INDEX IF NOT EXISTS idx_pdfs_drawing ON pdfs(drawing_number);

-- Index for looking up PDFs by supplier
CREATE INDEX IF NOT EXISTS idx_pdfs_supplier ON pdfs(supplier_name);

-- Table for all tags (both cables and equipment)
CREATE TABLE IF NOT EXISTS tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name TEXT NOT NULL UNIQUE,
    tag_type TEXT NOT NULL CHECK(tag_type IN ('cable', 'equipment')),
    description TEXT,
    room_tag TEXT,
    deck TEXT,
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Junction table for tag occurrences in PDFs
CREATE TABLE IF NOT EXISTS tag_occurrences (
    occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id INTEGER NOT NULL,
    pdf_id INTEGER NOT NULL,
    page_number INTEGER,
    confidence REAL DEFAULT 1.0,  -- For OCR results, can store confidence score
    date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
    FOREIGN KEY (pdf_id) REFERENCES pdfs(pdf_id) ON DELETE CASCADE,
    UNIQUE(tag_id, pdf_id, page_number)  -- Prevent duplicate entries
);

-- Table for cable connections (which equipment a cable connects)
-- This stores the FROM -> TO relationship for each cable
CREATE TABLE IF NOT EXISTS cable_connections (
    connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cable_tag_id INTEGER NOT NULL,
    start_equipment_tag_id INTEGER NOT NULL,
    dest_equipment_tag_id INTEGER NOT NULL,
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cable_tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
    FOREIGN KEY (start_equipment_tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
    FOREIGN KEY (dest_equipment_tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
    UNIQUE(cable_tag_id)  -- Each cable has one connection record
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(tag_name);
CREATE INDEX IF NOT EXISTS idx_tags_type ON tags(tag_type);
CREATE INDEX IF NOT EXISTS idx_tags_description ON tags(description);
CREATE INDEX IF NOT EXISTS idx_occurrences_tag ON tag_occurrences(tag_id);
CREATE INDEX IF NOT EXISTS idx_occurrences_pdf ON tag_occurrences(pdf_id);
CREATE INDEX IF NOT EXISTS idx_pdfs_path ON pdfs(relative_path);
CREATE INDEX IF NOT EXISTS idx_pdfs_searchable ON pdfs(is_searchable);
CREATE INDEX IF NOT EXISTS idx_cable_conn_cable ON cable_connections(cable_tag_id);
CREATE INDEX IF NOT EXISTS idx_cable_conn_start ON cable_connections(start_equipment_tag_id);
CREATE INDEX IF NOT EXISTS idx_cable_conn_dest ON cable_connections(dest_equipment_tag_id);

-- View for easy cable lookups
CREATE VIEW IF NOT EXISTS cable_pdf_view AS
SELECT 
    t.tag_name AS cable_tag,
    t.description,
    p.filename AS pdf_filename,
    p.relative_path AS pdf_path,
    o.page_number,
    o.confidence
FROM tags t
JOIN tag_occurrences o ON t.tag_id = o.tag_id
JOIN pdfs p ON o.pdf_id = p.pdf_id
WHERE t.tag_type = 'cable';

-- View for easy equipment lookups
CREATE VIEW IF NOT EXISTS equipment_pdf_view AS
SELECT 
    t.tag_name AS equipment_tag,
    t.description,
    t.room_tag,
    t.deck,
    p.filename AS pdf_filename,
    p.relative_path AS pdf_path,
    o.page_number,
    o.confidence
FROM tags t
JOIN tag_occurrences o ON t.tag_id = o.tag_id
JOIN pdfs p ON o.pdf_id = p.pdf_id
WHERE t.tag_type = 'equipment';

-- View for PDF contents (all tags found in a PDF)
CREATE VIEW IF NOT EXISTS pdf_contents_view AS
SELECT 
    p.filename AS pdf_filename,
    p.relative_path AS pdf_path,
    t.tag_type,
    t.tag_name,
    t.description,
    o.page_number
FROM pdfs p
JOIN tag_occurrences o ON p.pdf_id = o.pdf_id
JOIN tags t ON o.tag_id = t.tag_id
ORDER BY p.filename, t.tag_type, t.tag_name;

-- View for cable connections with full details
CREATE VIEW IF NOT EXISTS cable_connections_view AS
SELECT 
    c.tag_name AS cable_tag,
    c.description AS cable_description,
    s.tag_name AS start_equipment_tag,
    s.description AS start_equipment_description,
    s.room_tag AS start_room,
    s.deck AS start_deck,
    d.tag_name AS dest_equipment_tag,
    d.description AS dest_equipment_description,
    d.room_tag AS dest_room,
    d.deck AS dest_deck
FROM cable_connections cc
JOIN tags c ON cc.cable_tag_id = c.tag_id
JOIN tags s ON cc.start_equipment_tag_id = s.tag_id
JOIN tags d ON cc.dest_equipment_tag_id = d.tag_id;
