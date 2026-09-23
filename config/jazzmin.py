"""
Jazzmin Configuration for Dormitory Management System
"""

# ==========================================================
# JAZZMIN SETTINGS
# ==========================================================

JAZZMIN_SETTINGS = {

    # ------------------------------------------------------
    # Branding
    # ------------------------------------------------------

    "site_title": "مدیریت خوابگاه",
    "site_header": "مدیریت خوابگاه",
    "site_brand": "سامانه خوابگاه",

    "site_logo": None,
    "site_icon": None,

    "login_logo": None,
    "login_logo_dark": None,

    "site_logo_classes": "img-circle elevation-2",

    "welcome_sign": "به سامانه مدیریت خوابگاه خوش آمدید 👋",

    "copyright": "سامانه مدیریت هوشمند خوابگاه",

    # ------------------------------------------------------
    # Theme
    # ------------------------------------------------------

    "show_theme_chooser": True,
    "default_theme_mode": "auto",

    # ------------------------------------------------------
    # Navigation
    # ------------------------------------------------------

    "show_sidebar": True,
    "navigation_expanded": True,

    "hide_apps": [],
    "hide_models": [],

    "order_with_respect_to": [
        "dormitory",
        "archive",
        "accounts",
        "auth",
    ],

    # ------------------------------------------------------
    # Search
    # ------------------------------------------------------

    "search_model": [
        "dormitory.Resident",
        "dormitory.Room",
        "dormitory.Transaction",
    ],

    # ------------------------------------------------------
    # User Menu
    # ------------------------------------------------------

    "usermenu_links": [],

    # ------------------------------------------------------
    # Top Menu
    # ------------------------------------------------------

    "topmenu_links": [
        {
            "name": "پیشخوان ادمین",
            "url": "admin:index",
        },
        {
            "name": "داشبورد تحلیلی",
            "url": "/dashboard/admin/",
            "new_window": True,
        },
    ],

    # ------------------------------------------------------
    # Icons
    # ------------------------------------------------------

    "icons": {
        "auth": "fas fa-shield-alt",
        "auth.user": "fas fa-user",
        "auth.group": "fas fa-users",

        "accounts": "fas fa-id-badge",
        "accounts.supervisor": "fas fa-user-shield",

        "dormitory": "fas fa-hotel",
        "dormitory.dormitory": "fas fa-building",
        "dormitory.room": "fas fa-door-open",
        "dormitory.resident": "fas fa-user-graduate",
        "dormitory.transaction": "fas fa-receipt",

        "archive": "fas fa-archive",
        "archive.archivedresident": "fas fa-user-slash",
        "archive.archivedtransaction": "fas fa-file-invoice-dollar",
    },

    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",

    # ------------------------------------------------------
    # Forms
    # ------------------------------------------------------

    "related_modal_active": True,
    "changeform_format": "horizontal_tabs",

    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "dormitory.resident": "horizontal_tabs",
        "dormitory.transaction": "horizontal_tabs",
    },

    # ------------------------------------------------------
    # Language
    # ------------------------------------------------------

    "language_chooser": False,

}

# ==========================================================
# UI TWEAKS
# ==========================================================

JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "navbar": "navbar-dark navbar-primary",
    "brand_colour": "navbar-primary",
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "accent": "accent-primary",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    }
}