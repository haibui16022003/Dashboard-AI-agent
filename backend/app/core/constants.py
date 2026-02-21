"""Allow-list constants for dashboard action validation."""

# Supported action types
ALLOWED_ACTIONS: set[str] = {
    "set_filters",
    "clear_filters",
    "navigate",
    "export",
}

# Filter fields that the agent is allowed to manipulate.
# These must match the `name` attribute of <Dropdown> components in Evidence pages.
ALLOWED_FILTER_FIELDS: set[str] = {
    "category",
    "year",
}

# Pages that the agent is allowed to navigate to.
ALLOWED_PAGES: set[str] = {
    "/",
    "/settings",
}

# Export formats supported by the frontend.
ALLOWED_EXPORT_FORMATS: set[str] = {
    "csv",
    "xlsx",
}
