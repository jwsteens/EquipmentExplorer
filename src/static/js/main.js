/**
 * Equipment Explorer - Main JavaScript
 * Global functionality: theme, keyboard shortcuts, toasts, pinned items (documents, cables, equipment)
 */

// =============================================================================
// THEME MANAGEMENT
// =============================================================================

function getTheme() {
    return localStorage.getItem('theme') || 'dark';
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    updateThemeIcon(theme);
}

function toggleTheme() {
    const current = getTheme();
    const next = current === 'dark' ? 'light' : 'dark';
    setTheme(next);
    showToast(`Switched to ${next} mode`, 'success');
}

function updateThemeIcon(theme) {
    const sunIcon = document.querySelector('.icon-sun');
    const moonIcon = document.querySelector('.icon-moon');
    
    if (sunIcon && moonIcon) {
        if (theme === 'dark') {
            sunIcon.classList.remove('hidden');
            moonIcon.classList.add('hidden');
        } else {
            sunIcon.classList.add('hidden');
            moonIcon.classList.remove('hidden');
        }
    }
}

// Initialize theme on load
document.addEventListener('DOMContentLoaded', function() {
    const theme = getTheme();
    setTheme(theme);
    updatePinnedCount();
    renderPinnedList();
});


// =============================================================================
// PINNED ITEMS (Documents, Cables, Equipment)
// =============================================================================

const PINNED_STORAGE_KEY = 'pinnedItems';

function getPinnedItems() {
    try {
        const stored = localStorage.getItem(PINNED_STORAGE_KEY);
        if (stored) {
            return JSON.parse(stored);
        }
        // Migrate from old pinnedDocuments format
        const oldDocs = localStorage.getItem('pinnedDocuments');
        if (oldDocs) {
            const docs = JSON.parse(oldDocs);
            const migrated = docs.map(d => ({
                identifier: d.filename,
                title: d.title,
                type: 'document',
                relativePath: d.relativePath,
                pinnedAt: d.pinnedAt
            }));
            localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(migrated));
            localStorage.removeItem('pinnedDocuments');
            return migrated;
        }
        return [];
    } catch (e) {
        console.error('Error reading pinned items:', e);
        return [];
    }
}

function savePinnedItems(items) {
    try {
        localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(items));
        updatePinnedCount();
        renderPinnedList();
    } catch (e) {
        console.error('Error saving pinned items:', e);
    }
}

function isPinned(identifier, type) {
    const pinned = getPinnedItems();
    return pinned.some(item => item.identifier === identifier && item.type === type);
}

function pinItem(identifier, title, type, extraData = {}) {
    const pinned = getPinnedItems();
    
    if (pinned.some(item => item.identifier === identifier && item.type === type)) {
        showToast(`Already pinned`, 'info');
        return;
    }
    
    pinned.push({
        identifier: identifier,
        title: title || identifier,
        type: type,
        ...extraData,
        pinnedAt: Date.now()
    });
    
    savePinnedItems(pinned);
    showToast(`${type.charAt(0).toUpperCase() + type.slice(1)} pinned`, 'success');
    updatePinButtons(identifier, type, true);
}

function unpinItem(identifier, type) {
    let pinned = getPinnedItems();
    pinned = pinned.filter(item => !(item.identifier === identifier && item.type === type));
    savePinnedItems(pinned);
    showToast(`Unpinned`, 'success');
    updatePinButtons(identifier, type, false);
}

function togglePinItem(identifier, title, type, extraData = {}) {
    if (isPinned(identifier, type)) {
        unpinItem(identifier, type);
    } else {
        pinItem(identifier, title, type, extraData);
    }
}

// =============================================================================
// DOCUMENT PIN FUNCTIONS (backward compatible)
// =============================================================================

function getPinnedDocuments() {
    return getPinnedItems().filter(item => item.type === 'document');
}

function isPinnedDocument(filename) {
    return isPinned(filename, 'document');
}

function pinDocument(filename, title, relativePath) {
    pinItem(filename, title, 'document', { relativePath });
}

function unpinDocument(filename) {
    unpinItem(filename, 'document');
}

function togglePinDocument(filename, title, relativePath) {
    togglePinItem(filename, title, 'document', { relativePath });
}

// =============================================================================
// CABLE PIN FUNCTIONS
// =============================================================================

function isPinnedCable(cableTag) {
    return isPinned(cableTag, 'cable');
}

function pinCable(cableTag, cableType, startTag, destTag) {
    pinItem(cableTag, cableTag, 'cable', { cableType, startTag, destTag });
}

function unpinCable(cableTag) {
    unpinItem(cableTag, 'cable');
}

function togglePinCable(cableTag, cableType, startTag, destTag) {
    togglePinItem(cableTag, cableTag, 'cable', { cableType, startTag, destTag });
}

// =============================================================================
// EQUIPMENT PIN FUNCTIONS
// =============================================================================

function isPinnedEquipment(equipmentTag) {
    return isPinned(equipmentTag, 'equipment');
}

function pinEquipment(equipmentTag, description, roomTag) {
    pinItem(equipmentTag, equipmentTag, 'equipment', { description, roomTag });
}

function unpinEquipment(equipmentTag) {
    unpinItem(equipmentTag, 'equipment');
}

function togglePinEquipment(equipmentTag, description, roomTag) {
    togglePinItem(equipmentTag, equipmentTag, 'equipment', { description, roomTag });
}

// =============================================================================
// PINNED UI FUNCTIONS
// =============================================================================

function clearAllPinned() {
    if (confirm('Remove all pinned items?')) {
        savePinnedItems([]);
        showToast('All pinned items cleared', 'success');
        
        document.querySelectorAll('.pin-btn.pinned').forEach(btn => {
            btn.classList.remove('pinned');
            btn.title = 'Pin';
        });
    }
}

function updatePinnedCount() {
    const count = getPinnedItems().length;
    const countEl = document.getElementById('pinnedCount');
    if (countEl) {
        countEl.textContent = count;
        countEl.setAttribute('data-count', count);
    }
    
    const clearBtn = document.getElementById('clearPinnedBtn');
    if (clearBtn) {
        clearBtn.style.display = count > 0 ? 'flex' : 'none';
    }
}

function updatePinButtons(identifier, type, pinned) {
    // Update new-style buttons with data-identifier and data-type
    document.querySelectorAll(`.pin-btn[data-identifier="${identifier}"][data-type="${type}"]`).forEach(btn => {
        btn.classList.toggle('pinned', pinned);
        btn.title = pinned ? 'Unpin' : 'Pin';
    });
    
    // Also update old-style document buttons for backward compatibility
    if (type === 'document') {
        document.querySelectorAll(`.pin-btn[data-filename="${identifier}"]`).forEach(btn => {
            btn.classList.toggle('pinned', pinned);
            btn.title = pinned ? 'Unpin document' : 'Pin document';
        });
    }
}

function renderPinnedList() {
    const listEl = document.getElementById('pinnedList');
    if (!listEl) return;
    
    const pinned = getPinnedItems();
    
    if (pinned.length === 0) {
        listEl.innerHTML = `
            <div class="pinned-empty">
                <p>No pinned items yet</p>
                <p class="text-muted" style="font-size: 0.85rem;">Pin documents, cables, or equipment for quick access</p>
            </div>
        `;
        return;
    }
    
    // Sort by most recently pinned
    pinned.sort((a, b) => b.pinnedAt - a.pinnedAt);
    
    // Group by type
    const documents = pinned.filter(p => p.type === 'document');
    const cables = pinned.filter(p => p.type === 'cable');
    const equipment = pinned.filter(p => p.type === 'equipment');
    
    let html = '';
    
    // Documents section
    if (documents.length > 0) {
        html += `<div class="pinned-section">
            <div class="pinned-section-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;color:var(--accent-danger)">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14,2 14,8 20,8"/>
                </svg>
                Documents (${documents.length})
            </div>`;
        documents.forEach(doc => { html += renderPinnedDocument(doc); });
        html += `</div>`;
    }
    
    // Cables section
    if (cables.length > 0) {
        html += `<div class="pinned-section">
            <div class="pinned-section-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;color:var(--accent-cable)">
                    <path d="M4 9h16"/><path d="M4 15h16"/>
                    <circle cx="8" cy="9" r="1" fill="currentColor"/>
                    <circle cx="16" cy="15" r="1" fill="currentColor"/>
                </svg>
                Cables (${cables.length})
            </div>`;
        cables.forEach(cable => { html += renderPinnedCable(cable); });
        html += `</div>`;
    }
    
    // Equipment section
    if (equipment.length > 0) {
        html += `<div class="pinned-section">
            <div class="pinned-section-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;color:var(--accent-equipment)">
                    <rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="4"/>
                </svg>
                Equipment (${equipment.length})
            </div>`;
        equipment.forEach(equip => { html += renderPinnedEquipment(equip); });
        html += `</div>`;
    }
    
    listEl.innerHTML = html;
}

function renderPinnedDocument(doc) {
    return `
        <div class="pinned-item">
            <div class="pinned-item-content">
                <div class="pinned-item-title" title="${escapeHtml(doc.title)}">${escapeHtml(doc.title)}</div>
                <div class="pinned-item-filename">${escapeHtml(doc.identifier)}</div>
            </div>
            <div class="pinned-item-actions">
                <a href="/pdf/${encodeURIComponent(doc.relativePath || doc.identifier)}" target="_blank" class="pinned-item-btn" title="Open PDF">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15,3 21,3 21,9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                </a>
                <a href="/search?q=${encodeURIComponent(doc.identifier)}&type=pdf" class="pinned-item-btn" title="View contents">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                        <circle cx="11" cy="11" r="8"/>
                        <path d="M21 21l-4.35-4.35"/>
                    </svg>
                </a>
                <button class="pinned-item-btn remove" onclick="unpinItem('${escapeHtml(doc.identifier)}', 'document')" title="Remove">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
        </div>`;
}

function renderPinnedCable(cable) {
    const subtitle = cable.startTag && cable.destTag 
        ? `${cable.startTag} → ${cable.destTag}` 
        : (cable.cableType || '');
    
    return `
        <div class="pinned-item">
            <div class="pinned-item-content">
                <div class="pinned-item-title mono" style="color: var(--accent-cable);" title="${escapeHtml(cable.identifier)}">${escapeHtml(cable.identifier)}</div>
                ${subtitle ? `<div class="pinned-item-filename">${escapeHtml(subtitle)}</div>` : ''}
            </div>
            <div class="pinned-item-actions">
                <a href="/search?q=${encodeURIComponent(cable.identifier)}&type=cable" class="pinned-item-btn" title="Search cable">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                        <circle cx="11" cy="11" r="8"/>
                        <path d="M21 21l-4.35-4.35"/>
                    </svg>
                </a>
                <button class="pinned-item-btn remove" onclick="unpinItem('${escapeHtml(cable.identifier)}', 'cable')" title="Remove">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
        </div>`;
}

function renderPinnedEquipment(equip) {
    const subtitle = equip.description || equip.roomTag || '';
    
    return `
        <div class="pinned-item">
            <div class="pinned-item-content">
                <div class="pinned-item-title mono" style="color: var(--accent-equipment);" title="${escapeHtml(equip.identifier)}">${escapeHtml(equip.identifier)}</div>
                ${subtitle ? `<div class="pinned-item-filename">${escapeHtml(subtitle)}</div>` : ''}
            </div>
            <div class="pinned-item-actions">
                <a href="/search?q=${encodeURIComponent(equip.identifier)}&type=equipment" class="pinned-item-btn" title="Search equipment">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                        <circle cx="11" cy="11" r="8"/>
                        <path d="M21 21l-4.35-4.35"/>
                    </svg>
                </a>
                <button class="pinned-item-btn remove" onclick="unpinItem('${escapeHtml(equip.identifier)}', 'equipment')" title="Remove">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
        </div>`;
}

function togglePinnedSidebar() {
    const sidebar = document.getElementById('pinnedSidebar');
    const overlay = document.getElementById('pinnedOverlay');
    
    if (sidebar && overlay) {
        const isOpen = sidebar.classList.contains('open');
        sidebar.classList.toggle('open');
        overlay.classList.toggle('open');
        
        if (!isOpen) {
            renderPinnedList();
        }
    }
}

// =============================================================================
// PIN BUTTON CREATORS
// =============================================================================

// Create a pin button HTML helper for documents
function createPinButton(filename, title, relativePath) {
    const pinned = isPinned(filename, 'document');
    return `
        <button class="pin-btn ${pinned ? 'pinned' : ''}" 
                data-identifier="${escapeHtml(filename)}"
                data-type="document"
                data-filename="${escapeHtml(filename)}"
                onclick="togglePinDocument('${escapeHtml(filename)}', '${escapeHtml(title || filename)}', '${escapeHtml(relativePath)}')"
                title="${pinned ? 'Unpin document' : 'Pin document'}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                <path d="M9 4v6l-2 4v2h10v-2l-2-4V4"/>
                <line x1="12" y1="16" x2="12" y2="21"/>
                <line x1="8" y1="4" x2="16" y2="4"/>
            </svg>
        </button>
    `;
}

// Create a pin button HTML helper for cables
function createCablePinButton(cableTag, cableType, startTag, destTag) {
    const pinned = isPinned(cableTag, 'cable');
    const args = `'${escapeHtml(cableTag)}', '${escapeHtml(cableType || '')}', '${escapeHtml(startTag || '')}', '${escapeHtml(destTag || '')}'`;
    return `
        <button class="pin-btn ${pinned ? 'pinned' : ''}" 
                data-identifier="${escapeHtml(cableTag)}"
                data-type="cable"
                onclick="event.stopPropagation(); togglePinCable(${args})"
                title="${pinned ? 'Unpin cable' : 'Pin cable'}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                <path d="M9 4v6l-2 4v2h10v-2l-2-4V4"/>
                <line x1="12" y1="16" x2="12" y2="21"/>
                <line x1="8" y1="4" x2="16" y2="4"/>
            </svg>
        </button>
    `;
}

// Create a pin button HTML helper for equipment
function createEquipmentPinButton(equipmentTag, description, roomTag) {
    const pinned = isPinned(equipmentTag, 'equipment');
    const args = `'${escapeHtml(equipmentTag)}', '${escapeHtml(description || '')}', '${escapeHtml(roomTag || '')}'`;
    return `
        <button class="pin-btn ${pinned ? 'pinned' : ''}" 
                data-identifier="${escapeHtml(equipmentTag)}"
                data-type="equipment"
                onclick="event.stopPropagation(); togglePinEquipment(${args})"
                title="${pinned ? 'Unpin equipment' : 'Pin equipment'}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px">
                <path d="M9 4v6l-2 4v2h10v-2l-2-4V4"/>
                <line x1="12" y1="16" x2="12" y2="21"/>
                <line x1="8" y1="4" x2="16" y2="4"/>
            </svg>
        </button>
    `;
}


// =============================================================================
// KEYBOARD SHORTCUTS
// =============================================================================

let pendingKey = null;
let pendingKeyTimeout = null;

document.addEventListener('keydown', function(e) {
    // Ignore if typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        // Allow escape to blur
        if (e.key === 'Escape') {
            e.target.blur();
        }
        return;
    }
    
    // Two-key shortcuts (G + ...)
    if (pendingKey === 'g') {
        clearTimeout(pendingKeyTimeout);
        pendingKey = null;
        
        switch (e.key.toLowerCase()) {
            case 'h':
                e.preventDefault();
                window.location.href = '/';
                return;
            case 's':
                e.preventDefault();
                window.location.href = '/search';
                return;
            case 'c':
                e.preventDefault();
                window.location.href = '/cables';
                return;
            case 'd':
                e.preventDefault();
                window.location.href = '/documents';
                return;
        }
    }
    
    // Close pinned sidebar on escape
    const pinnedSidebar = document.getElementById('pinnedSidebar');
    if (e.key === 'Escape' && pinnedSidebar && pinnedSidebar.classList.contains('open')) {
        togglePinnedSidebar();
        return;
    }
    
    // Single-key shortcuts
    switch (e.key) {
        case '/':
            e.preventDefault();
            focusSearch();
            break;
            
        case 'Escape':
            hideShortcuts();
            clearSearch();
            break;
            
        case 't':
        case 'T':
            if (!e.ctrlKey && !e.metaKey) {
                toggleTheme();
            }
            break;
            
        case 'p':
        case 'P':
            if (!e.ctrlKey && !e.metaKey) {
                togglePinnedSidebar();
            }
            break;
            
        case '?':
            e.preventDefault();
            showShortcuts();
            break;
            
        case 'g':
        case 'G':
            pendingKey = 'g';
            pendingKeyTimeout = setTimeout(() => {
                pendingKey = null;
            }, 1000);
            break;
    }
});

function focusSearch() {
    // Try different search inputs
    const searchInputs = [
        document.getElementById('searchInput'),
        document.getElementById('quickSearchInput'),
        document.querySelector('.dataTables_filter input')
    ];
    
    for (const input of searchInputs) {
        if (input) {
            input.focus();
            input.select();
            break;
        }
    }
}

function clearSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput && document.activeElement === searchInput) {
        searchInput.value = '';
        searchInput.blur();
    }
}

function showShortcuts() {
    const modal = document.getElementById('shortcutsModal');
    if (modal) {
        modal.classList.add('show');
    }
}

function hideShortcuts() {
    const modal = document.getElementById('shortcutsModal');
    if (modal) {
        modal.classList.remove('show');
    }
}

// Close shortcuts modal on outside click
document.addEventListener('click', function(e) {
    const modal = document.getElementById('shortcutsModal');
    if (modal && e.target === modal) {
        hideShortcuts();
    }
});


// =============================================================================
// TOAST NOTIFICATIONS
// =============================================================================

function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span>${escapeHtml(message)}</span>
        <button onclick="this.parentElement.remove()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;padding:0;margin-left:var(--space-md);">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
    `;
    
    container.appendChild(toast);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

// Format numbers with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Copy text to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard', 'success');
        return true;
    } catch (err) {
        showToast('Failed to copy', 'error');
        return false;
    }
}


// =============================================================================
// PWA OFFLINE INDICATOR
// =============================================================================

window.addEventListener('online', function() {
    showToast('Back online', 'success');
});

window.addEventListener('offline', function() {
    showToast('You are offline', 'error');
});


// =============================================================================
// USER MENU
// =============================================================================

function toggleUserMenu() {
    const dropdown = document.getElementById('userMenuDropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

// Close user menu on outside click
document.addEventListener('click', function(e) {
    const userMenu = document.querySelector('.user-menu');
    const dropdown = document.getElementById('userMenuDropdown');
    
    if (dropdown && userMenu && !userMenu.contains(e.target)) {
        dropdown.classList.remove('show');
    }
});
