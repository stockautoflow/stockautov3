document.addEventListener('DOMContentLoaded', () => {
    const tableBody = document.getElementById('monitor-table-body');
    const statusIndicator = document.getElementById('connection-status');
    const modalBackdrop = document.getElementById('modal-backdrop');
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modeToggle = document.getElementById('mode-toggle');
    const modeLabel = document.getElementById('mode-label');
    const filterInputs = document.querySelectorAll('.filter-input');
    const sortHeaders = document.querySelectorAll('#monitor-table th.sortable'); // v1.14 selector fix
    
    let eventSource;
    let lastId = 0;
    let isLiveMode = true;
    let sortState = { col: 0, asc: false }; // <-- 修正 1/4: デフォルトを降順(false)に

    // --- Modal Control ---
    const showModal = (id) => { console.log(`showModal(${id})`); fetch(`/get_details/${id}`).then(r => r.json()).then(d => { if(d.error){alert(`Error: ${d.error}`); return;} document.getElementById('modal-title').textContent = `通知詳細 (ID: ${id})`; document.getElementById('modal-subject').textContent = d.subject || '(None)'; document.getElementById('modal-body').textContent = d.body || '(None)'; const e = document.getElementById('modal-error'); e.textContent = d.error_message || '(None)'; e.parentElement.style.display = d.error_message ? 'block' : 'none'; modalBackdrop.style.display = 'flex'; }).catch(e => { console.error('Failed fetch details:', e); alert('Failed load details.');}); };
    const closeModal = () => { modalBackdrop.style.display = 'none'; };
    modalCloseBtn.addEventListener('click', closeModal);
    modalBackdrop.addEventListener('click', (e) => { if (e.target === modalBackdrop) closeModal(); });

    // --- Table Row Insertion ---
    const addRow = (item, position = 'afterbegin') => {
        if (!isLiveMode && !passesFilters(item)) { /* console.log(`[Initial/Analysis] Skip ID ${item.id}`); */ return; } // v1.14 check
        let dirClass = ''; if (item.direction === 'BUY') dirClass = 'col-dir-buy'; if (item.direction === 'SELL') dirClass = 'col-dir-sell';
        const row = document.createElement('tr'); row.dataset.status = item.status;
        const summaryHtml = item.summary.replace(/\n/g, '<br>');
        row.innerHTML = `
            <td class="col-id" data-value="${item.id}">${item.id}</td>
            <td class="col-time" data-value="${item.time}">${item.time}</td>
            <td class="col-status" data-value="${item.status}"><span class="status-badge status-${item.status.toLowerCase()}">${item.status}</span></td>
            <td class="col-event" data-value="${item.event_type}">${item.event_type}</td>
            <td class="col-symbol" data-value="${item.symbol}">${item.symbol}</td>
            <td class="col-symbol-name" data-value="${item.symbol_name}">${item.symbol_name}</td>
            <td class="col-direction ${dirClass}" data-value="${item.direction}">${item.direction}</td>
            <td class="col-quantity" data-value="${item.quantity}">${item.quantity}</td>
            <td class="col-price" data-value="${item.price}">${item.price}</td>
            <td class="col-tp" data-value="${item.tp}">${item.tp}</td>
            <td class="col-sl" data-value="${item.sl}">${item.sl}</td>
            <td class="col-summary">${summaryHtml}</td>
            <td class="col-action"><button class="detail-btn" data-id="${item.id}">表示</button></td>
        `;
        tableBody.insertAdjacentElement(position, row);
        row.querySelector('.detail-btn').addEventListener('click', (e) => { showModal(e.target.dataset.id); });
    };

    // --- SSE Connection ---
    const connectEventSource = (id) => {
        if (eventSource) eventSource.close();
        const queryId = (typeof id === 'number' && !isNaN(id)) ? id : 0;
        eventSource = new EventSource(`/stream?last_id=${queryId}`);
        eventSource.onopen = () => { console.log('SSE connected.'); statusIndicator.textContent = '● 接続中'; statusIndicator.className = 'status-connected'; };
        eventSource.onmessage = (event) => {
            try {
                const newDataArray = JSON.parse(event.data);
                if (Array.isArray(newDataArray)) {
                    newDataArray.forEach(item => {
                        // v1.14: Filter SSE data too
                        if (passesFilters(item)) { addRow(item, 'afterbegin'); }
                        lastId = item.id;
                    });
                }
            } catch (e) { console.error('SSE parse error:', e, event.data); }
        };
        eventSource.onerror = (err) => {
            console.error('SSE error:', err); statusIndicator.textContent = '● 切断 (再接続...)'; statusIndicator.className = 'status-disconnected'; eventSource.close();
            if (isLiveMode) { setTimeout(() => connectEventSource(lastId), 5000); }
        };
        eventSource.addEventListener('connected', (event) => { console.log('SSE connected event.'); });
        eventSource.addEventListener('heartbeat', (event) => { /* console.log('SSE heartbeat'); */ if (statusIndicator.className.includes('disconnected')) { statusIndicator.textContent = '● 接続中'; statusIndicator.className = 'status-connected'; } });
    };

    // --- Initial Data Load ---
    const loadInitialData = () => {
        console.log("loadInitialData..."); tableBody.innerHTML = '';
        fetch('/get_initial_data')
            .then(r => { console.log("Initial fetch status:", r.status); if(!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
            .then(d => {
                if(d.error){ console.error("API Error:", d.error); statusIndicator.textContent = `● DBエラー`; statusIndicator.className = 'status-error'; return; }
                console.log(`Received ${d.data.length} items.`); d.data.forEach(item => addRow(item, 'beforeend'));
                lastId = d.last_id; console.log(`Initial load done. Last ID: ${lastId}`);
                
                // ▼▼▼【変更箇所 2/4】▼▼▼
                // [変更前] sortState = { col: 0, asc: true }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); sortHeaders[0]?.classList.add('sort-asc'); sortRows(0, 'number', true);
                
                // [変更後] デフォルトを 'asc: false' (降順) にする
                sortState = { col: 0, asc: false }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); sortHeaders[0]?.classList.add('sort-desc'); sortRows(0, 'number', false); 
                // ▲▲▲【変更箇所ここまで】▲▲▲

                if (!isLiveMode) { applyFilters(); } // v1.14 Apply filters if starting in analysis mode
                if (isLiveMode) { console.log("Connecting SSE..."); connectEventSource(lastId); }
            })
            .catch(e => { console.error('Fetch Error:', e); statusIndicator.textContent = '● サーバーエラー'; statusIndicator.className = 'status-error'; });
    };

    // --- Mode Toggle ---
    modeToggle.addEventListener('change', () => {
        isLiveMode = modeToggle.checked; console.log(`Mode: ${isLiveMode ? 'Live' : 'Analysis'}`);
        document.body.classList.toggle('live-mode', isLiveMode); document.body.classList.toggle('analysis-mode', !isLiveMode);
        if (isLiveMode) {
            modeLabel.textContent = 'ライブ更新中'; statusIndicator.style.display = 'inline-block';
            filterInputs.forEach(input => { input.disabled = true; input.value = ''; });
            
            // ▼▼▼【変更箇所 3/4】▼▼▼
            // [変更前] sortState = { col: 0, asc: true }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); sortHeaders[0]?.classList.add('sort-asc');
            
            // [変更後] ライブモードに戻る際のソートも 'asc: false' (降順) にする
            sortState = { col: 0, asc: false }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); sortHeaders[0]?.classList.add('sort-desc');
            // ▲▲▲【変更箇所ここまで】▲▲▲
            
            loadInitialData(); // Reload & reconnect
        } else {
            console.log("Analysis mode: closing SSE."); if(eventSource) eventSource.close();
            modeLabel.textContent = '分析モード (停止中)'; statusIndicator.textContent = '● 停止'; statusIndicator.className = 'status-disconnected';
            filterInputs.forEach(input => input.disabled = false);
            applyFilters(); // Apply filters to current view
        }
    });

    // --- Filtering Logic (v1.14 - Simplified & Logged) ---
    const passesFilters = (item) => {
        // console.log(`passesFilters for ID ${item.id}`);
        for (const input of filterInputs) {
            const filterValue = input.value.toLowerCase(); if (filterValue === '') continue;
            const colIndex = input.dataset.column; let cellValue = ''; let match = false;
            // Get value
            if (colIndex === '0') cellValue = String(item.id); else if (colIndex === '1') cellValue = item.time; else if (colIndex === '2') cellValue = item.status; else if (colIndex === '3') cellValue = item.event_type; else if (colIndex === '4') cellValue = item.symbol; else if (colIndex === '5') cellValue = item.symbol_name; else if (colIndex === '6') cellValue = item.direction; else if (colIndex === '7') cellValue = item.quantity; else if (colIndex === '8') cellValue = item.price; else if (colIndex === '9') cellValue = item.tp; else if (colIndex === '10') cellValue = item.sl; else continue;
            cellValue = cellValue.toLowerCase();
            // Apply logic
            if (colIndex === '3') { if (filterValue === '1') match = cellValue.startsWith('新規注文発注'.toLowerCase()); else if (filterValue === '2') match = cellValue.startsWith('決済完了'.toLowerCase()); else match = cellValue.includes(filterValue); }
            else { match = cellValue.includes(filterValue); }
            if (!match) { console.log(`  > Filter FAIL: ID=${item.id}, Col=${colIndex}, Val='${cellValue}', Filter='${filterValue}'`); return false; }
            // else { console.log(`  > Filter PASS: ID=${item.id}, Col=${ColIndex}, Val='${cellValue}', Filter='${filterValue}'`); }
        }
        // console.log(`  > Filter ALL PASS for ID ${item.id}`);
        return true;
    };
    const applyFilters = () => {
        console.log("applyFilters..."); // v1.14 Log
        const rows = tableBody.querySelectorAll('tr'); const activeFilters = Array.from(filterInputs).filter(i => i.dataset.column <= 10 && i.value !== '').map(input => ({ col: input.dataset.column, value: input.value.toLowerCase() }));
        console.log("Active filters:", activeFilters); // v1.14 Log
        rows.forEach(row => {
            let isVisible = true; const rowId = row.cells[0]?.textContent;
            for (const filter of activeFilters) {
                const colIndex = filter.col; const cell = row.cells[colIndex]; if (!cell) continue; // Safety check
                const cellValue = (cell.dataset.value || cell.textContent).toLowerCase(); let filterValue = filter.value; let match = false;
                if (colIndex === '3') { if (filterValue === '1') match = cellValue.startsWith('新規注文発注'.toLowerCase()); else if (filterValue === '2') match = cellValue.startsWith('決済完了'.toLowerCase()); else match = cellValue.includes(filterValue); }
                else { match = cellValue.includes(filterValue); }
                if (!match) { isVisible = false; console.log(`  > Hiding Row ID ${rowId}: Failed filter Col=${colIndex}, Val='${cellValue}', Filter='${filterValue}'`); break; } // v1.14 Log break
            }
            // console.log(`Row ID ${rowId} visibility set to: ${isVisible}`); // v1.14 Log
            row.style.display = isVisible ? '' : 'none';
        });
    };
    filterInputs.forEach(input => input.addEventListener('input', applyFilters));

    // --- Sorting Logic ---
    sortHeaders.forEach(header => {
        header.addEventListener('click', () => {
            if (isLiveMode) return; const colIndex = header.dataset.column; const dataType = header.dataset.type;
            
            // ▼▼▼【変更箇所 4/4】▼▼▼
            // [変更前] let isAsc; if (sortState.col == colIndex) { isAsc = !sortState.asc; } else { isAsc = true; }
            
            // [変更後] 新しい列をクリックしたときのデフォルトも降順(false)にする (ID列(0)以外の場合)
            let isAsc; 
            if (sortState.col == colIndex) { 
                isAsc = !sortState.asc; 
            } else { 
                isAsc = (colIndex == 0) ? false : true; // デフォルトは昇順だが、ID(0)列だけ降順
            }
            // ▲▲▲【変更箇所ここまで】▲▲▲

            sortState = { col: colIndex, asc: isAsc }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); header.classList.add(isAsc ? 'sort-asc' : 'sort-desc');
            sortRows(colIndex, dataType, isAsc);
        });
    });
    const sortRows = (colIndex, dataType, isAsc) => {
        console.log(`Sorting col ${colIndex}, type ${dataType}, asc ${isAsc}`); // v1.14 Log
        const rows = Array.from(tableBody.querySelectorAll('tr')); const multiplier = isAsc ? 1 : -1;
        rows.sort((rowA, rowB) => {
            const cellA = rowA.cells[colIndex]; const cellB = rowB.cells[colIndex]; if(!cellA || !cellB) return 0; // Safety
            let valA = cellA.dataset.value || cellA.textContent; let valB = cellB.dataset.value || cellB.textContent;
            if (dataType === 'number') { valA = parseFloat(valA) || 0; valB = parseFloat(valB) || 0; } // v1.14 NaN fallback
            if (valA < valB) return -1 * multiplier; if (valA > valB) return 1 * multiplier; return 0;
        });
        rows.forEach(row => tableBody.appendChild(row));
        // applyFilters(); // v1.14: Removed, sorting shouldn't hide rows based on old filter state
    };

    loadInitialData();
});