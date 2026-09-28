/* ===================================================================
   BACKUP — Database backup trigger and status handling
=================================================================== */

const Backup = (() => {
  let isBackingUp = false;

  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;

    // Cookie fallback
    const name = 'csrftoken';
    const matches = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, '\\$1') + '=([^;]*)'));
    return matches ? decodeURIComponent(matches[1]) : '';
  }

  async function createBackup() {
    if (isBackingUp) return;

    const btn = document.getElementById('btn-backup-db');
    const iconEl = document.getElementById('btn-backup-icon');
    const textEl = document.getElementById('btn-backup-text');

    isBackingUp = true;
    if (btn) {
      btn.disabled = true;
      btn.classList.add('opacity-70', 'cursor-not-allowed');
    }
    if (iconEl) {
      iconEl.innerHTML = `<svg class="animate-spin h-3.5 w-3.5 inline-block text-blue-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 004 4h4v-4a8 8 0 01-8-8z"></path>
      </svg>`;
    }
    if (textEl) {
      textEl.textContent = 'در حال تهیه پشتیبان...';
    }

    try {
      const response = await fetch('/dashboard/api/backup/create/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCsrfToken(),
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      });

      const data = await response.json();

      if (response.ok && data.status === 'success') {
        const backup = data.backup || {};
        const successMsg = `بک‌آپ با موفقیت در پوشه db-backups ذخیره شد (${backup.size || ''})`;
        if (typeof Toast !== 'undefined') {
          Toast.show(successMsg, 'success', 5000);
        } else {
          alert(successMsg);
        }
      } else {
        const errorMsg = data.message || 'خطا در ایجاد بک‌آپ دیتابیس';
        if (typeof Toast !== 'undefined') {
          Toast.show(errorMsg, 'danger', 6000);
        } else {
          alert(errorMsg);
        }
      }
    } catch (err) {
      console.error('Backup request failed:', err);
      const errText = 'خطا در برقراری ارتباط با سرور جهت پشتیبان‌گیری';
      if (typeof Toast !== 'undefined') {
        Toast.show(errText, 'danger', 6000);
      } else {
        alert(errText);
      }
    } finally {
      isBackingUp = false;
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('opacity-70', 'cursor-not-allowed');
      }
      if (iconEl) {
        iconEl.innerHTML = '💾';
      }
      if (textEl) {
        textEl.textContent = 'پشتیبان‌گیری دیتابیس';
      }
    }
  }

  return { createBackup };
})();

// Attach globally
window.Backup = Backup;
