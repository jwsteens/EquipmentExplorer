/**
 * Equipment Explorer - Search Page JavaScript
 */

// State
let currentFilter = 'all';
let searchTimeout = null;
let selectedAutocompleteIndex = -1;
let autocompleteResults = [];

// DOM Elements
const searchInput = document.getElementById('searchInput');
const autocompleteDropdown = document.getElementById('autocompleteDropdown');
const emptyState = document.getElementById('emptyState');
const loadingState = document.getElementById('loadingState');
const resultsContent = document.getElementById('resultsContent');
const filterButtons = document.querySelectorAll('.filter-btn');
const partialSearchCheckbox = document.getElementById('partialSearch');

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    // Check for query parameter
    const urlParams = new URLSearchParams(window.location.search);
    const queryParam = urlParams.get('q');
    const typeParam = urlParams.get('type');
    
    // Set filter if specified
    if (typeParam && ['cable', 'equipment', 'pdf'].includes(typeParam)) {
        currentFilter = typeParam;
        filterButtons.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.type === typeParam);
        });
    }
    
    if (queryParam) {
        searchInput.value = queryParam;
        performSearch(queryParam);
    }
    
    // Filter buttons
    filterButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            filterButtons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentFilter = this.dataset.type;
            
            if (searchInput.value.trim()) {
                performSearch(searchInput.value.trim());
            }
        });
    });
    
    // Example searches
    document.querySelectorAll('.example-search').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            searchInput.value = this.textContent;
            performSearch(this.textContent);
        });
    });
    
    // Search input handlers
    searchInput.addEventListener('input', handleInput);
    searchInput.addEventListener('keydown', handleKeydown);
    searchInput.addEventListener('focus', () => {
        if (autocompleteResults.length > 0) {
            autocompleteDropdown.classList.add('show');
        }
    });
    
    // Close autocomplete on outside click
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.search-box')) {
            autocompleteDropdown.classList.remove('show');
        }
    });
});

function handleInput(e) {
    const query = e.target.value.trim();
    
    if (searchTimeout) {
        clearTimeout(searchTimeout);
    }
    
    if (query.length < 2) {
        autocompleteDropdown.classList.remove('show');
        autocompleteResults = [];
        return;
    }
    
    searchTimeout = setTimeout(() => {
        fetchAutocomplete(query);
    }, 150);
}

function handleKeydown(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        
        if (selectedAutocompleteIndex >= 0 && autocompleteResults[selectedAutocompleteIndex]) {
            const item = autocompleteResults[selectedAutocompleteIndex];
            searchInput.value = item.tag_name;
            autocompleteDropdown.classList.remove('show');
            performSearch(item.tag_name);
        } else if (searchInput.value.trim()) {
            autocompleteDropdown.classList.remove('show');
            performSearch(searchInput.value.trim());
        }
        
        selectedAutocompleteIndex = -1;
    } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (autocompleteResults.length > 0) {
            selectedAutocompleteIndex = Math.min(selectedAutocompleteIndex + 1, autocompleteResults.length - 1);
            updateAutocompleteSelection();
        }
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (autocompleteResults.length > 0) {
            selectedAutocompleteIndex = Math.max(selectedAutocompleteIndex - 1, -1);
            updateAutocompleteSelection();
        }
    } else if (e.key === 'Escape') {
        autocompleteDropdown.classList.remove('show');
        selectedAutocompleteIndex = -1;
    }
}

async function fetchAutocomplete(query) {
    try {
        const typeParam = currentFilter !== 'all' ? `&type=${currentFilter}` : '';
        const url = `/api/search/autocomplete?q=${encodeURIComponent(query)}${typeParam}`;
        const response = await fetch(url);
        const data = await response.json();
        
        autocompleteResults = data;
        selectedAutocompleteIndex = -1;
        
        if (data.length > 0) {
            renderAutocomplete(data);
            autocompleteDropdown.classList.add('show');
        } else {
            autocompleteDropdown.classList.remove('show');
        }
    } catch (error) {
        console.error('Autocomplete error:', error);
    }
}

function renderAutocomplete(results) {
    autocompleteDropdown.innerHTML = results.map((item, index) => {
        if (item.tag_type === 'pdf') {
            // PDF autocomplete item
            const desc = item.description ? ` - ${item.description.substring(0, 40)}${item.description.length > 40 ? '...' : ''}` : '';
            const supplier = item.supplier_code || item.supplier_name || '';
            return `
                <div class="autocomplete-item" data-index="${index}" onclick="selectAutocompleteItem(${index})">
                    <div style="display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0;">
                        <span class="autocomplete-item-name" style="font-size: 0.9rem;">${escapeHtml(item.tag_name)}</span>
                        ${desc ? `<span class="text-muted" style="font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(desc)}</span>` : ''}
                    </div>
                    <span class="autocomplete-item-meta">
                        <span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #ef4444;">PDF</span>
                        ${supplier ? `<span class="text-muted" style="font-size: 0.75rem;">${escapeHtml(supplier)}</span>` : ''}
                    </span>
                </div>
            `;
        } else {
            // Tag autocomplete item (cable/equipment)
            const desc = item.description ? item.description.substring(0, 50) + (item.description.length > 50 ? '...' : '') : '';
            return `
                <div class="autocomplete-item" data-index="${index}" onclick="selectAutocompleteItem(${index})">
                    <div style="display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0;">
                        <span class="autocomplete-item-name">${escapeHtml(item.tag_name)}</span>
                        ${desc ? `<span class="text-muted" style="font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(desc)}</span>` : ''}
                    </div>
                    <span class="autocomplete-item-meta">
                        <span class="badge ${item.tag_type === 'cable' ? 'badge-cable' : 'badge-equipment'}">
                            ${item.tag_type}
                        </span>
                        ${item.pdf_count > 0 ? `<span class="badge badge-muted">${item.pdf_count} PDFs</span>` : ''}
                    </span>
                </div>
            `;
        }
    }).join('');
}

function updateAutocompleteSelection() {
    const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
    items.forEach((item, index) => {
        item.classList.toggle('selected', index === selectedAutocompleteIndex);
    });
}

function selectAutocompleteItem(index) {
    const item = autocompleteResults[index];
    if (item) {
        searchInput.value = item.tag_name;
        autocompleteDropdown.classList.remove('show');
        performSearch(item.tag_name);
    }
}

async function performSearch(query) {
    // Update URL
    const url = new URL(window.location);
    url.searchParams.set('q', query);
    if (currentFilter !== 'all') {
        url.searchParams.set('type', currentFilter);
    } else {
        url.searchParams.delete('type');
    }
    window.history.pushState({}, '', url);
    
    // Add to recent searches
    addRecentSearch(query);
    
    // Show loading
    emptyState.classList.add('hidden');
    resultsContent.classList.add('hidden');
    loadingState.classList.remove('hidden');
    
    try {
        const isPartial = partialSearchCheckbox.checked;
        
        // PDF search
        if (currentFilter === 'pdf') {
            const response = await fetch(`/api/search/pdf/${encodeURIComponent(query)}`);
            const data = await response.json();
            renderPdfSearchResults(data);
        } else if (isPartial) {
            // Partial search
            const typeParam = currentFilter !== 'all' ? `&type=${currentFilter}` : '';
            const response = await fetch(`/api/search/partial/${encodeURIComponent(query)}?${typeParam}`);
            const data = await response.json();
            renderPartialResults(data);
        } else {
            // Exact search
            const response = await fetch(`/api/search/tag/${encodeURIComponent(query)}`);
            const data = await response.json();
            renderExactResults(data);
        }
    } catch (error) {
        console.error('Search error:', error);
        resultsContent.innerHTML = `
            <div class="result-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="color: var(--accent-danger)">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="15" y1="9" x2="9" y2="15"/>
                    <line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                <p>Error performing search</p>
                <p class="text-muted">${escapeHtml(error.message)}</p>
            </div>
        `;
    }
    
    loadingState.classList.add('hidden');
    resultsContent.classList.remove('hidden');
}

function renderExactResults(data) {
    if (!data.found) {
        // Try partial search as suggestion
        resultsContent.innerHTML = `
            <div class="result-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="11" cy="11" r="8"/>
                    <path d="m21 21-4.35-4.35"/>
                </svg>
                <p>No exact match found for "${escapeHtml(data.tag_name)}"</p>
                <p class="text-muted">Try enabling "Partial match" or check your spelling</p>
            </div>
        `;
        return;
    }
    
    const tagInfo = data.tag_info;
    const pdfs = data.pdfs;
    const connection = data.connection;
    const connectedCables = data.connected_cables;
    const equipmentLocation = data.equipment_location;
    
    let html = '';
    
    // Determine pin button based on tag type
    const isCable = tagInfo.tag_type === 'cable';
    const pinButton = isCable 
        ? createCablePinButton(tagInfo.tag_name, tagInfo.description || '', connection?.start_equipment_tag || '', connection?.dest_equipment_tag || '')
        : createEquipmentPinButton(tagInfo.tag_name, tagInfo.description || '', equipmentLocation?.room_tag || '');
    
    // Tag info card
    html += `
        <div class="tag-info-card">
            <div class="tag-info-header">
                <div class="tag-info-icon ${tagInfo.tag_type}">
                    ${tagInfo.tag_type === 'cable' ? `
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M4 9h16"/>
                            <path d="M4 15h16"/>
                            <circle cx="8" cy="9" r="1" fill="currentColor"/>
                            <circle cx="16" cy="15" r="1" fill="currentColor"/>
                        </svg>
                    ` : `
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="4" y="4" width="16" height="16" rx="2"/>
                            <circle cx="12" cy="12" r="4"/>
                        </svg>
                    `}
                </div>
                <div class="tag-info-details">
                    <div style="display: flex; align-items: center; gap: var(--space-sm); flex-wrap: wrap;">
                        <h2 style="margin: 0;">${escapeHtml(tagInfo.tag_name)}</h2>
                        <span class="tag-type ${tagInfo.tag_type}">${tagInfo.tag_type}</span>
                        ${pinButton}
                    </div>
                </div>
            </div>
            <div class="tag-info-body">
    `;
    
    if (tagInfo.description) {
        html += `<p class="tag-description">${escapeHtml(tagInfo.description)}</p>`;
    }
    
    // Equipment location info
    if (equipmentLocation && (equipmentLocation.room_tag || equipmentLocation.deck)) {
        html += renderEquipmentLocation(equipmentLocation);
    }
    
    // Connection diagram for cables
    if (connection) {
        html += renderConnectionDiagram(connection);
    }
    
    // Connected cables for equipment
    if (connectedCables && connectedCables.length > 0) {
        html += renderConnectedCables(connectedCables, tagInfo.tag_name);
    }
    
    html += `
            </div>
        </div>
    `;
    
    // PDF results
    if (pdfs && pdfs.length > 0) {
        html += `
            <div class="pdf-results">
                <div class="pdf-results-header">
                    <h3 class="pdf-results-title">Found in Documents</h3>
                    <span class="pdf-results-count">${pdfs.length} document${pdfs.length !== 1 ? 's' : ''}</span>
                </div>
                <div class="pdf-list">
        `;
        
        pdfs.forEach(pdf => {
            html += renderPdfCard(pdf, tagInfo.tag_name);
        });
        
        html += `
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="pdf-results">
                <div class="result-empty" style="padding: var(--space-lg);">
                    <p class="text-muted">No documents found containing this tag</p>
                </div>
            </div>
        `;
    }
    
    resultsContent.innerHTML = html;
}

function renderEquipmentLocation(location) {
    let locationParts = [];
    
    if (location.room_tag) {
        const roomDisplay = location.room_description 
            ? `${location.room_tag} (${location.room_description})`
            : location.room_tag;
        locationParts.push(`<span>📍 <strong>Room:</strong> ${escapeHtml(String(location.room_tag))}</span>`);
        if (location.room_description) {
            locationParts.push(`<span class="text-muted" style="margin-left: var(--space-md);">${escapeHtml(location.room_description)}</span>`);
        }
    }
    
    if (location.deck) {
        locationParts.push(`<span>🚢 <strong>Deck:</strong> ${escapeHtml(location.deck)}</span>`);
    }
    
    if (locationParts.length === 0) return '';
    
    return `
        <div class="equipment-location" style="background: var(--bg-tertiary); border-radius: var(--radius-md); padding: var(--space-md); margin-bottom: var(--space-lg);">
            <div class="connection-title" style="margin-bottom: var(--space-sm);">Location</div>
            <div style="display: flex; flex-direction: column; gap: var(--space-xs);">
                ${locationParts.join('')}
            </div>
        </div>
    `;
}

function renderConnectionDiagram(conn) {
    const startRoom = conn.start_room || '';
    const startRoomDesc = conn.start_room_description ? ` (${conn.start_room_description})` : '';
    const destRoom = conn.dest_room || '';
    const destRoomDesc = conn.dest_room_description ? ` (${conn.dest_room_description})` : '';
    
    return `
        <div class="connection-diagram">
            <div class="connection-title">Cable Connection</div>
            <div class="connection-flow">
                <div class="connection-endpoint from">
                    <div class="endpoint-label from">FROM</div>
                    <div class="endpoint-tag" onclick="searchTag('${escapeHtml(conn.start_equipment_tag)}')">${escapeHtml(conn.start_equipment_tag)}</div>
                    ${conn.start_equipment_description ? `<div class="endpoint-description">${escapeHtml(conn.start_equipment_description)}</div>` : ''}
                    <div class="endpoint-location">
                        ${startRoom ? `<span>📍 ${escapeHtml(startRoom)}${escapeHtml(startRoomDesc)}</span>` : ''}
                        ${conn.start_deck ? `<span>🚢 ${escapeHtml(conn.start_deck)}</span>` : ''}
                    </div>
                </div>
                
                <div class="connection-arrow">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="5" y1="12" x2="19" y2="12"/>
                        <polyline points="12,5 19,12 12,19"/>
                    </svg>
                </div>
                
                <div class="connection-endpoint to">
                    <div class="endpoint-label to">TO</div>
                    <div class="endpoint-tag" onclick="searchTag('${escapeHtml(conn.dest_equipment_tag)}')">${escapeHtml(conn.dest_equipment_tag)}</div>
                    ${conn.dest_equipment_description ? `<div class="endpoint-description">${escapeHtml(conn.dest_equipment_description)}</div>` : ''}
                    <div class="endpoint-location">
                        ${destRoom ? `<span>📍 ${escapeHtml(destRoom)}${escapeHtml(destRoomDesc)}</span>` : ''}
                        ${conn.dest_deck ? `<span>🚢 ${escapeHtml(conn.dest_deck)}</span>` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderConnectedCables(cables, equipmentTag) {
    const displayCount = 15;
    const showAll = cables.length <= displayCount;
    
    let html = `
        <div class="connected-cables">
            <div class="connected-cables-title">Connected Cables (${cables.length})</div>
            <div class="cables-list" id="cablesList">
    `;
    
    cables.slice(0, showAll ? cables.length : displayCount).forEach(cable => {
        const isFrom = cable.connection_direction === 'from';
        const otherEquipment = isFrom ? cable.dest_equipment_tag : cable.start_equipment_tag;
        const otherDesc = isFrom ? cable.dest_equipment_description : cable.start_equipment_description;
        
        // Add pin button for each cable in the list
        const cablePinBtn = createCablePinButton(cable.cable_tag, '', cable.start_equipment_tag || '', cable.dest_equipment_tag || '');
        
        html += `
            <div class="cable-item">
                <span class="cable-item-tag" onclick="searchTag('${escapeHtml(cable.cable_tag)}')">${escapeHtml(cable.cable_tag)}</span>
                <span class="cable-item-direction ${isFrom ? 'from' : 'to'}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
                        <line x1="5" y1="12" x2="19" y2="12"/>
                        <polyline points="12,5 19,12 12,19"/>
                    </svg>
                    ${isFrom ? 'to' : 'from'}
                </span>
                <span class="cable-item-equipment">
                    <a href="#" onclick="event.preventDefault(); searchTag('${escapeHtml(otherEquipment)}')" style="color: var(--accent-equipment)">${escapeHtml(otherEquipment)}</a>
                    ${otherDesc ? `<span class="text-muted"> - ${escapeHtml(otherDesc)}</span>` : ''}
                </span>
                ${cablePinBtn}
            </div>
        `;
    });
    
    html += '</div>';
    
    if (!showAll) {
        html += `
            <button class="btn btn-ghost btn-sm mt-md" onclick="showAllCables()">
                Show all ${cables.length} cables
            </button>
        `;
    }
    
    html += '</div>';
    
    // Store full list for "show all"
    window._allConnectedCables = cables;
    window._equipmentTag = equipmentTag;
    
    return html;
}

function showAllCables() {
    const cables = window._allConnectedCables;
    if (!cables) return;
    
    const list = document.getElementById('cablesList');
    list.innerHTML = '';
    
    cables.forEach(cable => {
        const isFrom = cable.connection_direction === 'from';
        const otherEquipment = isFrom ? cable.dest_equipment_tag : cable.start_equipment_tag;
        const otherDesc = isFrom ? cable.dest_equipment_description : cable.start_equipment_description;
        
        // Add pin button for each cable in the list
        const cablePinBtn = createCablePinButton(cable.cable_tag, '', cable.start_equipment_tag || '', cable.dest_equipment_tag || '');
        
        list.innerHTML += `
            <div class="cable-item">
                <span class="cable-item-tag" onclick="searchTag('${escapeHtml(cable.cable_tag)}')">${escapeHtml(cable.cable_tag)}</span>
                <span class="cable-item-direction ${isFrom ? 'from' : 'to'}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
                        <line x1="5" y1="12" x2="19" y2="12"/>
                        <polyline points="12,5 19,12 12,19"/>
                    </svg>
                    ${isFrom ? 'to' : 'from'}
                </span>
                <span class="cable-item-equipment">
                    <a href="#" onclick="event.preventDefault(); searchTag('${escapeHtml(otherEquipment)}')" style="color: var(--accent-equipment)">${escapeHtml(otherEquipment)}</a>
                    ${otherDesc ? `<span class="text-muted"> - ${escapeHtml(otherDesc)}</span>` : ''}
                </span>
                ${cablePinBtn}
            </div>
        `;
    });
}

function renderPdfCard(pdf, searchTag) {
    const title = pdf.document_description || pdf.filename;
    const pdfUrl = `/pdf/${encodeURIComponent(pdf.relative_path)}#search=${encodeURIComponent(searchTag)}`;
    
    let pagesHtml = '';
    if (pdf.pages && pdf.pages.length > 0) {
        pagesHtml = `
            <div class="pdf-pages">
                <span class="text-muted" style="font-size: 0.75rem; margin-right: var(--space-xs);">Pages:</span>
                ${pdf.pages.slice(0, 10).map(p => `<span class="page-badge">${p}</span>`).join('')}
                ${pdf.pages.length > 10 ? `<span class="page-badge">+${pdf.pages.length - 10}</span>` : ''}
            </div>
        `;
    }
    
    let supplierHtml = '';
    if (pdf.supplier_code || pdf.supplier_name) {
        const parts = [];
        if (pdf.supplier_code) {
            parts.push(`<span class="mono" style="font-size: 0.8rem;">${escapeHtml(pdf.supplier_code)}</span>`);
        }
        if (pdf.supplier_name) {
            parts.push(`<span class="text-muted">${escapeHtml(pdf.supplier_name)}</span>`);
        }
        supplierHtml = `
            <div class="pdf-supplier" style="font-size: 0.85rem; margin-bottom: var(--space-sm); display: flex; gap: var(--space-sm); align-items: center;">
                <span style="color: var(--text-muted);">📋</span>
                ${parts.join(' · ')}
            </div>
        `;
    }
    
    return `
        <div class="pdf-card">
            <div class="pdf-card-header">
                <div class="pdf-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14,2 14,8 20,8"/>
                    </svg>
                </div>
                <div class="pdf-info">
                    <div class="pdf-title">${escapeHtml(title)}</div>
                    <div class="pdf-filename">${escapeHtml(pdf.filename)}</div>
                </div>
            </div>
            ${supplierHtml}
            ${pagesHtml}
            <div class="pdf-actions">
                <a href="${pdfUrl}" target="_blank" class="btn btn-primary btn-sm">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15,3 21,3 21,9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                    Open PDF
                </a>
                <button class="btn btn-secondary btn-sm" onclick="copyPdfLink('${pdfUrl}')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
                        <rect x="9" y="9" width="13" height="13" rx="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                    Copy Link
                </button>
                <button class="btn btn-ghost btn-sm" onclick="searchPdf('${escapeHtml(pdf.filename)}')" title="View all tags in this PDF">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14,2 14,8 20,8"/>
                        <line x1="16" y1="13" x2="8" y2="13"/>
                        <line x1="16" y1="17" x2="8" y2="17"/>
                    </svg>
                    Contents
                </button>
                ${createPinButton(pdf.filename, title, pdf.relative_path)}
            </div>
        </div>
    `;
}

function renderPartialResults(data) {
    if (data.results.length === 0) {
        resultsContent.innerHTML = `
            <div class="result-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="11" cy="11" r="8"/>
                    <path d="m21 21-4.35-4.35"/>
                </svg>
                <p>No matches found for "${escapeHtml(data.query)}"</p>
                <p class="text-muted">Try a different search term</p>
            </div>
        `;
        return;
    }
    
    let html = `
        <div class="partial-results-header">
            <h3>Found ${data.results.length} matches for "${escapeHtml(data.query)}"</h3>
        </div>
        <div class="partial-results-list">
    `;
    
    data.results.forEach(result => {
        const isCable = result.tag_type === 'cable';
        const pinButton = isCable 
            ? createCablePinButton(result.tag_name, result.description || '', '', '')
            : createEquipmentPinButton(result.tag_name, result.description || '', result.room_tag || '');
        
        html += `
            <div class="partial-result-item" onclick="searchTag('${escapeHtml(result.tag_name)}')">
                <div class="partial-result-icon ${result.tag_type}">
                    ${result.tag_type === 'cable' ? `
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M4 9h16"/>
                            <path d="M4 15h16"/>
                        </svg>
                    ` : `
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="4" y="4" width="16" height="16" rx="2"/>
                            <circle cx="12" cy="12" r="4"/>
                        </svg>
                    `}
                </div>
                <div class="partial-result-info">
                    <div class="partial-result-name">${escapeHtml(result.tag_name)}</div>
                    ${result.description ? `<div class="partial-result-desc">${escapeHtml(result.description)}</div>` : ''}
                </div>
                <div class="partial-result-meta">
                    <span class="badge ${result.tag_type === 'cable' ? 'badge-cable' : 'badge-equipment'}">${result.tag_type}</span>
                    ${result.pdf_count > 0 ? `<span class="badge badge-muted">${result.pdf_count} PDFs</span>` : ''}
                    ${pinButton}
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    resultsContent.innerHTML = html;
}

function searchTag(tagName) {
    searchInput.value = tagName;
    currentFilter = 'all';
    filterButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.type === 'all');
    });
    performSearch(tagName);
}

function searchPdf(filename) {
    searchInput.value = filename;
    currentFilter = 'pdf';
    filterButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.type === 'pdf');
    });
    performSearch(filename);
}

function renderPdfSearchResults(data) {
    if (!data.found) {
        resultsContent.innerHTML = `
            <div class="result-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14,2 14,8 20,8"/>
                </svg>
                <p>No document found for "${escapeHtml(data.query || data.filename)}"</p>
                <p class="text-muted">Try searching for a different filename or drawing number</p>
            </div>
        `;
        return;
    }
    
    const pdf = data.pdf;
    const cables = data.cables || [];
    const equipment = data.equipment || [];
    const pdfUrl = `/pdf/${encodeURIComponent(pdf.relative_path)}`;
    
    let html = `
        <div class="tag-info-card">
            <div class="tag-info-header">
                <div class="tag-info-icon pdf">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14,2 14,8 20,8"/>
                    </svg>
                </div>
                <div class="tag-info-details">
                    <h2>${escapeHtml(pdf.document_description || pdf.filename)}</h2>
                    <div style="display: flex; gap: var(--space-sm); align-items: center; flex-wrap: wrap;">
                        <span class="mono text-muted" style="font-size: 0.9rem;">${escapeHtml(pdf.filename)}</span>
                        ${pdf.is_searchable ? '<span class="badge badge-success">Indexed</span>' : 
                          pdf.ocr_processed ? '<span class="badge badge-warning">OCR Done</span>' : 
                          '<span class="badge badge-muted">Not Indexed</span>'}
                    </div>
                </div>
            </div>
            <div class="tag-info-body">
    `;
    
    // PDF metadata
    html += `<div class="pdf-metadata" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-md); margin-bottom: var(--space-lg);">`;
    
    if (pdf.supplier_code || pdf.supplier_name) {
        html += `
            <div>
                <div class="text-muted" style="font-size: 0.75rem; text-transform: uppercase; margin-bottom: 4px;">Supplier</div>
                <div>
                    ${pdf.supplier_code ? `<span class="mono">${escapeHtml(pdf.supplier_code)}</span>` : ''}
                    ${pdf.supplier_name ? `<span class="text-secondary"> · ${escapeHtml(pdf.supplier_name)}</span>` : ''}
                </div>
            </div>
        `;
    }
    
    if (pdf.category) {
        html += `
            <div>
                <div class="text-muted" style="font-size: 0.75rem; text-transform: uppercase; margin-bottom: 4px;">Category</div>
                <div>${escapeHtml(pdf.category)}${pdf.subcategory ? ` / ${escapeHtml(pdf.subcategory)}` : ''}</div>
            </div>
        `;
    }
    
    if (pdf.page_count) {
        html += `
            <div>
                <div class="text-muted" style="font-size: 0.75rem; text-transform: uppercase; margin-bottom: 4px;">Pages</div>
                <div class="mono">${pdf.page_count}</div>
            </div>
        `;
    }
    
    html += `
            <div>
                <div class="text-muted" style="font-size: 0.75rem; text-transform: uppercase; margin-bottom: 4px;">Status</div>
                <div>
                    ${pdf.is_searchable ? '<span class="badge badge-success">Indexed</span>' : 
                      pdf.ocr_processed ? '<span class="badge badge-warning">OCR Done</span>' : 
                      '<span class="badge badge-muted">Not Indexed</span>'}
                </div>
            </div>
        </div>
    `;
    
    // Action buttons
    html += `
        <div style="margin-bottom: var(--space-lg); display: flex; gap: var(--space-sm); flex-wrap: wrap;">
            <a href="${pdfUrl}" target="_blank" class="btn btn-primary">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                    <polyline points="15,3 21,3 21,9"/>
                    <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                Open PDF
            </a>
            ${createPinButton(pdf.filename, pdf.document_description || pdf.filename, pdf.relative_path)}
        </div>
    `;
    
    // Tags found in this PDF
    if (cables.length > 0 || equipment.length > 0) {
        html += `<div class="pdf-contents">`;
        
        // Equipment list
        if (equipment.length > 0) {
            html += `
                <div style="margin-bottom: var(--space-lg);">
                    <h4 style="color: var(--accent-equipment); margin-bottom: var(--space-md); display: flex; align-items: center; gap: var(--space-sm);">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px">
                            <rect x="4" y="4" width="16" height="16" rx="2"/>
                            <circle cx="12" cy="12" r="4"/>
                        </svg>
                        Equipment (${equipment.length})
                    </h4>
                    <div class="tags-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-sm);">
            `;
            
            equipment.forEach(tag => {
                html += renderTagItem(tag, pdfUrl);
            });
            
            html += `</div></div>`;
        }
        
        // Cables list
        if (cables.length > 0) {
            html += `
                <div>
                    <h4 style="color: var(--accent-cable); margin-bottom: var(--space-md); display: flex; align-items: center; gap: var(--space-sm);">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px">
                            <path d="M4 9h16"/>
                            <path d="M4 15h16"/>
                            <circle cx="8" cy="9" r="1" fill="currentColor"/>
                            <circle cx="16" cy="15" r="1" fill="currentColor"/>
                        </svg>
                        Cables (${cables.length})
                    </h4>
                    <div class="tags-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-sm);">
            `;
            
            cables.forEach(tag => {
                html += renderTagItem(tag, pdfUrl);
            });
            
            html += `</div></div>`;
        }
        
        html += `</div>`;
    } else {
        html += `
            <div class="text-muted" style="text-align: center; padding: var(--space-lg);">
                No tags found in this document
            </div>
        `;
    }
    
    html += `</div></div>`;
    
    resultsContent.innerHTML = html;
}

function renderTagItem(tag, pdfUrl) {
    const pagesHtml = tag.pages && tag.pages.length > 0 
        ? `<span class="text-muted" style="font-size: 0.75rem;">p. ${tag.pages.slice(0, 5).join(', ')}${tag.pages.length > 5 ? '...' : ''}</span>`
        : '';
    
    const locationHtml = tag.room_tag || tag.deck
        ? `<div class="text-muted" style="font-size: 0.8rem; margin-top: 2px;">
            ${tag.room_tag ? `📍 ${tag.room_tag}${tag.room_description ? ` (${tag.room_description})` : ''}` : ''}
            ${tag.deck ? `🚢 ${tag.deck}` : ''}
           </div>`
        : '';
    
    // Build the PDF search URL with the tag as search parameter
    const pdfSearchUrl = pdfUrl ? `${pdfUrl}#search=${encodeURIComponent(tag.tag_name)}` : null;
    
    const openInPdfButton = pdfSearchUrl ? `
        <a href="${pdfSearchUrl}" target="_blank" class="btn btn-ghost btn-sm" 
           onclick="event.stopPropagation();" title="Open PDF and search for ${escapeHtml(tag.tag_name)}"
           style="padding: 4px 8px; min-width: auto;">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-4.35-4.35"/>
            </svg>
        </a>
    ` : '';
    
    // Add pin button based on tag type
    const isCable = tag.tag_type === 'cable';
    const pinButton = isCable 
        ? createCablePinButton(tag.tag_name, tag.description || '', '', '')
        : createEquipmentPinButton(tag.tag_name, tag.description || '', tag.room_tag || '');
    
    return `
        <div class="tag-item" style="background: var(--bg-tertiary); border-radius: var(--radius-md); padding: var(--space-sm) var(--space-md); cursor: pointer;" onclick="searchTag('${escapeHtml(tag.tag_name)}')">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-sm);">
                <div style="flex: 1; min-width: 0;">
                    <span class="mono" style="color: var(--accent-secondary); font-weight: 500;">${escapeHtml(tag.tag_name)}</span>
                    ${tag.description ? `<div class="text-muted" style="font-size: 0.85rem;">${escapeHtml(tag.description)}</div>` : ''}
                    ${locationHtml}
                </div>
                <div style="display: flex; align-items: center; gap: var(--space-xs); flex-shrink: 0;">
                    ${pagesHtml}
                    ${openInPdfButton}
                    ${pinButton}
                </div>
            </div>
        </div>
    `;
}

function copyPdfLink(url) {
    const fullUrl = window.location.origin + url;
    navigator.clipboard.writeText(fullUrl).then(() => {
        showToast('Link copied to clipboard', 'success');
    }).catch(() => {
        showToast('Failed to copy link', 'error');
    });
}

function addRecentSearch(query) {
    let recent = JSON.parse(localStorage.getItem('recentSearches') || '[]');
    recent = recent.filter(item => item.query !== query);
    recent.unshift({ query: query, timestamp: Date.now() });
    recent = recent.slice(0, 10);
    localStorage.setItem('recentSearches', JSON.stringify(recent));
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
