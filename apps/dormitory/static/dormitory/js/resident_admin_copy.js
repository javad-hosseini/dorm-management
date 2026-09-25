/**
 * Helper to copy resident profile to clipboard in Django Admin (Jazzmin)
 */
function copyResidentClipboard(btn) {
    if (!btn) return;
    const text = btn.getAttribute('data-resident-text') || btn.dataset.residentText;
    if (!text) return;

    function markSuccess() {
        const origHtml = btn.innerHTML;
        btn.innerHTML = '✅ کپی شد!';
        btn.classList.remove('btn-outline-primary', 'btn-outline-info');
        btn.classList.add('btn-success');
        setTimeout(() => {
            btn.innerHTML = origHtml;
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-primary');
        }, 2000);
    }

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(markSuccess).catch(() => fallbackCopy(text, markSuccess));
    } else {
        fallbackCopy(text, markSuccess);
    }
}

function fallbackCopy(text, callback) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    ta.style.top = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
        document.execCommand('copy');
        if (callback) callback();
    } catch (e) {
        prompt('متن مشخصات را به صورت دستی کپی کنید:', text);
    }
    document.body.removeChild(ta);
}
