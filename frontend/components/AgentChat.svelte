<script>
    import { onMount, onDestroy } from "svelte";
    import { page } from "$app/stores";

    let isOpen = false;
    let messages = [];
    let inputText = "";
    let isLoading = false;

    const AGENT_URL = "http://localhost:4000/agent/action";
    const WS_URL = "ws://localhost:4000/ws";
    const RECONNECT_DELAY_MS = 3000;

    let ws = null;
    let reconnectTimer = null;

    // Derive the current page name from the SvelteKit route
    $: currentPage = ($page?.route?.id ?? "/index").replace(/^\//, "") || "index";

    // ── WebSocket ─────────────────────────────────────────────────
    function connectWebSocket() {
        if (typeof window === "undefined") return;
        if (ws && ws.readyState <= WebSocket.OPEN) return;
        try {
            ws = new WebSocket(WS_URL);
            ws.addEventListener("open", () => console.log("[AgentChat] WS connected"));
            ws.addEventListener("message", (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    console.log("[AgentChat] WS message:", msg);
                    if (msg.type === "DASHBOARD_ACTION") {
                        dispatchAction(msg.payload);
                    }
                } catch (err) {
                    console.error("[AgentChat] WS parse error:", err);
                }
            });
            ws.addEventListener("close", () => scheduleReconnect());
            ws.addEventListener("error", () => { if (ws) ws.close(); });
        } catch (err) {
            console.error("[AgentChat] WS init error:", err);
            scheduleReconnect();
        }
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connectWebSocket();
        }, RECONNECT_DELAY_MS);
    }

    function disconnectWebSocket() {
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
        if (ws) { ws.close(); ws = null; }
    }

    // ── Action dispatcher ─────────────────────────────────────────
    function dispatchAction(payload) {
        console.log("[AgentChat] Dispatching dashboard-action:", payload);

        if (payload.action === "navigate") {
            window.location.pathname = payload.page;
            return;
        }

        if (payload.action === "export") {
            exportData(payload.format);
            return;
        }

        window.dispatchEvent(new CustomEvent("dashboard-action", { detail: payload }));
    }

    function exportData(format) {
        const table = document.querySelector("table");
        if (!table) return;
        const rows = Array.from(table.querySelectorAll("tr"));
        const csv = rows
            .map(row => Array.from(row.querySelectorAll("th, td"))
                .map(c => `"${c.textContent.trim()}"`)
                .join(","))
            .join("\n");
        const blob = new Blob([csv], { type: "text/csv" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `dashboard-export.${format}`;
        a.click();
        URL.revokeObjectURL(a.href);
    }

    // ── Lifecycle ──
    onMount(() => connectWebSocket());
    onDestroy(() => disconnectWebSocket());

    // ── Chat UI logic ──

    function toggle() { isOpen = !isOpen; }

    async function sendMessage() {
        const text = inputText.trim();
        if (!text || isLoading) return;

        messages = [...messages, { role: "user", content: text }];
        inputText = "";
        isLoading = true;

        try {
            const res = await fetch(AGENT_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt: text, page: currentPage }),
            });
            if (!res.ok) throw new Error(`Server responded with ${res.status}`);
            const data = await res.json();

            // Build the displayed message content
            let content = data.result || "";

            // If there's a data result, attach a formatted table if available
            const dr = data.data_result;
            if (dr && dr.rows && dr.rows.length > 0) {
                const tableHtml = buildResultTable(dr);
                messages = [
                    ...messages,
                    { role: "agent", content: data.result || "📊 Here are the results:", html: tableHtml }
                ];
            } else {
                // Action-only or error response — show badge + confirmation text
                if (data.actions && data.actions.length > 0) {
                    const badges = data.actions.map(a => {
                        switch (a.action) {
                            case "set_filters":   return "🔽";
                            case "clear_filters": return "🧹";
                            case "navigate":      return "📄";
                            case "export":        return "📥";
                            default:              return "⚡";
                        }
                    });
                    content = `${badges.join(" ")}  ${content}`;
                }
                messages = [...messages, { role: "agent", content }];
            }

            // Apply dashboard actions from HTTP response
            if (data.actions && data.actions.length > 0) {
                for (const action of data.actions) {
                    dispatchAction(action);
                }
            }

        } catch (err) {
            messages = [...messages, { role: "agent", content: `⚠️ Error: ${err.message}` }];
        } finally {
            isLoading = false;
        }
    }

    /**
     * Build a compact HTML table from a DataResult for display in the chat.
     * Limited to first 10 rows to keep the chat readable.
     */
    function buildResultTable(dr) {
        const maxRows = 10;
        const cols = dr.columns;
        const rows = dr.rows.slice(0, maxRows);

        const headerCells = cols.map(c => `<th>${escHtml(c)}</th>`).join("");
        const bodyRows = rows.map(row => {
            const cells = cols.map(c => {
                const v = row[c];
                const formatted = typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v ?? "");
                return `<td>${escHtml(formatted)}</td>`;
            }).join("");
            return `<tr>${cells}</tr>`;
        }).join("");

        const moreNote = dr.rows.length > maxRows
            ? `<p class="more-note">Showing ${maxRows} of ${dr.rows.length} rows</p>`
            : "";

        return `<table class="result-table"><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody></table>${moreNote}`;
    }

    function escHtml(str) {
        return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    function handleKeydown(e) {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    }
</script>

<div class="fixed bottom-6 right-6 z-[9999] font-sans">
    <!-- Toggle -->
    <button on:click={toggle} aria-label="Toggle AI chat"
        class="w-14 h-14 rounded-full border-none bg-gradient-to-br from-indigo-500 to-purple-500 text-white flex items-center justify-center shadow-lg shadow-indigo-500/40 hover:scale-110 hover:shadow-xl hover:shadow-indigo-500/60 transition-all cursor-pointer">
        {#if isOpen}
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        {:else}
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        {/if}
    </button>

    <!-- Panel -->
    {#if isOpen}
        <div class="absolute bottom-[72px] right-0 w-[420px] max-h-[580px] bg-[#1e1e2e] rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-[slideUp_0.25s_ease-out]">
            <div class="px-4 py-3.5 bg-gradient-to-br from-indigo-500 to-purple-500 text-white font-semibold text-[15px] flex items-center gap-2">
                🤖 AI Data Assistant
                <span class="ml-auto text-[10px] opacity-70 font-normal">Actions · Queries · Hybrid</span>
            </div>

            <div class="flex-1 overflow-y-auto p-4 flex flex-col gap-3 min-h-[200px] max-h-[400px]">
                {#if messages.length === 0}
                    <p class="text-zinc-400 text-[13px] text-center mt-12 leading-relaxed">
                        Ask me to filter data, answer data questions, or both.<br/>
                        <span class="opacity-60 text-[11px]">e.g. "What is the total revenue in 2020?"</span>
                    </p>
                {/if}

                {#each messages as msg}
                    <div class="max-w-[92%] {msg.role === 'user' ? 'self-end' : 'self-start'}">
                        <div class="text-[11px] font-semibold uppercase tracking-wider mb-1 {msg.role === 'user' ? 'text-right text-purple-400' : 'text-zinc-500'}">
                            {msg.role === "user" ? "You" : "Agent"}
                        </div>
                        <div class="px-3.5 py-2.5 rounded-xl text-[13px] leading-relaxed break-words {msg.role === 'user' ? 'bg-indigo-500 text-white rounded-br-sm' : 'bg-[#27273a] text-zinc-200 rounded-bl-sm'}">
                            {msg.content}
                            {#if msg.html}
                                <!-- svelte-ignore a11y-no-static-element-interactions -->
                                <div class="result-html mt-2">{@html msg.html}</div>
                            {/if}
                        </div>
                    </div>
                {/each}

                {#if isLoading}
                    <div class="self-start max-w-[88%]">
                        <div class="text-[11px] font-semibold uppercase tracking-wider mb-1 text-zinc-500">Agent</div>
                        <div class="bg-[#27273a] rounded-xl rounded-bl-sm px-4 py-3 flex gap-1.5">
                            <span class="w-2 h-2 rounded-full bg-purple-400 animate-bounce [animation-delay:0s]"></span>
                            <span class="w-2 h-2 rounded-full bg-purple-400 animate-bounce [animation-delay:0.15s]"></span>
                            <span class="w-2 h-2 rounded-full bg-purple-400 animate-bounce [animation-delay:0.3s]"></span>
                        </div>
                    </div>
                {/if}
            </div>

            <div class="flex gap-2 px-3.5 py-3 border-t border-[#2e2e42] bg-[#1a1a2e]">
                <input type="text" bind:value={inputText} on:keydown={handleKeydown}
                    placeholder="e.g. What is the total revenue in 2020?" disabled={isLoading} id="agent-chat-input"
                    class="flex-1 px-3.5 py-2.5 border border-[#3f3f5c] rounded-lg bg-[#27273a] text-zinc-200 text-[13.5px] outline-none placeholder:text-zinc-500 focus:border-indigo-500 transition-colors" />
                <button on:click={sendMessage} disabled={isLoading || !inputText.trim()} aria-label="Send message"
                    class="w-10 h-10 rounded-lg border-none bg-indigo-500 text-white flex items-center justify-center cursor-pointer hover:bg-indigo-600 hover:scale-105 transition-all disabled:opacity-40 disabled:cursor-not-allowed">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                </button>
            </div>
        </div>
    {/if}
</div>

<style>
    @keyframes slideUp {
        from { opacity: 0; transform: translateY(12px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    /* Result table rendered inside the chat bubble */
    :global(.result-html .result-table) {
        width: 100%;
        border-collapse: collapse;
        font-size: 11px;
        margin-top: 6px;
        color: #d4d4d8;
    }
    :global(.result-html .result-table th) {
        background: #3f3f5c;
        color: #a78bfa;
        padding: 4px 8px;
        text-align: left;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        border-bottom: 1px solid #52527a;
    }
    :global(.result-html .result-table td) {
        padding: 4px 8px;
        border-bottom: 1px solid #2e2e42;
    }
    :global(.result-html .result-table tr:last-child td) {
        border-bottom: none;
    }
    :global(.result-html .more-note) {
        font-size: 10px;
        color: #71717a;
        margin-top: 4px;
        text-align: right;
    }
</style>
