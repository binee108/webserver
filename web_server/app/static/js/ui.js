document.addEventListener('DOMContentLoaded', function () {
    initDropdowns();
    initMobileNav();
    initAlerts();
    initLoadingForms();
    initPasswordValidation();
});

function initDropdowns() {
    const dropdowns = Array.from(document.querySelectorAll('[data-dropdown]'));
    if (!dropdowns.length) {
        return;
    }

    const closeDropdown = (dropdown) => {
        const trigger = dropdown.querySelector('[data-dropdown-toggle]');
        const menu = dropdown.querySelector('[data-dropdown-menu]');
        if (!trigger || !menu) {
            return;
        }
        menu.classList.remove('is-open');
        menu.setAttribute('aria-hidden', 'true');
        trigger.setAttribute('aria-expanded', 'false');
    };

    const openDropdown = (dropdown) => {
        const trigger = dropdown.querySelector('[data-dropdown-toggle]');
        const menu = dropdown.querySelector('[data-dropdown-menu]');
        if (!trigger || !menu) {
            return;
        }
        dropdowns.forEach((other) => {
            if (other !== dropdown) {
                closeDropdown(other);
            }
        });
        menu.classList.add('is-open');
        menu.setAttribute('aria-hidden', 'false');
        trigger.setAttribute('aria-expanded', 'true');
    };

    dropdowns.forEach((dropdown) => {
        const trigger = dropdown.querySelector('[data-dropdown-toggle]');
        if (!trigger) {
            return;
        }

        trigger.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            const menu = dropdown.querySelector('[data-dropdown-menu]');
            if (!menu) {
                return;
            }
            if (menu.classList.contains('is-open')) {
                closeDropdown(dropdown);
            } else {
                openDropdown(dropdown);
            }
        });
    });

    document.addEventListener('click', (event) => {
        dropdowns.forEach((dropdown) => {
            if (!dropdown.contains(event.target)) {
                closeDropdown(dropdown);
            }
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            dropdowns.forEach((dropdown) => closeDropdown(dropdown));
        }
    });
}

function initMobileNav() {
    const nav = document.querySelector('[data-mobile-nav]');
    if (!nav) {
        return;
    }

    const toggleButton = nav.querySelector('[data-mobile-toggle]');
    const overlay = nav.querySelector('[data-mobile-overlay]');
    const panel = nav.querySelector('[data-mobile-panel]');
    const closeTargets = nav.querySelectorAll('[data-mobile-close]');

    if (!toggleButton || !overlay || !panel) {
        return;
    }

    const closeMenu = () => {
        panel.classList.remove('is-open');
        overlay.classList.remove('is-visible');
        toggleButton.classList.remove('active');
        toggleButton.setAttribute('aria-expanded', 'false');
    };

    const openMenu = () => {
        panel.classList.add('is-open');
        overlay.classList.add('is-visible');
        toggleButton.classList.add('active');
        toggleButton.setAttribute('aria-expanded', 'true');
    };

    toggleButton.addEventListener('click', () => {
        if (panel.classList.contains('is-open')) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    overlay.addEventListener('click', closeMenu);
    closeTargets.forEach((target) => {
        target.addEventListener('click', closeMenu);
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeMenu();
        }
    });
}

function initAlerts() {
    document.querySelectorAll('[data-alert]').forEach((alert) => {
        const closeButton = alert.querySelector('[data-alert-close]');
        if (!closeButton) {
            return;
        }
        closeButton.addEventListener('click', () => {
            alert.classList.add('hidden');
            window.setTimeout(() => {
                if (alert.parentNode) {
                    alert.parentNode.removeChild(alert);
                }
            }, 200);
        });
    });
}

function initLoadingForms() {
    document.querySelectorAll('[data-loading-form]').forEach((form) => {
        const button = form.querySelector('[data-loading-button]');
        const defaultText = button ? button.querySelector('[data-loading-default]') : null;
        const busyText = button ? button.querySelector('[data-loading-busy]') : null;

        form.addEventListener('submit', () => {
            if (form.dataset.loading === 'true') {
                return;
            }
            form.dataset.loading = 'true';
            if (button) {
                button.dataset.loading = 'true';
                button.disabled = true;
            }
            if (defaultText) {
                defaultText.hidden = true;
            }
            if (busyText) {
                busyText.hidden = false;
            }
        });
    });
}

function initPasswordValidation() {
    document.querySelectorAll('[data-password-validate]').forEach((form) => {
        const passwordInput = form.querySelector('[data-password-source]');
        const confirmInput = form.querySelector('[data-password-target]');
        const message = form.querySelector('[data-password-message]');
        const submitButton = form.querySelector('[data-password-submit]') || form.querySelector('[data-loading-button]');

        if (!passwordInput || !confirmInput || !submitButton) {
            return;
        }

        const updateState = () => {
            const confirmValue = confirmInput.value;
            const mismatch = confirmValue !== '' && passwordInput.value !== confirmValue;
            confirmInput.classList.toggle('input-error', mismatch);

            if (message) {
                if (mismatch) {
                    message.classList.remove('hidden');
                } else {
                    message.classList.add('hidden');
                }
            }

            if (form.dataset.loading === 'true') {
                submitButton.disabled = true;
                return;
            }

            submitButton.disabled = mismatch;
        };

        passwordInput.addEventListener('input', updateState);
        confirmInput.addEventListener('input', updateState);
        updateState();
    });
}
