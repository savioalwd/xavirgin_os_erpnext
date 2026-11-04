import frappe

no_cache = 1


def get_context(context):
    # If the user is logged in (not a Guest), redirect them straight into the ERP desk workspace
    if frappe.session.user and frappe.session.user != "Guest":
        frappe.local.flags.redirect_location = "/desk/xavirgin-os"
        raise frappe.Redirect

    context.no_cache = 1
    context.title = "Xavirgin OS — Autonomous Enterprise Systems & Engineering Residency"
    context.metatags = {
        "title": "Careers at Xavirgin | Zero Energy Protocol Remote Internships",
        "description": "Join Xavirgin's 90-day practical remote internship and engineering tracks. Build production-grade Flutter, React, Laravel, Python, and UI/UX systems.",
        "keywords": "Xavirgin careers, remote software internship, Zero Energy Protocol, Flutter developer jobs, React developer, Laravel backend, Python AI engineering, UI UX design tracks, India tech jobs, Kerala software startup",
        "canonical": "https://xavirgin.com/careers",
        "robots": "index, follow",
        "author": "XAVIRGIN (OPC) PRIVATE LIMITED",
        
        # Open Graph (Facebook, LinkedIn, Discord previews)
        "og:type": "website",
        "og:site_name": "Xavirgin OS",
        "og:title": "Careers at Xavirgin | Zero Energy Protocol Internships",
        "og:description": "Build real-world software, AI pipelines, and cross-platform apps. Apply for our 90-day remote internship tracks.",
        "og:url": "https://xavirgin.com/careers",
        "og:image": "/assets/xavirgin_os/images/xavirgin_social_card.png",
        "og:image:width": "1200",
        "og:image:height": "630",
        
        # Twitter / X Card
        "twitter:card": "summary_large_image",
        "twitter:site": "@xavirgin_com",
        "twitter:title": "Careers at Xavirgin | Zero Energy Protocol",
        "twitter:description": "Join our 90-day practical engineering and design tracks. Real code, real execution.",
        "twitter:image": "/assets/xavirgin_os/images/xavirgin_social_card.png"
    }
    context.company_legal_name = "XAVIRGIN (OPC) PRIVATE LIMITED"
    context.cin = "U62090KL2025OPC098558"

    # Fetch count of open roles for live badge
    context.open_jobs_count = frappe.db.count(
        "Xavirgin Job Opening", {"status": "Open", "is_published": 1}
    )
    return context