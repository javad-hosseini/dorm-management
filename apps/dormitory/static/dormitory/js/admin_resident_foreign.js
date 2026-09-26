/**
 * Handles 'is_foreign' (اتباع) toggle in Django Jazzmin admin resident change/add form.
 * Dynamically switches the national_code label, placeholder, and help-text between:
 * - "کد ملی" (for Iranian residents): Locked strictly to 10 digits, numeric only.
 * - "شماره پاسپورت / کد فراگیر اتباع" (for foreign residents): Unlocked, letters and numbers allowed.
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
        const helpBlock = fieldContainer ? (fieldContainer.querySelector('.help-block') || fieldContainer.querySelector('.help') || fieldContainer.querySelector('small:not(.national-code-counter)')) : null;

        // Create or find counter element
        let counterEl = fieldContainer ? fieldContainer.querySelector('.national-code-counter') : null;
        if (!counterEl && fieldContainer) {
            counterEl = document.createElement('div');
            counterEl.className = 'national-code-counter';
            counterEl.style.fontSize = '11px';
            counterEl.style.marginTop = '4px';
            counterEl.style.fontWeight = 'bold';
            counterEl.style.transition = 'color 0.2s ease';
            nationalCodeInput.parentElement.appendChild(counterEl);
        }

        // Store default values
        const defaultLabel = nationalCodeLabel ? nationalCodeLabel.innerHTML : 'کد ملی:';
        const defaultPlaceholder = 'کد ملی ۱۰ رقمی (ایرانی)';
        const defaultHelp = helpBlock ? helpBlock.innerHTML : '';

        const foreignLabel = '<span style="color:#0284c7; font-weight:bold;">🌐 شماره پاسپورت / کد فراگیر اتباع:</span>';
        const foreignPlaceholder = 'شماره پاسپورت یا شناسه یکتا/کد فراگیر (مثال: P12345678)';
        const foreignHelp = '<span style="color:#0284c7;">📌 شماره گذرنامه یا کد فراگیر تبعه خارجی را وارد کنید. بدون محدودیت رقم (شامل حروف و اعداد).</span>';

        function updateCounter(length, isForeign) {
            if (!counterEl) return;
            if (isForeign) {
                counterEl.innerHTML = '<span style="color:#0284c7;">🌐 حالت اتباع: بدون محدودیت ارقام (حروف و اعداد مجاز است)</span>';
            } else {
                if (length === 10) {
                    counterEl.innerHTML = '<span style="color:#16a34a;">✅ ۱۰ رقم کد ملی تکمیل شد</span>';
                } else if (length > 0) {
                    counterEl.innerHTML = `<span style="color:#d97706;">⚠️ ${length} از ۱۰ رقم وارد شده است</span>`;
                } else {
                    counterEl.innerHTML = '<span style="color:#64748b;">🔒 کد ملی ایرانی (قفل روی حداکثر ۱۰ رقم عددی)</span>';
                }
            }
        }

        function sanitizeInput() {
            const isForeign = foreignCheckbox.checked;
            let val = nationalCodeInput.value || '';

            if (isForeign) {
                // For foreigners: allow letters, numbers, etc.
                // Automatically uppercase latin letters
                const start = nationalCodeInput.selectionStart;
                const end = nationalCodeInput.selectionEnd;
                const upper = val.toUpperCase();
                if (upper !== val) {
                    nationalCodeInput.value = upper;
                    if (start !== null && end !== null) {
                        nationalCodeInput.setSelectionRange(start, end);
                    }
                }
                updateCounter(nationalCodeInput.value.length, true);
            } else {
                // For Iranian:
                // 1. Convert Persian and Arabic digits to English 0-9
                const p2e = d => '0123456789'['۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩'.indexOf(d) % 10];
                let cleaned = val.replace(/[۰-۹٠-٩]/g, p2e);

                // 2. Remove any character that is not an ASCII digit
                cleaned = cleaned.replace(/\D/g, '');

                // 3. Strictly cap at 10 digits
                if (cleaned.length > 10) {
                    cleaned = cleaned.slice(0, 10);
                }

                if (val !== cleaned) {
                    nationalCodeInput.value = cleaned;
                }
                updateCounter(cleaned.length, false);
            }
        }

        function updateUI(isForeign, animate) {
            if (isForeign) {
                if (nationalCodeLabel) {
                    nationalCodeLabel.innerHTML = foreignLabel;
                }
                nationalCodeInput.placeholder = foreignPlaceholder;
                nationalCodeInput.setAttribute('dir', 'ltr');
                nationalCodeInput.setAttribute('maxlength', '30'); // Allow longer passport/foreign codes
                nationalCodeInput.removeAttribute('inputmode');
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
                nationalCodeInput.setAttribute('maxlength', '10'); // Locked strictly to 10 digits
                nationalCodeInput.setAttribute('inputmode', 'numeric');
                nationalCodeInput.style.letterSpacing = '';
                nationalCodeInput.style.borderColor = '';
                nationalCodeInput.style.backgroundColor = '';
                if (helpBlock) {
                    helpBlock.innerHTML = defaultHelp;
                }
            }

            sanitizeInput();

            if (animate) {
                nationalCodeInput.classList.add('pulse-highlight');
                setTimeout(() => {
                    nationalCodeInput.classList.remove('pulse-highlight');
                }, 400);
            }
        }

        // Prevent typing non-digits and prevent exceeding 10 digits when not foreign
        nationalCodeInput.addEventListener('keypress', function(e) {
            if (foreignCheckbox.checked) {
                return; // No restrictions for foreign residents
            }
            // Allow control keys (backspace, delete, tab, enter, arrows, copy/paste shortcuts)
            if (e.ctrlKey || e.altKey || e.metaKey || e.key.length > 1) {
                return;
            }
            // Block non-digit keys (allow English, Persian, Arabic digits)
            if (!/[\d۰-۹٠-٩]/.test(e.key)) {
                e.preventDefault();
                return;
            }
            // Check if already 10 digits and user is not replacing selected text
            const selectedLength = (this.selectionEnd || 0) - (this.selectionStart || 0);
            if (this.value.length >= 10 && selectedLength === 0) {
                e.preventDefault();
            }
        });

        // Input event (typing, deleting, mobile keyboard, voice input)
        nationalCodeInput.addEventListener('input', sanitizeInput);

        // Paste event
        nationalCodeInput.addEventListener('paste', function() {
            setTimeout(sanitizeInput, 0);
        });

        // Checkbox change listener
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
