document.addEventListener("DOMContentLoaded", function () {
    // Only inject global header/footer if the template didn't already render it
    if (!document.querySelector(".xav-global-navbar")) {
        const navHtml = `
            <header class="xav-global-navbar">
                <div class="xav-nav-container">
                    <a href="/" class="xav-brand">
                        <img src="/assets/xavirgin_os/images/xavirgin_logo.jpeg" alt="Xavirgin" onerror="this.style.display='none'">
                        <span>xavirgin<span style="color:#00e599;">.os</span></span>
                    </a>
                    <nav class="xav-nav-links">
                        <a href="/" class="xav-link">Home</a>
                        <a href="/careers" class="xav-link">Careers & Cohorts</a>
                        <a href="https://xavirgin.com" target="_blank" class="xav-link">Main Website ↗</a>
                        <a href="/login" class="xav-btn-emerald">Portal Login</a>
                    </nav>
                </div>
            </header>
        `;
        document.body.insertAdjacentHTML("afterbegin", navHtml);
    }

    if (!document.querySelector(".xav-global-footer")) {
        const footerHtml = `
            <footer class="xav-global-footer">
                <div class="xav-footer-inner">
                    <div class="row g-4 justify-content-between align-items-start">
                        <div class="col-md-6">
                            <div class="fw-bold text-white mb-1" style="font-size: 15px;">XAVIRGIN (OPC) PRIVATE LIMITED</div>
                            <div class="font-monospace small mb-2" style="color: #00e599;">CIN: U62090KL2025OPC098558</div>
                            <p class="small mb-1" style="color: #94a3b8;">
                                Registered Office: 8/372, Ground Floor, Valiyaparambil, Edathala, Aluva, Ernakulam, Kerala — 683561, India
                            </p>
                            <p class="small mb-0" style="color: #64748b;">
                                Central Registration Centre, Ministry of Corporate Affairs, Government of India
                            </p>
                        </div>
                        <div class="col-md-6 text-md-end">
                            <div class="fw-bold text-white mb-2 small text-uppercase" style="letter-spacing: 0.8px;">Statutory & Legal Policies</div>
                            <div class="xav-legal-links justify-content-md-end">
                                <a href="https://xavirgin.com/privacy-policy.html" target="_blank" rel="noopener">Privacy Policy ↗</a>
                                <a href="https://xavirgin.com/terms-and-conditions.html" target="_blank" rel="noopener">Terms & Conditions ↗</a>
                                <a href="https://xavirgin.com/legal-notice.html" target="_blank" rel="noopener">Legal Notice ↗</a>
                                <a href="https://xavirgin.com/workplace-policy.html" target="_blank" rel="noopener">Workplace Policy ↗</a>
                            </div>
                            <div class="mt-3 small" style="color: #64748b;">
                                &copy; 2026 XAVIRGIN (OPC) PRIVATE LIMITED. All rights reserved.
                            </div>
                        </div>
                    </div>
                </div>
            </footer>
        `;
        document.body.insertAdjacentHTML("beforeend", footerHtml);
    }
});