/**
 * Handles 'is_foreign' (اتباع) toggle in Django Jazzmin admin resident change/add form.
 * Dynamically switches the national_code label, placeholder, and help-text between:
 * - "کد ملی" (for Iranian residents)
 * - "شماره پاسپورت / کد فراگیر اتباع" (for foreign residents)
 */
(function() {
    function initForeignResidentToggle() {
        const foreignCheckbox = document.getElementById('id_is_foreign');
        const nationalCodeInput = document.getElementById('id_national_code');

        if (!foreignCheckbox || !nationalCodeInput) {
            return;
        }

        // Find label
        const nationalCodeLabel = document.querySelector('label[for="id_national_code"]');
        
        // Find help text container
        const fieldContainer = nationalCodeInput.closest('.form-group') || nationalCodeInput.closest('.field-national_code');
        const helpBlock = fieldContainer ? (fieldContainer.querySelector('.help-block') || fieldContainer.querySelector('.help') || fieldContainer.querySelector('small')) : null;

        // Store default values
        const defaultLabel = nationalCodeLabel ? nationalCodeLabel.innerHTML : 'کد ملی:';
        const defaultPlaceholder = 'کد ملی ۱۰ رقمی (ایرانی)';
        const defaultHelp = helpBlock ? helpBlock.innerHTML : '';

        const foreignLabel = '<span style="color:#0284c7; font-weight:bold;">🌐 شماره پاسپورت / کد فراگیر اتباع:</span>';
        const foreignPlaceholder = 'شماره پاسپورت یا شناسه یکتا/کد فراگیر (مثال: P12345678)';
        const foreignHelp = '<span style="color:#0284c7;">📌 شماره گذرنامه یا کد فراگیر ۱۰-۱۲ رقمی تبعه خارجی را وارد کنید. نیازی به اعتبارسنجی ۱۰ رقمی کد ملی نیست.</span>';

        function updateUI(isForeign, animate) {
            if (isForeign) {
                if (nationalCodeLabel) {
                    nationalCodeLabel.innerHTML = foreignLabel;
                }
                nationalCodeInput.placeholder = foreignPlaceholder;
                nationalCodeInput.setAttribute('dir', 'ltr');
                nationalCodeInput.style.letterSpacing = '1px';
                nationalCodeInput.style.borderColor = '#38bdf8';
                nationalCodeInput.style.backgroundColor = 'rgba(56, 189, 248, 0.05)';
                if (helpBlock) {
                    helpBlock.innerHTML = foreignHelp;
                }
            } else {
                if (nationalCodeLabel) {
                    nationalCodeLabel.innerHTML = defaultLabel;
                }
                nationalCodeInput.placeholder = defaultPlaceholder;
                nationalCodeInput.removeAttribute('dir');
                nationalCodeInput.style.letterSpacing = '';
                nationalCodeInput.style.borderColor = '';
                nationalCodeInput.style.backgroundColor = '';
                if (helpBlock) {
                    helpBlock.innerHTML = defaultHelp;
                }
            }

            if (animate) {
                nationalCodeInput.classList.add('pulse-highlight');
                setTimeout(() => {
                    nationalCodeInput.classList.remove('pulse-highlight');
                }, 400);
            }
        }

        // Auto-uppercase passport letters on input if foreign is checked
        nationalCodeInput.addEventListener('input', function() {
            if (foreignCheckbox.checked && this.value) {
                const start = this.selectionStart;
                const end = this.selectionEnd;
                this.value = this.value.toUpperCase();
                this.setSelectionRange(start, end);
            }
        });

        foreignCheckbox.addEventListener('change', function() {
            updateUI(this.checked, true);
            nationalCodeInput.focus();
        });

        // Initialize state on load
        updateUI(foreignCheckbox.checked, false);

        // Decorate checkbox container with a badge for better UX in Jazzmin
        const foreignContainer = foreignCheckbox.closest('.form-group') || foreignCheckbox.closest('.field-is_foreign');
        if (foreignContainer) {
            const foreignLabelEl = foreignContainer.querySelector('label') || foreignCheckbox.parentElement;
            if (foreignLabelEl && !foreignLabelEl.querySelector('.foreign-badge')) {
                const badge = document.createElement('span');
                badge.className = 'badge badge-info foreign-badge';
                badge.style.marginRight = '6px';
                badge.style.fontSize = '11px';
                badge.style.fontWeight = 'normal';
                badge.textContent = 'اتباع غیرایرانی';
                foreignLabelEl.appendChild(badge);
            }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initForeignResidentToggle);
    } else {
        initForeignResidentToggle();
    }
})();
