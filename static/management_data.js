feather.replace();

function normalizeDateToISO(dateInput) {
  if (!dateInput || dateInput === '-' || dateInput === '') return null;

  if (typeof dateInput === 'number') {
    const excelEpoch = new Date(Date.UTC(1899, 11, 30));
    const date = new Date(excelEpoch.getTime() + dateInput * 86400000);
    return date.toISOString().split('T')[0];
  }

  const match = dateInput.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (match) {
    const [_, day, month, year] = match;
    return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(dateInput)) {
    return dateInput;
  }

  const parsed = new Date(dateInput);
  return !isNaN(parsed) ? parsed.toISOString().split('T')[0] : null;
}

/* --- Format tanggal untuk tampilan --- */
function formatDateDisplay(dateInput) {
  if (!dateInput || dateInput === '-') return '-';
  if (dateInput === 'all') return 'All';
  const iso = normalizeDateToISO(dateInput);
  if (!iso) return '-';
  const [y, m, d] = iso.split('-');
  return `${d}-${m}-${y}`;
}

/* --- Ambil tanggal kemarin (H-1) dalam format ISO --- */
function getYesterdayISO() {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return yesterday.toISOString().split('T')[0];
}

/* --- Toggle sidebar --- */
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('show');
  document.getElementById('sidebarOverlay').classList.toggle('show');
}

/* --- Update nomor baris tabel 
function updateRowNumbers() {
  document.querySelectorAll("#excelTable tbody tr").forEach((row, i) => {
    const noCell = row.querySelector("td");
    if (noCell) noCell.textContent = i + 1;
  });
}--- */

/* --- Update nomor tiket ke MongoDB --- */
function updateNoToMongoDB() {
  const rows = document.querySelectorAll("#excelTable tbody tr");
  const updates = [];

  rows.forEach((row, i) => {
    const no_tiket = row.querySelector("td[data-key='no_tiket']")?.textContent.trim();
    if (no_tiket) updates.push({ no_tiket, no: i + 1 });
  });

  fetch('/update-no', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates })
  })
    .then(res => res.json())
    .then(result => {
      if (result.message === "Nomor berhasil diperbarui") {
        console.log("Update nomor berhasil");
      } else {
        console.warn("Gagal memperbarui nomor");
      }
    })
    .catch(err => console.error("Error update nomor:", err));
}

/* --- Update tabel dari data tersimpan di MongoDB --- */
function updateTableWithSavedData(data) {
  const tbody = document.querySelector('#excelTable tbody');
  tbody.innerHTML = '';

  data.forEach((row, i) => {
    const caringContent = `<span class="caring-display"><span class="caring-text">${row.caring}</span></span>`;
    const reassignContent = `<span class="text-dark">${row.reassign || 'YA'}</span>`;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${row.tanggal}</td>
      <td data-key="no_tiket">${row.no_tiket}</td>
      <td>${row.no_inet}</td>
      <td>${row.sto}</td>
      <td>${row.redaman}</td>
      <td>${row.scc_not_passed}</td>
      <td>${caringContent}</td>
      <td>${reassignContent}</td>
    `;
    tbody.appendChild(tr);
  });
}

document.addEventListener('DOMContentLoaded', function () {
  /* --- Import file Excel --- */
  document.getElementById('excelFile').addEventListener('change', function (e) {
    const file = e.target.files[0];
    if (!file) return;

    const loadingOverlay = document.getElementById('loadingOverlay');

    document.querySelector('#excelTable tbody').innerHTML = '';
    const paginationWrapper = document.querySelector('.pagination-wrapper');
    if (paginationWrapper) paginationWrapper.remove(); 

    loadingOverlay.classList.remove('d-none');
    loadingOverlay.classList.add('d-flex');

    const reader = new FileReader();
    reader.onload = function (e) {
      const data = new Uint8Array(e.target.result);
      const workbook = XLSX.read(data, { type: 'array' });
      const worksheet = workbook.Sheets['TIKET NC'];

      if (!worksheet) {
        alert('Sheet "TIKET NC" tidak ditemukan.');
        hideLoading();
        return;
      }

      const jsonData = XLSX.utils.sheet_to_json(worksheet, { defval: '-' });

      const yesterdayISO = getYesterdayISO();

      const hasYesterday = jsonData.some(r => normalizeDateToISO(r.DATE_CLOSE) === yesterdayISO);

      let targetDate;
      if (hasYesterday) {
        targetDate = yesterdayISO;
      } else {
        const allDates = jsonData
          .map(r => normalizeDateToISO(r.DATE_CLOSE))
          .filter(Boolean)
          .sort()
          .reverse();
        targetDate = allDates[0] || null;
      }

      if (!targetDate) {
        alert("Tidak bisa menentukan tanggal dari data Excel.");
        hideLoading();
        return;
      }

      fetch('/check-date-exists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tanggal: targetDate })
      })

      .then(res => res.json())
      .then(result => {
        if (result.exists) {
          alert(result.message);
          hideLoading();
          return;  
        }
        lanjutProsesImport(jsonData); 
      })
            .catch(err => {
              console.error('Error saat cek tanggal:', err);
              hideLoading();
            });
        };
        reader.readAsArrayBuffer(file);

    function hideLoading() {
      loadingOverlay.classList.add('d-none');
      loadingOverlay.classList.remove('d-flex');
    }

    function lanjutProsesImport(jsonData) {
      const tbody = document.querySelector('#excelTable tbody');
      tbody.innerHTML = '';
      const yesterdayISO = getYesterdayISO();
      const fragment = document.createDocumentFragment();
      let count = 1;

      const dropdownHTML = (prefix, initial) => `
        <div class="dropdown caring-dropdown">
          <button class="btn btn-sm dropdown-toggle caring-display" type="button" data-bs-toggle="dropdown">
            <span class="caring-text">${prefix}${initial}</span>
          </button>
          <ul class="dropdown-menu">
            <li><a class="dropdown-item caring-option" href="#">YA</a></li>
            <li><a class="dropdown-item caring-option" href="#">RNA</a></li>
            <li><a class="dropdown-item caring-option" href="#">Reject</a></li>
            <li><a class="dropdown-item caring-option" href="#">Diluar Jangkauan</a></li>
          </ul>
        </div>`;

      jsonData.forEach(row => { 
        const witel = row.WITEL?.toString().toLowerCase() || '';
        const rowDateISO = normalizeDateToISO(row.DATE_CLOSE);
        const isHMinus1 = rowDateISO === yesterdayISO;
        const boosterParts = row.IBOOSTER_ONT_RX?.toString().split('|').map(p => p.trim());
        const boosterValue = parseFloat(boosterParts?.[boosterParts.length - 1] || '');
        const redamanYa = !isNaN(boosterValue) && boosterValue <= -23 && boosterValue >= -40;
        const sccPassed = (!row.TROUBLE_CLOSED_GROUP || row.TROUBLE_CLOSED_GROUP === '-') && rowDateISO ? 'YA' : '-';
        const showRow = redamanYa || sccPassed === 'YA';

        if (witel.includes('lampung') && (isHMinus1 || !rowDateISO) && showRow) {
          let caringContent = '-';
          if (redamanYa && sccPassed === 'YA') caringContent = dropdownHTML(`ONT=${boosterValue}, `, 'YA');
          else if (redamanYa) caringContent = `<span class="caring-display">ONT=${boosterValue}</span>`;
          else if (sccPassed === 'YA') caringContent = dropdownHTML('', 'YA');

          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${count++}</td>
            <td>${formatDateDisplay(row.DATE_CLOSE)}</td>
            <td>${row.TROUBLE_NO || '-'}</td>
            <td>${((row.ND_GROUP ?? '-').toString()).split(/[-–]/)[0].trim()}</td>
            <td>${row.STO || '-'}</td>
            <td>${redamanYa ? 'YA' : '-'}</td>
            <td>${sccPassed}</td>
            <td>${caringContent}</td>
            <td>
              <div class="dropdown reassign-dropdown">
                <button class="dropdown-toggle reassign-display text-dark bg-transparent border-0" type="button" data-bs-toggle="dropdown">
                  ${row.reassign || 'YA'}
                </button>
                <ul class="dropdown-menu">
                  <li><a class="dropdown-item reassign-option" href="#">Ya</a></li>
                  <li><a class="dropdown-item reassign-option" href="#">Tidak</a></li>
                </ul>
              </div>
            </td>
          `;
          fragment.appendChild(tr);
        }
      });

      tbody.appendChild(fragment);
      document.getElementById('saveBtn').classList.remove('d-none');
    
      hideLoading();
      document.getElementById('excelFile').value = '';
    }
  });


  /* --- Export ke Excel --- */
  document.getElementById('exportBtn').addEventListener('click', function () {
    const rows = Array.from(document.querySelectorAll("#excelTable tbody tr"))
      .map(row => Array.from(row.querySelectorAll("td")).map(cell => cell.innerText.trim()));

    const headers = [
      ['NO', 'TANGGAL', 'NO TIKET', 'NO INET', 'STO', 'POTENSI GAUL BY', '', 'CARING', 'RE-ASSIGN'],
      ['', '', '', '', '', 'REDAMAN', 'SCC NOT PASSED', '', '']
    ];

    const data = [...headers, ...rows];
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.aoa_to_sheet(data);

    ws['!merges'] = [{ s: { r: 0, c: 5 }, e: { r: 0, c: 6 } }];
    XLSX.utils.book_append_sheet(wb, ws, 'Lampung_Tickets');
    XLSX.writeFile(wb, 'rekap_tiket_lampung.xlsx');
  });

  /* --- Event delegasi untuk dropdown Caring & Status --- */
  document.addEventListener('click', function (e) {
    if (e.target.classList.contains('caring-option')) {
      e.preventDefault();
      const selected = e.target.textContent;
      const caringBtn = e.target.closest('.dropdown').querySelector('.caring-display .caring-text');
      if (caringBtn) {
        const prefix = caringBtn.textContent.match(/(ONT=[^,]+, )?/)?.[0] || '';
        caringBtn.textContent = `${prefix}${selected}`;
      }
    }

    if (e.target.classList.contains('reassign-option')) {
      e.preventDefault();
      const selectedText = e.target.textContent.trim();
      const displaySpan = e.target.closest('.dropdown').querySelector('.reassign-display');
      if (displaySpan) displaySpan.innerHTML = `${selectedText}`;
    }

    if (e.target.classList.contains('filter-option-db')) {
      e.preventDefault();
      window.location.href = `/management_data?date=${e.target.dataset.date}&page=0`;
    }
  });

  /* --- Tombol Save --- */
  document.getElementById('saveBtn').addEventListener('click', async function () {
    const rows = document.querySelectorAll('#excelTable tbody tr');
    if (!rows.length) {
      alert('Tidak ada data untuk disimpan.');
      return;
    }

    const dataToSave = Array.from(rows).map((row, i) => {
      const cells = row.querySelectorAll('td');
      const getText = (idx) => cells[idx]?.innerText.trim() || '-';

      const caringValue = cells[7]?.querySelector('.caring-text')?.textContent.trim()
        || cells[7]?.innerText.trim()
        || '-';

      const reassignValue = cells[8]?.querySelector('.reassign-display')?.textContent.trim()
        || cells[8]?.innerText.trim()
        || 'YA';

      return {
        no: i + 1,
        tanggal: normalizeDateToISO(getText(1)),
        no_tiket: getText(2),
        no_inet: getText(3),
        sto: getText(4),
        redaman: getText(5),
        scc_not_passed: getText(6),
        caring: caringValue,
        reassign: reassignValue
      };
    });

    // Kirim ke backend
    const response = await fetch('/save-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: dataToSave })
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      alert(err.message || 'Gagal menyimpan data ke server.');
      return;
    }

    const result = await response.json();
    alert(result.message || 'Data berhasil disimpan!');
    document.getElementById('saveBtn').classList.add('d-none');
  });


function doSearch() {
  const searchValue = document.getElementById("searchInput").value.trim();
  const params = new URLSearchParams(window.location.search);

  if (searchValue) {
    params.set("search", searchValue);
    params.set("page", 1); 
  } else {
    params.delete("search");
  }

  window.location.search = params.toString();
}

// Enter untuk search
document.getElementById("searchInput").addEventListener("keyup", function (e) {
  if (e.key === "Enter") {
    doSearch();
  }
  if (this.value === "") {
    doSearch();
  }
});
 
    });
