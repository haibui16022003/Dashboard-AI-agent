/**
 * Dashboard Actions — WebSocket client that receives DASHBOARD_ACTION messages
 * from the AI Agent backend and applies them to the Evidence.dev frontend
 * by manipulating URL query parameters.
 *
 * Evidence.dev binds <Dropdown name="X"> to `${inputs.X.value}` via URL params.
 * Updating the URL (with goto()) triggers Svelte reactivity → SQL re-execution.
 */

import { goto } from "$app/navigation";

const WS_URL = "ws://localhost:4000/ws";
const RECONNECT_DELAY_MS = 3_000;

let ws = null;
let reconnectTimer = null;

// ── WebSocket lifecycle ───────────────────────────────────────────

export function connectWebSocket() {
    if (ws && ws.readyState <= WebSocket.OPEN) return;

    ws = new WebSocket(WS_URL);

    ws.addEventListener("open", () => {
        console.log("[DashboardActions] WebSocket connected");
    });

    ws.addEventListener("message", (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "DASHBOARD_ACTION") {
                handleAction(msg.payload);
            }
        } catch (err) {
            console.error("[DashboardActions] Failed to parse message:", err);
        }
    });

    ws.addEventListener("close", () => {
        console.warn("[DashboardActions] WebSocket closed, reconnecting...");
        scheduleReconnect();
    });

    ws.addEventListener("error", (err) => {
        console.error("[DashboardActions] WebSocket error:", err);
        ws.close();
    });
}

function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket();
    }, RECONNECT_DELAY_MS);
}

export function disconnectWebSocket() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    if (ws) {
        ws.close();
        ws = null;
    }
}

// ── Action handlers ─────────────────────────────────────────────

function handleAction(payload) {
    console.log("[DashboardActions] Applying action:", payload);

    switch (payload.action) {
        case "set_filters":
            applyFilters(payload.filters);
            break;
        case "clear_filters":
            clearFilters(payload.fields);
            break;
        case "navigate":
            navigateToPage(payload.page);
            break;
        case "export":
            exportData(payload.format);
            break;
        default:
            console.warn("[DashboardActions] Unknown action:", payload.action);
    }
}

/**
 * Apply filters by setting URL query parameters.
 * e.g. filters = [{ field: "category", value: "Clothing" }]
 *   → URL becomes ?category=Clothing
 */
function applyFilters(filters) {
    const url = new URL(window.location.href);
    for (const { field, value } of filters) {
        url.searchParams.set(field, value);
    }
    goto(url.pathname + url.search, { replaceState: true, noScroll: true });
}

/**
 * Clear filters by setting them back to the wildcard "%" (Evidence "show all").
 */
function clearFilters(fields) {
    const url = new URL(window.location.href);
    for (const field of fields) {
        // Evidence uses "%" as the wildcard / "All" value
        url.searchParams.set(field, "%");
    }
    goto(url.pathname + url.search, { replaceState: true, noScroll: true });
}

/**
 * Navigate to a different Evidence page.
 */
function navigateToPage(page) {
    goto(page, { noScroll: false });
}

/**
 * Export visible data as CSV (basic implementation).
 * Finds the first <table> on the page and converts it to a downloadable file.
 */
function exportData(format) {
    const table = document.querySelector("table");
    if (!table) {
        console.warn("[DashboardActions] No table found on page for export");
        return;
    }

    const rows = Array.from(table.querySelectorAll("tr"));
    const csvContent = rows
        .map((row) => {
            const cells = Array.from(row.querySelectorAll("th, td"));
            return cells.map((cell) => `"${cell.textContent.trim()}"`).join(",");
        })
        .join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `dashboard-export.${format === "xlsx" ? "csv" : format}`;
    link.click();
    URL.revokeObjectURL(url);
}
