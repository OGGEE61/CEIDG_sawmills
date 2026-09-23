let allData = [];
let filteredData = [];
let currentPage = 1;
let rowsPerPage = 15;

// Chart instances
let regionChartInst = null;
let yearChartInst = null;

// DOM Elements
const wojewodztwoFilter = document.getElementById('wojewodztwoFilter');
const statusFilter = document.getElementById('statusFilter');
const miastoFilter = document.getElementById('miastoFilter');
const kodFilter = document.getElementById('kodFilter');
const searchFilter = document.getElementById('searchFilter');
const hideNanRegion = document.getElementById('hideNanRegion');
const resetFilters = document.getElementById('resetFilters');
const tableBody = document.getElementById('tableBody');
const rowsPerPageSelect = document.getElementById('rowsPerPageSelect');
const recordCountLabel = document.getElementById('recordCount');
const totalFirmsLabel = document.getElementById('totalFirms');
const topRegionLabel = document.getElementById('topRegion');
const prevPageBtn = document.getElementById('prevPage');
const nextPageBtn = document.getElementById('nextPage');
const pageInfoLabel = document.getElementById('pageInfo');

// Setup Chart Defaults for Dark Theme
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    loadData();
    
    // Event listeners
    wojewodztwoFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    hideNanRegion.addEventListener('change', applyFilters);
    miastoFilter.addEventListener('input', applyFilters);
    kodFilter.addEventListener('input', applyFilters);
    searchFilter.addEventListener('input', applyFilters);
    resetFilters.addEventListener('click', () => {
        wojewodztwoFilter.value = '';
        statusFilter.value = '';
        miastoFilter.value = '';
        kodFilter.value = '';
        searchFilter.value = '';
        hideNanRegion.checked = false;
        applyFilters();
    });
    
    rowsPerPageSelect.addEventListener('change', (e) => {
        rowsPerPage = parseInt(e.target.value);
        currentPage = 1;
        updateDashboard();
    });

    prevPageBtn.addEventListener('click', () => {
        if(currentPage > 1) {
            currentPage--;
            renderTable();
        }
    });
    
    nextPageBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(filteredData.length / rowsPerPage);
        if(currentPage < maxPage) {
            currentPage++;
            renderTable();
        }
    });
});

// Load CSV Data
function loadData() {
    Papa.parse('tartaki_ceidg.csv', {
        download: true,
        header: true,
        skipEmptyLines: true,
        complete: function(results) {
            allData = results.data;
            filteredData = [...allData];
            
            // Populate Filters
            populateFilters();
            
            // Render
            applyFilters();
            recordCountLabel.textContent = "Dane załadowane. Połączono.";
            document.querySelector('.dot').classList.remove('pulse');
        },
        error: function(err) {
            console.error(err);
            recordCountLabel.textContent = "Błąd ładowania danych.";
            recordCountLabel.style.color = "var(--danger)";
            document.querySelector('.dot').style.backgroundColor = "var(--danger)";
        }
    });
}

function populateFilters() {
    const wojewodztwa = new Set();
    const statusy = new Set();
    
    allData.forEach(row => {
        if(row['detail.adresDzialalnosci.wojewodztwo']) wojewodztwa.add(row['detail.adresDzialalnosci.wojewodztwo'].toUpperCase());
        if(row['STATUS']) statusy.add(row['STATUS'].toUpperCase());
    });
    
    Array.from(wojewodztwa).sort().forEach(w => {
        const opt = document.createElement('option');
        opt.value = w;
        opt.textContent = w;
        wojewodztwoFilter.appendChild(opt);
    });
    
    // Statuses are hardcoded in HTML, so we don't need to auto-populate them.
}

function applyFilters() {
    const wFilter = wojewodztwoFilter.value.toLowerCase();
    const sFilter = statusFilter.value.toLowerCase();
    const mFilter = miastoFilter.value.toLowerCase();
    const kFilter = kodFilter.value.toLowerCase();
    const term = searchFilter.value.toLowerCase();
    const hideNan = hideNanRegion.checked;
    
    filteredData = allData.filter(row => {
        const woj = (row['detail.adresDzialalnosci.wojewodztwo'] || '').toLowerCase();
        const stat = (row['STATUS'] || '').toLowerCase();
        const miasto = (row['detail.adresDzialalnosci.miasto'] || '').toLowerCase();
        const kod = (row['detail.adresDzialalnosci.kod'] || '').toLowerCase();
        const nazwa = (row['NAZWA'] || '').toLowerCase();
        const nip = (row['NIP'] || '').toLowerCase();
        
        const matchWoj = !wFilter || woj === wFilter;
        const matchStat = sFilter === 'all' || !sFilter || stat === sFilter;
        const matchMiasto = !mFilter || miasto.includes(mFilter);
        const matchKod = !kFilter || kod.includes(kFilter);
        const matchSearch = !term || nazwa.includes(term) || nip.includes(term);
        const matchNan = !hideNan || (woj !== 'nan' && woj !== '');
        
        return matchWoj && matchStat && matchMiasto && matchKod && matchSearch && matchNan;
    });
    
    currentPage = 1;
    updateDashboard();
}

function updateDashboard() {
    totalFirmsLabel.textContent = filteredData.length.toLocaleString('pl-PL');
    
    renderTable();
    renderCharts();
    updateTopRegion();
}

function updateTopRegion() {
    const counts = {};
    filteredData.forEach(row => {
        const w = (row['detail.adresDzialalnosci.wojewodztwo'] || 'BRAK').toUpperCase();
        counts[w] = (counts[w] || 0) + 1;
    });
    
    let max = 0;
    let top = "-";
    for(const [k, v] of Object.entries(counts)) {
        if(v > max && k !== 'BRAK' && k !== 'NAN') {
            max = v;
            top = k;
        }
    }
    
    topRegionLabel.textContent = top;
}

function renderTable() {
    tableBody.innerHTML = '';
    
    const start = (currentPage - 1) * rowsPerPage;
    const end = start + rowsPerPage;
    const pageData = filteredData.slice(start, end);
    
    pageData.forEach(row => {
        const tr = document.createElement('tr');
        
        // Extract values handling potential missing keys
        const nazwa = row['NAZWA'] || '-';
        const nip = row['detail.wlasciciel.nip'] || row['summary.wlasciciel.nip'] || row['NIP'] || '-';
        const regon = row['detail.wlasciciel.regon'] || row['summary.wlasciciel.regon'] || row['REGON'] || '-';
        const pkd = row['PKD_GLOWNE_KOD'] || '-';
        const woj = row['detail.adresDzialalnosci.wojewodztwo'] || '-';
        const powiat = row['detail.adresDzialalnosci.powiat'] || '-';
        const gmina = row['detail.adresDzialalnosci.gmina'] || '-';
        const miasto = row['detail.adresDzialalnosci.miasto'] || '-';
        const ulica = (row['detail.adresDzialalnosci.ulica'] && row['detail.adresDzialalnosci.ulica'] !== 'nan') ? row['detail.adresDzialalnosci.ulica'] : '';
        const budynek = (row['detail.adresDzialalnosci.budynek'] && row['detail.adresDzialalnosci.budynek'] !== 'nan') ? row['detail.adresDzialalnosci.budynek'] : '';
        const lokal = (row['detail.adresDzialalnosci.lokal'] && row['detail.adresDzialalnosci.lokal'] !== 'nan') ? row['detail.adresDzialalnosci.lokal'] : '';
        const kod = row['detail.adresDzialalnosci.kod'] || '-';
        const email = row['EMAIL'] && row['EMAIL'] !== 'nan' ? row['EMAIL'] : '-';
        const telefon = row['TELEFON'] && row['TELEFON'] !== 'nan' ? row['TELEFON'] : '-';
        const www = row['WWW'] && row['WWW'] !== 'nan' ? row['WWW'] : '-';
        const status = row['STATUS'] || '-';
        const dataRozp = row['detail.dataRozpoczecia'] || '-';

        let fullAdres = miasto;
        
        let ulicaPart = '';
        if (ulica) ulicaPart += ulica + ' ';
        if (budynek) ulicaPart += budynek;
        if (lokal) ulicaPart += '/' + lokal;
        
        if(ulicaPart.trim()) {
            fullAdres += `<br><span style="font-size: 0.85em; color: var(--text-muted);">${ulicaPart.trim()}</span>`;
        }
        
        tr.innerHTML = `
            <td class="col-nazwa"><strong>${nazwa}</strong></td>
            <td>${nip}</td>
            <td>${regon}</td>
            <td>${pkd}</td>
            <td>${woj}</td>
            <td>${powiat}</td>
            <td>${gmina}</td>
            <td>${fullAdres}</td>
            <td>${kod}</td>
            <td>${email}</td>
            <td>${telefon}</td>
            <td>${www}</td>
            <td><span class="badge ${status === 'AKTYWNY' ? 'badge-active' : ''}">${status}</span></td>
            <td>${dataRozp}</td>
        `;
        tableBody.appendChild(tr);
    });
    
    // Update pagination controls
    const maxPage = Math.ceil(filteredData.length / rowsPerPage) || 1;
    pageInfoLabel.textContent = `Strona ${currentPage} z ${maxPage}`;
    
    prevPageBtn.disabled = currentPage === 1;
    nextPageBtn.disabled = currentPage === maxPage;
}

function renderCharts() {
    // Prepare Data for Region Chart
    const regionCounts = {};
    const yearCounts = {};
    
    filteredData.forEach(row => {
        // Regions
        const w = (row['detail.adresDzialalnosci.wojewodztwo'] || 'Inne').toUpperCase();
        regionCounts[w] = (regionCounts[w] || 0) + 1;
        
        // Years
        const dateStr = row['detail.dataRozpoczecia'];
        if(dateStr && dateStr.length >= 4) {
            const year = dateStr.substring(0, 4);
            yearCounts[year] = (yearCounts[year] || 0) + 1;
        }
    });
    
    // Sort regions by count
    const sortedRegions = Object.entries(regionCounts).sort((a,b) => b[1] - a[1]).slice(0, 10); // Top 10
    
    // Sort years by year desc, take top 5
    const sortedYears = Object.keys(yearCounts).sort().reverse().slice(0, 6).reverse(); // Last 6 years
    const yearData = sortedYears.map(y => yearCounts[y]);

    // Draw Region Chart
    const rCtx = document.getElementById('regionChart').getContext('2d');
    if(regionChartInst) regionChartInst.destroy();
    
    regionChartInst = new Chart(rCtx, {
        type: 'bar',
        data: {
            labels: sortedRegions.map(i => i[0]),
            datasets: [{
                label: 'Liczba firm',
                data: sortedRegions.map(i => i[1]),
                backgroundColor: 'rgba(59, 130, 246, 0.8)',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } }
        }
    });
    
    // Draw Year Chart
    const yCtx = document.getElementById('yearChart').getContext('2d');
    if(yearChartInst) yearChartInst.destroy();
    
    yearChartInst = new Chart(yCtx, {
        type: 'line',
        data: {
            labels: sortedYears,
            datasets: [{
                label: 'Nowe firmy',
                data: yearData,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 3,
                tension: 0.3,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } }
        }
    });
}
